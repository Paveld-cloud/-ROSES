import os
import time
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread

# ================== Настройки ==================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# =============== Логирование ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============== Инициализация бота ===============
bot = telebot.TeleBot(BOT_TOKEN)

# =============== Авторизация Google Sheets ===============
try:
    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly "]
    )
    gs = gspread.authorize(creds)
    sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
except Exception as e:
    logger.error(f"❌ Ошибка инициализации Google Sheets: {e}")
    raise

# =============== Кэширование данных ===============
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

# =============== Храним ID сообщений ===============
user_messages = {}

def delete_previous_messages(chat_id):
    if chat_id in user_messages:
        for msg_id in user_messages[chat_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
        user_messages[chat_id] = []
    else:
        user_messages[chat_id] = []  # Создаём запись для нового пользователя

# =============== Команды ===============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    delete_previous_messages(message.chat.id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔎 Поиск"), KeyboardButton("📚 Каталог"))
    markup.row(KeyboardButton("📦 Заказать"), KeyboardButton("❓ Помощь"))
    msg = bot.send_message(message.chat.id,
                           "🌸 <b>Добро пожаловать!</b>\n\nВыберите действие:",
                           parse_mode='HTML',
                           reply_markup=markup)
    user_messages[message.chat.id].append(msg.message_id)

# === ВСЕ ТВОИ СУЩЕСТВУЮЩИЕ HANDLER'Ы ===
# Вставь сюда свои функции: handle_search, callback_query_handler и т.д.

# =============== Webhook endpoint ===============
app = Flask(__name__)

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# =============== Установка Webhook ===============
@app.before_first_request
def set_bot_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        public_url = os.getenv("PUBLIC_URL") or f"https://{request.host}"
        webhook_url = f"{public_url}/telegram"
        bot.set_webhook(url=webhook_url)
        logger.info(f"🌐 Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Не удалось установить webhook: {e}")

# =============== Главная страница ===============
@app.route('/')
def index():
    return 'Telegram бот запущен!', 200

# =============== Запуск сервера ===============
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
