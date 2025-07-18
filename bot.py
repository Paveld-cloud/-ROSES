import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

bot = telebot.TeleBot(BOT_TOKEN)

creds = Credentials.from_service_account_info(CREDS_JSON)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet_roses = spreadsheet.worksheet("List1")
sheet_users = spreadsheet.worksheet("Пользователи")

cached_roses = sheet_roses.get_all_records()

app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")
bot.remove_webhook()
bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")

@app.route("/")
def index():
    return "Бот работает!"

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

def send_main_menu(chat_id, text):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=["start"])
def start_handler(message):
    user_data = [
        str(message.from_user.id),
        message.from_user.first_name,
        message.from_user.username or "",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ""
    ]
    sheet_users.append_row(user_data)
    send_main_menu(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:")

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def search_handler(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact_handler(message):
    bot.send_message(message.chat.id, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def order_handler(message):
    bot.send_message(message.chat.id, "🛒 Напишите, какие сорта вас интересуют")

@bot.message_handler(func=lambda m: m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def search_rose(message):
    query = message.text.strip().lower()
    sheet_users.append_row([
        str(message.from_user.id),
        message.from_user.first_name,
        message.from_user.username or "",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message.text
    ])
    matches = [r for r in cached_roses if query in r.get("Название", "").lower()]
    if not matches:
        bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.")
        return
    for rose in matches:
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"{rose.get('Описание', '')}\n"
            f"Цена: {rose.get('price', '?')}"
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{rose.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{rose.get('Название')}")
        )
        bot.send_photo(
            message.chat.id,
            rose.get("photo", "https://example.com/default.jpg"),
            caption=caption,
            parse_mode='HTML',
            reply_markup=keyboard
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("care_") or call.data.startswith("history_"))
def callback_details(call):
    action, name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if name.lower() in r.get("Название", "").lower()), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    text = rose.get("Уход" if action == "care" else "История", "Не указано")
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
