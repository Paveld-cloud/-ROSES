import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime

# ========== Логирование ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== Переменные окружения ==========
try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
    CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
except Exception as e:
    logger.error(f"❌ Ошибка загрузки переменных окружения: {e}")
    raise

# ========== Инициализация ==========
bot = telebot.TeleBot(BOT_TOKEN)
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.sheet1
users_sheet = spreadsheet.worksheet("Пользователи")

# ========== Кэш ==========
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

# ========== Flask ==========
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
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# ========== Вспомогательная функция ==========
def save_user_to_sheet(message):
    user_id = message.from_user.id
    name = message.from_user.first_name or ""
    username = message.from_user.username or ""
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    users_sheet.append_row([str(user_id), name, username, date, ""])

def save_query_to_sheet(user_id, query):
    try:
        records = users_sheet.get_all_records()
        for i, row in enumerate(records, start=2):  # с учётом заголовков
            if str(row.get("ID")) == str(user_id):
                old_query = row.get("Запрос", "")
                new_query = (old_query + ", " if old_query else "") + query
                users_sheet.update_cell(i, 5, new_query)
                break
    except Exception as e:
        logger.error(f"❌ Не удалось записать запрос: {e}")

# ========== Обработчики ==========
@bot.message_handler(commands=['start'])
def start_handler(message):
    save_user_to_sheet(message)
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
def search_handler(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact_handler(message):
    bot.reply_to(message, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def order_handler(message):
    bot.reply_to(message, "🛒 Напишите, какие сорта вас интересуют")

@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def query_handler(message):
    query = message.text.strip().lower()
    save_query_to_sheet(message.from_user.id, query)
    matches = [r for r in cached_roses if query in r.get('Название', '').lower()]

    if not matches:
        bot.send_message(message.chat.id, "😔 Не найдено ни одной розы с таким названием.")
        return

    for rose in matches[:5]:
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"{rose.get('Описание', '')}\n"
            f"Цена: {rose.get('price', '?')}"
        )
        photo_urls = rose.get('photo', '').split(',')  # Поддержка нескольких фото
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{rose.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{rose.get('Название')}")
        )
        media_group = []
        for i, url in enumerate(photo_urls[:5]):
            if i == 0:
                bot.send_photo(message.chat.id, url.strip(), caption=caption, parse_mode='HTML', reply_markup=keyboard)
            else:
                bot.send_photo(message.chat.id, url.strip())

@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def callback_handler(call):
    action, name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if name.lower() in r.get("Название", "").lower()), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    if action == "care":
        bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
    else:
        bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
    bot.answer_callback_query(call.id)

# ========== Local запуск ==========
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Flask запущен на порту {port}")
    app.run(host="0.0.0.0", port=port)

