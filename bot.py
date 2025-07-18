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

# Загрузка конфигурации
try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
    CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
except Exception as e:
    logger.error(f"❌ Ошибка загрузки переменных окружения: {e}")
    raise

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Подключение к Google Таблице
try:
    creds = Credentials.from_service_account_info(
        CREDS_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gs = gspread.authorize(creds)
    spreadsheet = gs.open_by_url(SPREADSHEET_URL)
    sheet = spreadsheet.worksheet("List1")
    users_sheet = spreadsheet.worksheet("Пользователи")
    logger.info("✅ Подключение к Google Таблице успешно")
except Exception as e:
    logger.error(f"❌ Ошибка авторизации: {e}")
    raise

# Кэш
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные роз загружены")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке роз: {e}")
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
    logger.error(f"❌ Ошибка установки webhook: {e}")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return '', 200

# Команды
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name or "",
            message.from_user.username or "",
            time.strftime("%Y-%m-%d %H:%M:%S"),
            ""  # пока без запроса
        ])
    except Exception as e:
        logger.warning(f"⚠️ Ошибка записи пользователя: {e}")

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    if message.text == "🔎 Поиск":
        bot.send_message(message.chat.id, "🔍 Введите название розы")
        return
    elif message.text == "📞 Связаться":
        bot.send_message(message.chat.id, "💬 Напишите нам: @your_username")
        return
    elif message.text == "📦 Заказать":
        bot.send_message(message.chat.id, "🛒 Напишите, какие сорта вас интересуют")
        return

    # Сохраняем историю запросов
    try:
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name or "",
            message.from_user.username or "",
            time.strftime("%Y-%m-%d %H:%M:%S"),
            message.text
        ])
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при записи запроса: {e}")

    # Поиск роз
    query = message.text.strip().lower()
    matches = [r for r in cached_roses if query in r.get('Название', '').strip().lower()]

    if not matches:
        bot.send_message(message.chat.id, "❌ Розы не найдены.")
        return

    for rose in matches[:5]:
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"{rose.get('Описание', '')}\n"
            f"Цена: {rose.get('price', '?')}"
        )
        photo_url = rose.get('photo', 'https://example.com/default.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{rose.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{rose.get('Название')}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

# Callback: Уход и История
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_details(call):
    action, name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if name.lower() in r.get('Название', '').lower()), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    if action == "care":
        bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
    else:
        bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
    bot.answer_callback_query(call.id)

# Запуск
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
