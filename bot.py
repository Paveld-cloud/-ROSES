import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
logger.info("✅ Успешное подключение к Google Таблице")

# Кэш роз
cached_roses = []
def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные загружены из таблицы")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке данных: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask-приложение
app = Flask(__name__)

WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")
try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Ошибка при установке webhook: {e}")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# Меню
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

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛒 Напишите, какие сорта вас интересуют")

# Поиск розы по названию
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
        photos = str(found.get('photo', '')).split(',')
        media_group = []

        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
            f"{found.get('Описание', '')}\nЦена: {rose.get('price', '?')}"
        )

        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{found.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{found.get('Название')}")
        )

        if len(photos) > 1:
            for i, url in enumerate(photos):
                url = url.strip()
                if i == 0:
                    media_group.append(telebot.types.InputMediaPhoto(media=url, caption=caption, parse_mode='HTML'))
                else:
                    media_group.append(telebot.types.InputMediaPhoto(media=url))
            bot.send_media_group(message.chat.id, media_group)
            bot.send_message(message.chat.id, "👇 Выберите:", reply_markup=keyboard)
        else:
            bot.send_photo(message.chat.id, photos[0].strip(), caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "❌ Не найдено ни одной розы с таким названием.")

# Обработка кнопок "Уход" и "История"
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

# Запуск
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
