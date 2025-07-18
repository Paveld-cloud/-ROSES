import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime

# Логгирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
    CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
except Exception as e:
    logger.error(f"❌ Ошибка загрузки переменных окружения: {e}")
    raise

# Инициализация бота
try:
    bot = telebot.TeleBot(BOT_TOKEN)
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    raise

# Подключение к Google Sheets
try:
    creds = Credentials.from_service_account_info(
        CREDS_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gs = gspread.authorize(creds)
    sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
    users_sheet = gs.open_by_url(SPREADSHEET_URL).worksheet("Пользователи")
    logger.info("✅ Успешное подключение к Google Таблице")
except Exception as e:
    logger.error(f"❌ Ошибка авторизации в Google Sheets: {e}")
    raise

# Кэш роз
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные успешно загружены из Google Таблицы")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask
app = Flask(__name__)

# Установка webhook
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
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return '', 200

# === Запись пользователя в лист "Пользователи" ===
def save_user_info(user):
    try:
        user_id = str(user.id)
        name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        username = user.username or ''
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing_ids = users_sheet.col_values(1)
        if user_id not in existing_ids:
            users_sheet.append_row([user_id, name, username, date])
            logger.info(f"👤 Пользователь записан: {user_id} - {name}")
    except Exception as e:
        logger.error(f"❌ Ошибка при записи пользователя: {e}")

# === Обработчики ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    save_user_info(message.from_user)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛒 Напишите, какие сорта вас интересуют")

@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = message.text.strip().lower()
    found = None
    for rose in cached_roses:
        name = rose.get('Название', '').strip().lower()
        if query in name:
            found = rose
            break
    if found:
        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
            f"{found.get('Описание', '')}\nЦена: {found.get('price', '?')}"
        )
        photo_url = found.get('photo', 'https://example.com/default.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{found.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{found.get('Название')}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "Не найдено ни одной розы с таким названием.")

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

# Локальный запуск
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Flask запущен на порту {port}")
    app.run(host="0.0.0.0", port=port)
