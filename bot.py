import os
import logging
import telebot
import gspread
import urllib.parse
from flask import Flask, request
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# 🔧 Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(eval(creds_json))
client = gspread.authorize(creds)
spreadsheet = client.open_by_url(SPREADSHEET_URL)
worksheet = spreadsheet.worksheet("Лист1")
data = worksheet.get_all_records()

# Flask и Telegram Webhook
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)
rose_cache = data  # Кэш

# 🔍 Нормализация текста
def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    for ch in '«»"()':
        text = text.replace(ch, "")
    return text.replace("роза", "").strip()

# 📌 Поиск роз
def search_rose(query):
    query_norm = normalize(query)
    for rose in rose_cache:
        title_norm = normalize(rose.get("Название", ""))
        if query_norm in title_norm:
            return rose
    return None

# 📥 Обработка текста
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    rose = search_rose(text)

    if not rose:
        bot.send_message(message.chat.id, "❌ Ничего не найдено.")
        return

    caption = f"<b>{rose.get('Название', 'Без названия')}</b>\n\n"
    caption += f"{rose.get('Описание', '').strip()}\n"
    caption += f"\nЦена: {rose.get('G', '?')}"  # Столбец G под ценой (если есть)

    # Кнопки
    keyboard = InlineKeyboardMarkup()
    name_encoded = urllib.parse.quote_plus(rose.get("Название", ""))
    keyboard.row(
        InlineKeyboardButton("🪴 Уход", callback_data=f"care_{name_encoded}"),
        InlineKeyboardButton("📜 История", callback_data=f"history_{name_encoded}")
    )

    photo_url = rose.get("photo", "").strip()
    if photo_url:
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode="HTML", reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=keyboard)

# 🔘 Кнопки: Уход и История
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    if data.startswith("care_") or data.startswith("history_"):
        _, encoded = data.split("_", 1)
        rose_name = urllib.parse.unquote_plus(encoded)
        rose = search_rose(rose_name)

        if not rose:
            bot.answer_callback_query(call.id, "Данные не найдены.")
            return

        if data.startswith("care_"):
            response = rose.get("Уход", "Нет данных по уходу.")
        else:
            response = rose.get("История", "Нет исторических данных.")

        bot.send_message(call.message.chat.id, response)

# 🌐 Webhook
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.data.decode("utf-8"))])
    return "OK"

@app.route("/")
def index():
    return "🤖 Бот работает!"

# 🚀 Установка webhook
bot.remove_webhook()
bot.set_webhook(url="https://roses-production.up.railway.app/telegram")
logger.info("🌐 Webhook установлен")

# 🏁 Запуск Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
