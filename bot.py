import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1
users_sheet = spreadsheet.worksheet("Пользователи")  # <-- исправлено

# Кэш роз
cached_roses = []

def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные загружены из таблицы")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask-приложение
app = Flask(__name__)

# Webhook
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")
bot.remove_webhook()
bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# === Хендлеры ===

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        users_sheet.append_row([str(user_id), full_name, username, date])
        logger.info(f"👤 Новый пользователь: {user_id} - {full_name}")
    except Exception as e:
        logger.error(f"❌ Не удалось сохранить пользователя: {e}")

    # Главное меню
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_animation(message.chat.id, "https://media.giphy.com/media/26AHONQ79FdWZhAI0/giphy.gif")
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def search_request(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact_info(message):
    bot.send_message(message.chat.id, "📬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def order_info(message):
    bot.send_message(message.chat.id, "🛒 Напишите, какие сорта вас интересуют")

@bot.message_handler(func=lambda m: m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def search_by_name(message):
    query = message.text.strip().lower()
    rose = next((r for r in cached_roses if query in r.get('Название', '').lower()), None)

    if not rose:
        bot.send_message(message.chat.id, "🚫 Роза не найдена")
        return

    caption = (
        f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
        f"{rose.get('Описание', '')}\n"
        f"Цена: {rose.get('price', '?')}"
    )

    photo_urls = [url.strip() for url in rose.get('photo', '').split(',') if url.strip()]
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(
        telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{rose.get('Название')}"),
        telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{rose.get('Название')}")
    )

    if photo_urls:
        media = [telebot.types.InputMediaPhoto(media=url) for url in photo_urls[:10]]
        media[0].caption = caption
        media[0].parse_mode = 'HTML'
        bot.send_media_group(message.chat.id, media)
        bot.send_message(message.chat.id, "👇 Подробнее:", reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_buttons(call):
    action, rose_name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if rose_name.lower() in r.get('Название', '').lower()), None)

    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    if action == "care":
        bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
    else:
        bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
    bot.answer_callback_query(call.id)

# Отладка локально
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
