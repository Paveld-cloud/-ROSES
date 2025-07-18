import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
import time
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация бота
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

# Кэш данных
cached_roses = []

def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные роз обновлены из таблицы.")
    except Exception as e:
        logger.error(f"❌ Ошибка обновления данных: {e}")
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

# Главная страница
@app.route('/')
def index():
    return "🤖 Бот запущен!"

# Обработка входящих запросов от Telegram
@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# Кнопки меню
def main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    return markup

# /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_data = [
        str(message.from_user.id),
        message.from_user.first_name,
        message.from_user.username or '',
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ''  # Пустой запрос при старте
    ]
    try:
        users_sheet.append_row(user_data)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось записать пользователя: {e}")
    
    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

# Обработка кнопок меню
@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.send_message(message.chat.id, "💬 Напишите нам: @your_username", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.send_message(message.chat.id, "🛒 Напишите, какие сорта вас интересуют", reply_markup=main_menu())

# Обработка поиска роз
@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = message.text.strip().lower()

    # Сохраняем поисковый запрос
    try:
        users_sheet.append_row([
            str(message.from_user.id),
            message.from_user.first_name,
            message.from_user.username or '',
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            query
        ])
    except Exception as e:
        logger.warning(f"⚠️ Ошибка записи запроса: {e}")
    
    found = None
    for rose in cached_roses:
        name = rose.get('Название', '').strip().lower()
        if query in name:
            found = rose
            break

    if found:
        photo_url = found.get('photo', 'https://example.com/default.jpg')
        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
            f"{found.get('Описание', '')}\n"
            f"Цена: {found.get('price', '?')}"
        )
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{found.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{found.get('Название')}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.", reply_markup=main_menu())

# Обработка нажатий "Уход" и "История"
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_details(call):
    action, rose_name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if rose_name.lower() in r.get('Название', '').lower()), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    if action == "care":
        bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
    elif action == "history":
        bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
    bot.answer_callback_query(call.id)

# Запуск для локальной отладки
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
