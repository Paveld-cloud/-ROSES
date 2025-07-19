import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация Telegram-бота
bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(CREDS_JSON, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
sheet_users = gs.open_by_url(SPREADSHEET_URL).worksheet("Пользователи")

# Кэш роз и избранное
cached_roses = sheet.get_all_records()
user_search_results = {}
user_favorites = {}

# Flask + Webhook
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
bot.remove_webhook()
bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")

@app.route('/')
def index():
    return 'OK'

@app.route('/telegram', methods=['POST'])
def telegram():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

def send_main_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "⭐ Избранное")
    bot.send_message(chat_id, "🌹 Выберите действие:", reply_markup=markup)

def send_rose_card(chat_id, rose, user_id, idx):
    caption = f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\nОписание: {rose.get('Описание', '?')}"
    photo_url = rose.get('photo', 'https://example.com/default.jpg')
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx}"),
        telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{idx}")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("⭐ Добавить в избранное", callback_data=f"favorite_{idx}")
    )
    bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=['start'])
def start(message):
    send_main_menu(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def search_prompt(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "⭐ Избранное")
def show_favorites(message):
    user_id = message.from_user.id
    favorites = user_favorites.get(user_id, [])
    if not favorites:
        bot.send_message(message.chat.id, "❌ Избранное пусто")
        return
    for idx, rose in enumerate(favorites):
        send_rose_card(message.chat.id, rose, user_id, idx)

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    query = message.text.strip().lower()
    results = [r for r in cached_roses if query in r.get('Название', '').lower()]
    if not results:
        bot.send_message(message.chat.id, "❌ Ничего не найдено")
        return
    user_search_results[message.from_user.id] = results
    for idx, rose in enumerate(results[:5]):
        send_rose_card(message.chat.id, rose, message.from_user.id, idx)

@bot.callback_query_handler(func=lambda call: call.data.startswith("care_"))
def care_detail(call):
    idx = int(call.data.split("_")[1])
    results = user_search_results.get(call.from_user.id, [])
    if idx < len(results):
        bot.send_message(call.message.chat.id, f"🪴 Уход:\n{results[idx].get('Уход', 'Не указано')}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("history_"))
def history_detail(call):
    idx = int(call.data.split("_")[1])
    results = user_search_results.get(call.from_user.id, [])
    if idx < len(results):
        bot.send_message(call.message.chat.id, f"📜 История:\n{results[idx].get('История', 'Не указана')}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("favorite_"))
def add_favorite(call):
    idx = int(call.data.split("_")[1])
    user_id = call.from_user.id
    results = user_search_results.get(user_id, [])
    if idx < len(results):
        rose = results[idx]
        if user_id not in user_favorites:
            user_favorites[user_id] = []
        if rose not in user_favorites[user_id]:
            user_favorites[user_id].append(rose)
            bot.answer_callback_query(call.id, "✅ Добавлено в избранное")
        else:
            bot.answer_callback_query(call.id, "⚠️ Уже в избранном")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)

