import os
import json
import logging
import datetime
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
import urllib.parse

# ========== Настройка логов ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== Переменные окружения ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# ========== Инициализация ==========
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")

# ========== Авторизация Google Sheets ==========
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# ========== Кэш ==========
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Кэш роз обновлен")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки роз: {e}")
        cached_roses = []

refresh_cached_roses()

# ========== Webhook ==========
try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook активен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Ошибка Webhook: {e}")

@app.route('/')
def index():
    return "Бот запущен!"

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ========== Вспомогательные ==========
def normalize(text):
    return text.replace('"', '').replace("«", "").replace("»", "").strip().lower()

def save_user(message, query=None):
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name,
            message.from_user.username or "",
            now,
            query or ""
        ])
    except Exception as e:
        logger.error(f"❌ Ошибка записи пользователя: {e}")

# ========== Команды ==========
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
    save_user(message)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def ask_for_search(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def ask_contact(message):
    bot.send_message(message.chat.id, "📬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def ask_order(message):
    bot.send_message(message.chat.id, "🛍 Напишите, какие сорта вас интересуют")

# ========== Обработка поиска ==========
@bot.message_handler(func=lambda m: m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def handle_search(message):
    query = normalize(message.text)
    save_user(message, query)

    results = []
    for rose in cached_roses:
        name = normalize(rose.get("Название", ""))
        if all(word in name for word in query.split()):
            results.append(rose)

    if not results:
        bot.send_message(message.chat.id, "❌ Розы не найдены.")
        return

    for rose in results:
        title = rose.get("Название", "Без названия")
        caption = f"🌹 <b>{title}</b>\n\n{rose.get('Описание', '')}\n\nЦена: {rose.get('price', '?')}"
        photo_url = rose.get("photo", "").split(",")[0].strip()

        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{urllib.parse.quote_plus(title)}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{urllib.parse.quote_plus(title)}")
        )

        if photo_url:
            bot.send_photo(message.chat.id, photo=photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
        else:
            bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)

# ========== Обработка кнопок ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_callback(call):
    action, raw_name = call.data.split("_", 1)
    name = urllib.parse.unquote_plus(raw_name)
    rose = next((r for r in cached_roses if normalize(name) == normalize(r.get("Название", ""))), None)

    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    field = "Уход" if action == "care" else "История"
    text = rose.get(field, "Нет информации")
    prefix = "🪴 Уход:\n" if action == "care" else "📜 История:\n"
    bot.send_message(call.message.chat.id, prefix + text)
    bot.answer_callback_query(call.id)

# ========== Запуск ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
