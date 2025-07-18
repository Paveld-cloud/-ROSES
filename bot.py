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
gc = gspread.authorize(creds)
spreadsheet = gc.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1
users_sheet = spreadsheet.worksheet("Пользователи")

# Кэширование данных
cached_roses = []

def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные успешно загружены из Google Таблицы")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке данных: {e}")
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
    logger.error(f"❌ Не удалось установить webhook: {e}")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return '', 200

# Обработчики
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=markup
    )
    # Запись пользователя
    try:
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name or '',
            message.from_user.username or '',
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ''
        ])
    except Exception as e:
        logger.warning(f"⚠️ Не удалось записать пользователя: {e}")

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛒 Напишите, какие сорта вас интересуют")

# Поиск
def clean_query(text):
    bad_words = ["роза", "розу", "розы", "про", "сорт", "сорта"]
    words = text.lower().split()
    return " ".join(w for w in words if w not in bad_words)

@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = clean_query(message.text.strip())
    matched = [r for r in cached_roses if query in r.get('Название', '').lower()]
    
    # Запись запроса в таблицу
    try:
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name or '',
            message.from_user.username or '',
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message.text.strip()
        ])
    except Exception as e:
        logger.warning(f"⚠️ Не удалось записать запрос: {e}")

    if not matched:
        bot.send_message(message.chat.id, "Не найдено ни одной розы с таким названием.")
        return

    for rose in matched:
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"{rose.get('Описание', '')}\n"
        )
        photo_url = rose.get('photo', 'https://example.com/default.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{rose.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{rose.get('Название')}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_rose_details(call):
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

# Запуск локально
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
