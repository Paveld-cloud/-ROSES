import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации из переменных окружения
try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
    CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
except Exception as e:
    logger.error(f"❌ Ошибка загрузки переменных окружения: {e}")
    raise

# Инициализация Telegram-бота
try:
    bot = telebot.TeleBot(BOT_TOKEN)
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    raise

# Авторизация Google Sheets
try:
    creds = Credentials.from_service_account_info(
        CREDS_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gs = gspread.authorize(creds)
    sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
    logger.info("✅ Успешное подключение к Google Таблице")
except Exception as e:
    logger.error(f"❌ Ошибка авторизации в Google Sheets: {e}")
    raise

# Кэш данных роз
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

# Flask-приложение
app = Flask(__name__)

# Установка Webhook при старте под Gunicorn
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Не удалось установить webhook: {e}")

# Простой маршрут для проверки сервиса
@app.route('/')
def index():
    return 'Бот работает!'

# Маршрут для Webhook Telegram
@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# ========== Хендлеры ==========

user_search = {}  # хранение состояния для поиска

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📚 Каталог")
    markup.row("📞 Связаться", "📦 Заказать")
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы:")
    user_search[message.chat.id] = True

@bot.message_handler(func=lambda m: user_search.get(m.chat.id))
def search_by_name(message):
    search_text = message.text.strip().lower()
    user_search[message.chat.id] = False  # сбрасываем флаг

    found = None
    idx_found = None
    for idx, rose in enumerate(cached_roses):
        if search_text in rose.get("Название", "").lower():
            found = rose
            idx_found = idx
            break

    if found:
        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n\n"
            f"{found.get('Описание', '')}\nЦена: {found.get('price', '?')} руб"
        )
        photo_url = found.get('photo', 'https://example.com/default.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx_found}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{idx_found}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "❌ Роза с таким названием не найдена.")

@bot.message_handler(func=lambda m: m.text == "📚 Каталог")
def handle_catalog(message):
    # Показываем первые 5 роз (можно сделать постранично)
    for idx, rose in enumerate(cached_roses[:5]):
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n\n"
            f"{rose.get('Описание', '')}\nЦена: {rose.get('price', '?')} руб"
        )
        photo_url = rose.get('photo', 'https://example.com/default.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{idx}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛒 Напишите, какие сорта вас интересуют")

@bot.callback_query_handler(func=lambda call: call.data.startswith("care_"))
def handle_rose_care(call):
    idx = int(call.data.replace("care_", ""))
    if idx >= len(cached_roses):
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    rose = cached_roses[idx]
    bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("history_"))
def handle_rose_history(call):
    idx = int(call.data.replace("history_", ""))
    if idx >= len(cached_roses):
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    rose = cached_roses[idx]
    bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
    bot.answer_callback_query(call.id)

# =============================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
