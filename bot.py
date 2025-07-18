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
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")
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

# Обработчики команд и callback'ов
def setup_handlers():
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
        bot.reply_to(message, "🔍 Введите название розы")

    @bot.message_handler(func=lambda m: m.text == "📞 Связаться")
    def handle_contact(message):
        bot.reply_to(message, "💬 Напишите нам: @your_username")

    @bot.message_handler(func=lambda m: m.text == "📦 Заказать")
    def handle_order(message):
        bot.reply_to(message, "🛒 Напишите, какие сорта вас интересуют")

    @bot.message_handler(func=lambda m: m.text == "📚 Каталог")
    def handle_catalog(message):
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            telebot.types.InlineKeyboardButton("Чайно-гибридные", callback_data="type_Чайно-гибридные"),
            telebot.types.InlineKeyboardButton("Плетистые", callback_data="type_Плетистые"),
            telebot.types.InlineKeyboardButton("Почвопокровные", callback_data="type_Почвопокровные"),
            telebot.types.InlineKeyboardButton("Флорибунда", callback_data="type_Флорибунда")
        )
        bot.send_message(message.chat.id, "📚 Выберите тип розы:", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("type_"))
    def handle_type(call):
        rose_type = call.data.replace("type_", "")
        roses = [r for r in cached_roses if r.get('Тип') == rose_type]
        if not roses:
            bot.answer_callback_query(call.id, "Нет роз этого типа")
            return

        for idx, rose in enumerate(roses[:5]):
            caption = (
                f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n\n"
                f"{rose.get('Описание', '')}\nЦена: {rose.get('price', '?')} руб"
            )
            photo_url = rose.get('photo', 'https://example.com/default.jpg')
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.add(
                telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx}_{rose_type}"),
                telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{idx}_{rose_type}")
            )
            bot.send_photo(call.message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
    def handle_rose_details(call):
        action, idx, rose_type = call.data.split("_")
        idx = int(idx)
        filtered_roses = [r for r in cached_roses if r.get('Тип') == rose_type]
        if idx >= len(filtered_roses):
            bot.answer_callback_query(call.id, "Роза не найдена")
            return
        rose = filtered_roses[idx]
        if action == "care":
            bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
        else:
            bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")

# Регистрируем обработчики
setup_handlers()

# Запуск под gunicorn, main блок для отладки
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
