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

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
sheet_users = gs.open_by_url(SPREADSHEET_URL).worksheet("Пользователи")

# Кэш данных роз
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные роз загружены")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask-приложение и Webhook
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

# 📥 Логирование запросов пользователей
def log_user_query(message, query_text):
    try:
        sheet_users.append_row([
            message.from_user.id,
            message.from_user.first_name,
            f"@{message.from_user.username}" if message.from_user.username else "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            query_text
        ])
        logger.info(f"✅ Запрос пользователя сохранён: {query_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в Google Таблицу: {e}")

# Обработчики
def setup_handlers():

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        send_main_menu(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:")

    @bot.message_handler(commands=['menu'])
    def show_menu(message):
        send_main_menu(message.chat.id, "📋 Главное меню:")

    def send_main_menu(chat_id, text):
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться")
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

    @bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
    def handle_search_prompt(message):
        bot.send_message(message.chat.id, "🔍 Введите название розы")

    @bot.message_handler(func=lambda m: m.text == "📞 Связаться")
    def handle_contact(message):
        bot.reply_to(message, "💬 Напишите нам: @your_username")

    @bot.message_handler(func=lambda message: True)
    def handle_search_text(message):
        query = message.text.strip().lower()
        if query in ["меню", "начать", "/menu", "/start"]:
            send_main_menu(message.chat.id, "🔄 Меню восстановлено.")
            return

        # 💾 Сохраняем запрос пользователя
        log_user_query(message, query)

        results = [r for r in cached_roses if query in r.get('Название', '').lower()]
        if not results:
            bot.send_message(message.chat.id, "❌ Ничего не найдено.")
            return

        for idx, rose in enumerate(results[:5]):
            send_rose_card(message.chat.id, rose, idx)

    def send_rose_card(chat_id, rose, idx=0):
        description = ''
        for key in rose:
            if key.strip().lower() == 'описание':
                description = rose[key]
                break

        caption = (
    f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
    f"{rose.get('Описание', '')}\n"
    f"Описание: {rose.get('price', '?')}"
        )

        photo_url = rose.get('photo', 'https://example.com/default.jpg')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{idx}")
        )
        bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
    def handle_rose_details(call):
        try:
            action, idx = call.data.split("_")
            idx = int(idx)
            rose = cached_roses[idx]
            if action == "care":
                bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
            else:
                bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            bot.answer_callback_query(call.id, "Произошла ошибка")

setup_handlers()

# Запуск Flask
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)            
