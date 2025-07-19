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

# Авторизация Google Sheets (если настроено)
gs = None
sheet = None
sheet_users = None
if SPREADSHEET_URL and CREDS_JSON:
    try:
        creds = Credentials.from_service_account_info(
            CREDS_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gs = gspread.authorize(creds)
        sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
        sheet_users = gs.open_by_url(SPREADSHEET_URL).worksheet("Пользователи")
        logger.info("✅ Google Sheets авторизован")
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets не настроен: {e}")
else:
    logger.warning("⚠️ Google Sheets не настроена — отключена запись в таблицу")

# Кэш данных роз и пользовательские данные
cached_roses = []
user_search_results = {}
user_favorites = {}
rose_search_stats = {}

def refresh_cached_roses():
    global cached_roses
    try:
        if sheet:
            cached_roses = sheet.get_all_records()
            logger.info("✅ Данные роз загружены из Google Таблицы")
        else:
            cached_roses = []
            logger.warning("⚠️ Google Таблица не настроена — данные роз не загружены")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask и Webhook
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
try:
    bot.remove_webhook()
    if WEBHOOK_URL:
        bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
        logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Webhook не установлен: {e}")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# 📥 Новый логгер для реальных результатов поиска
def log_found_rose(message, rose_name):
    try:
        if sheet_users:
            sheet_users.append_row([
                message.from_user.id,
                message.from_user.first_name,
                f"@{message.from_user.username}" if message.from_user.username else "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                rose_name
            ])
            logger.info(f"✅ Сохранён найденный сорт: {rose_name}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи розы в Google Таблицу: {e}")

# Обработчики
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск")
    markup.row("📞 Связаться", "⭐ Избранное")
    bot.send_message(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nНажмите кнопку \"Поиск\" и введите название розы.", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search_prompt(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: True)
def handle_search_text(message):
    query = message.text.strip().lower()
    results = [r for r in cached_roses if query in r.get('Название', '').lower()]

    if not results:
        bot.send_message(message.chat.id, "❌ Ничего не найдено.")
        return

    user_search_results[message.from_user.id] = results

    for idx, rose in enumerate(results[:5]):
        send_rose_card(message.chat.id, rose, message.from_user.id, idx)
        log_found_rose(message, rose.get("Название", "Неизвестно"))

# Отправка карточки розы
def send_rose_card(chat_id, rose, user_id, idx):
    caption = f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\nОписание: {rose.get('Описание', '?')}"
    photo_url = rose.get('photo', 'https://example.com/default.jpg')
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
        telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{user_id}_{idx}")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("⭐ В избранное", callback_data=f"favorite_{user_id}_{idx}")
    )
    bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
