import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
import datetime
import urllib.parse

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация бота и таблицы
bot = telebot.TeleBot(BOT_TOKEN)

creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# Кэш
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Кэш роз обновлен")
    except Exception as e:
        logger.error(f"❌ Ошибка кэша: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask + Webhook
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")

try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook активен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Ошибка Webhook: {e}")

@app.route("/")
def index():
    return "OK"

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ===================== Вспомогательные ======================
def normalize(text):
    return str(text).replace('"', '').replace('«', '').replace('»', '').strip().lower()

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

# ======================= Обработчики ========================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.add("📦 Заказать")
    bot.send_message(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:", parse_mode="HTML", reply_markup=markup)
    save_user(message)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def ask_for_query(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы:")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact_info(message):
    bot.send_message(message.chat.id, "📬 Наш Telegram: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def ask_order(message):
    bot.send_message(message.chat.id, "🛍 Напишите, какие сорта вас интересуют")

# ==================== Поиск роз =====================
@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def search_rose(message):
    query = normalize(message.text)
    save_user(message, query)

    matches = [r for r in cached_roses if query in normalize(r.get('Название', ''))]

    if not matches:
        bot.send_message(message.chat.id, "❌ Розы не найдены.")
        return

    for rose in matches:
        name = rose.get("Название", "Без названия")
        description = rose.get("Описание", "")
        price = rose.get("price", "?")
        photo_url = rose.get("photo", "").strip()

        caption = f"🌹 <b>{name}</b>\n\n{description}\n\nЦена: {price}"
        markup = telebot.types.InlineKeyboardMarkup()
        encoded_name = urllib.parse.quote_plus(name)
        markup.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{encoded_name}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{encoded_name}")
        )

        if photo_url:
            bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=markup)

# ============ Обработка кнопок ===============
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_buttons(call):
    action, encoded_name = call.data.split("_", 1)
    decoded_name = urllib.parse.unquote_plus(encoded_name)

    rose = next((r for r in cached_roses if normalize(decoded_name) == normalize(r.get("Название", ""))), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    if action == "care":
        text = rose.get("Уход", "Нет информации")
        prefix = "🪴 Уход:\n"
    else:
        text = rose.get("История", "Нет информации")
        prefix = "📜 История:\n"

    bot.send_message(call.message.chat.id, prefix + text)
    bot.answer_callback_query(call.id)

# ============ Запуск вручную ============
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
