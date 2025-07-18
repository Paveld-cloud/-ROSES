import os
import json
import logging
import datetime
import urllib.parse
import telebot
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Telegram бот
bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# Кэш роз
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные роз загружены")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки роз: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")

try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Webhook ошибка: {e}")

@app.route('/')
def index():
    return "Бот работает!"

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# Вспомогательные функции
def normalize(text):
    return text.replace('"', '').replace("«", "").replace("»", "").lower().strip()

def save_user(message, query=None):
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name,
            message.from_user.username or "",
            now,
            query or ""
        ])
    except Exception as e:
        logger.error(f"❌ Ошибка записи пользователя: {e}")

# Команда /start
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
    save_user(message)

# Обработка кнопок меню
@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "📬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛍 Напишите, какие сорта вас интересуют")

# Поиск розы
@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = message.text.strip().lower()
    save_user(message, query)

    matches = [r for r in cached_roses if normalize(query) in normalize(r.get('Название', ''))]

    if not matches:
        bot.send_message(message.chat.id, "❌ Розы не найдены.")
        return

    for rose in matches:
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"{rose.get('Описание', '')}\n"
            f"Цена: {rose.get('price', '?')}"
        )
        photo_urls = [url.strip() for url in rose.get("photo", "").split(",") if url.strip()]

        encoded_name = urllib.parse.quote_plus(rose.get('Название', ''))
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{encoded_name}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{encoded_name}")
        )

        if photo_urls:
            media = [telebot.types.InputMediaPhoto(url, caption=caption if i == 0 else "", parse_mode='HTML')
                     for i, url in enumerate(photo_urls)]
            bot.send_media_group(message.chat.id, media)
            bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)
        else:
            bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)

# Кнопки ухода и истории
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_buttons(call):
    action, encoded_name = call.data.split("_", 1)
    name = urllib.parse.unquote_plus(encoded_name)

    rose = next((r for r in cached_roses if normalize(name) in normalize(r.get('Название', ''))), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    text = rose.get("Уход" if action == "care" else "История", "Нет информации")
    prefix = "🪴 Уход:\n" if action == "care" else "📜 История:\n"
    bot.send_message(call.message.chat.id, prefix + text)
    bot.answer_callback_query(call.id)

# Запуск
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
