import os
import json
import logging
import telebot
import urllib.parse
import gspread
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==================== Настройки ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

# ==================== Логирование ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== Авторизация Google Sheets ====================
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# ==================== Инициализация бота ====================
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== Кнопки ====================
def start_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("🔍 Поиск"))
    return markup

def rose_inline_buttons(rose_name):
    encoded = urllib.parse.quote_plus(rose_name)
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🪴 Уход", callback_data=f"care_{encoded}"),
        InlineKeyboardButton("📜 История", callback_data=f"story_{encoded}")
    )
    return markup

# ==================== Сохранение пользователя и запроса ====================
def save_user(message, query=None):
    user_id = message.from_user.id
    name = message.from_user.first_name or ''
    username = message.from_user.username or ''
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [str(user_id), name, username, date, query or ""]
    users_sheet.append_row(row)

# ==================== Обработка /start ====================
@bot.message_handler(commands=['start'])
def handle_start(message):
    save_user(message)
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать! Введите название розы для поиска.",
        reply_markup=start_keyboard()
    )

# ==================== Обработка "Поиск" ====================
@bot.message_handler(func=lambda msg: msg.text == "🔍 Поиск")
def handle_search_command(message):
    bot.send_message(message.chat.id, "🔎 Введите название розы")

# ==================== Поиск розы ====================
@bot.message_handler(func=lambda message: True)
def handle_query(message):
    query = message.text.strip().lower()
    save_user(message, query)

    rows = sheet.get_all_records()
    found_roses = [r for r in rows if query in str(r.get("Название", "")).lower()]

    if not found_roses:
        bot.send_message(message.chat.id, "❌ Розы не найдены.")
        return

    for rose in found_roses:
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n\n"
            f"Цена: {rose.get('price', '')}\n"
            f"{rose.get('Описание', '')}"
        )
        photo_url = rose.get("photo", "")
        buttons = rose_inline_buttons(rose.get("Название", ""))
        try:
            bot.send_photo(message.chat.id, photo_url, caption=caption, reply_markup=buttons, parse_mode='HTML')
        except Exception:
            bot.send_message(message.chat.id, caption, reply_markup=buttons, parse_mode='HTML')

# ==================== Inline-кнопки ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    if data.startswith("care_"):
        name = urllib.parse.unquote_plus(data[5:])
        rows = sheet.get_all_records()
        for rose in rows:
            if name.strip().lower() in str(rose.get("Название", "")).strip().lower():
                text = rose.get("Уход", "Информация об уходе отсутствует.")
                bot.send_message(call.message.chat.id, f"🪴 <b>Уход за розой</b>\n\n{text}", parse_mode='HTML')
                break

    elif data.startswith("story_"):
        name = urllib.parse.unquote_plus(data[6:])
        rows = sheet.get_all_records()
        for rose in rows:
            if name.strip().lower() in str(rose.get("Название", "")).strip().lower():
                text = rose.get("История", "История отсутствует.")
                bot.send_message(call.message.chat.id, f"📜 <b>История розы</b>\n\n{text}", parse_mode='HTML')
                break

# ==================== Запуск ====================
if __name__ == "__main__":
    from flask import Flask, request

    app = Flask(__name__)

    @app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
        return "!", 200

    @app.route("/")
    def index():
        return "Bot is running!"

    bot.remove_webhook()
    bot.set_webhook(url=f"{os.getenv('WEBHOOK_URL')}/{BOT_TOKEN}")
