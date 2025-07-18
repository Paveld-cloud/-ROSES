import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Кэш роз
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    cached_roses = sheet.get_all_records()
refresh_cached_roses()

# Flask-приложение
app = Flask(__name__)
WEBHOOK_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/telegram"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# Запись пользователя
def save_user_info(message, query=None):
    user_id = message.from_user.id
    name = message.from_user.first_name
    username = message.from_user.username or ''
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    records = users_sheet.get_all_records()
    exists = any(str(r['ID']) == str(user_id) for r in records)
    if not exists or query:
        users_sheet.append_row([user_id, name, username, now, query or ''])

# Обработчики
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=markup
    )
    save_user_info(message)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "📩 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛒 Укажите сорта роз, которые вас интересуют")

@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def search_rose(message):
    query = message.text.strip().lower()
    found = next((r for r in cached_roses if query in r.get('Название', '').lower()), None)
    if found:
        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
            f"{found.get('Описание', '')}\n"
            f"Цена: {found.get('price', '?')}"
        )
        photo_url = found.get('photo', 'https://example.com/placeholder.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        name_encoded = quote_plus(found.get('Название'))
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{name_encoded}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{name_encoded}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "❌ Не найдено роз с таким названием")
    save_user_info(message, query=query)

@bot.callback_query_handler(func=lambda call: call.data.startswith("care_") or call.data.startswith("history_"))
def handle_callbacks(call):
    action, name_enc = call.data.split("_", 1)
    name = unquote_plus(name_enc)
    rose = next((r for r in cached_roses if name.lower() in r.get('Название', '').lower()), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    text = rose.get("Уход" if action == "care" else "История", "Информация отсутствует")
    bot.send_message(call.message.chat.id, f"{'🪴 Уход' if action == 'care' else '📜 История'}:\n{text}")
    bot.answer_callback_query(call.id)

# Запуск
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
