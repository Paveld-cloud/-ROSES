import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
import datetime
import threading
import time
from fuzzywuzzy import fuzz  # Импортируем fuzzywuzzy для нечеткого поиска

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация Telegram-бота
bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация в Google Sheets
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# Кэш роз
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        required_columns = ['Название', 'Описание', 'price', 'photo', 'Уход', 'История']
        if cached_roses and not all(col in cached_roses[0] for col in required_columns):
            logger.error("❌ Неправильная структура таблицы, отсутствуют столбцы")
            cached_roses = []
        else:
            logger.info(f"✅ Кэш роз обновлен. Количество записей: {len(cached_roses)}")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке роз: {e}")
        cached_roses = []

# Периодическое обновление кэша каждые 5 минут
def periodic_refresh():
    while True:
        refresh_cached_roses()
        time.sleep(300)

threading.Thread(target=periodic_refresh, daemon=True).start()
refresh_cached_roses()

# Flask-приложение
app = Flask(__name__)
WEBHOOK_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"

try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook активен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Ошибка вебхука: {e}")

@app.route('/')
def index():
    return "Бот работает!"

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# --- Хелперы ---

def normalize(text):
    if not text:
        return ""
    return (
        text.replace('"', '')
            .replace("«", "")
            .replace("»", "")
            .replace("(", "")
            .replace(")", "")
            .replace('роза', '')
            .replace('  ', ' ')  # Удаление двойных пробелов
            .lower()
            .strip()
    )

def main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    return markup

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

# --- Обработчики ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=main_menu()
    )
    save_user(message)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.send_message(message.chat.id, "📬 Напишите нам: @your_username", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.send_message(message.chat.id, "🛍 Напишите, какие сорта вас интересуют", reply_markup=main_menu())

# --- Поиск роз с fuzzywuzzy ---
@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = normalize(message.text)
    logger.info(f"🔍 Поиск: '{query}' (оригинал: '{message.text}')")
    save_user(message, message.text)
    found = []
    
    for rose in cached_roses:
        rose_name = normalize(rose.get('Название', ''))
        logger.debug(f"Сравнение: '{query}' с '{rose_name}'")
        # Используем fuzzywuzzy для оценки схожести
        score = fuzz.partial_ratio(query, rose_name)
        if score > 80:  # Порог для совпадений (можно настроить)
            found.append((rose, score))
    
    if not found:
        logger.info(f"❌ Не найдено для запроса: '{query}'")
        bot.send_message(message.chat.id, "❌ Розы не найдены.", reply_markup=main_menu())
        return

    # Сортировка по релевантности
    found.sort(key=lambda x: x[1], reverse=True)
    
    for rose, score in found[:5]:  # Ограничение на 5 результатов
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"Релевантность: {score}%\n"
            f"{rose.get('Описание', '')}\n"
            f"Цена: {rose.get('price', '?')}"
        )
        photo_url = rose.get("photo", "").split(",")[0].strip()
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{rose.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{rose.get('Название')}")
        )
        if photo_url:
            try:
                bot.send_photo(message.chat.id, photo=photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
            except Exception as e:
                logger.error(f"❌ Ошибка отправки фото: {e}")
                bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)
        else:
            bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)

# --- Уход и История ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_details(call):
    action, name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if normalize(name) in normalize(r.get('Название', ''))), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    text = rose.get("Уход" if action == "care" else "История", "Нет информации")
    prefix = "🪴 Уход:\n" if action == "care" else "📜 История:\n"
    bot.send_message(call.message.chat.id, prefix + text, reply_markup=main_menu())
    bot.answer_callback_query(call.id)

# --- Flask run ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
