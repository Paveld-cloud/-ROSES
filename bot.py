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
    CREDS_JSON, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
cached_roses = sheet.get_all_records()
logger.info("✅ Данные успешно загружены из Google Таблицы")

# Flask-приложение
app = Flask(__name__)

WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")
bot.remove_webhook()
bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# Обработчики
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    
    with open("welcome.gif", "rb") as gif:  # Добавь свой файл в проект
        bot.send_animation(message.chat.id, gif)

    bot.send_message(
        message.chat.id,
        "🌹 <b>Добро пожаловать в мир роз!</b>\n\nВыберите действие ниже:",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.reply_to(message, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.reply_to(message, "📨 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.reply_to(message, "🛒 Укажите сорта роз и количество.")

@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = message.text.strip().lower()
    found = next((r for r in cached_roses if query in r.get('Название', '').lower()), None)
    if found:
        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
            f"{found.get('Описание', '')}\nЦена: {found.get('price', '?')}"
        )
        photos = [url.strip() for url in found.get('photo', '').split(',') if url.strip()]
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход 🌱", callback_data=f"care_{found.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История 🌸", callback_data=f"history_{found.get('Название')}")
        )

        if len(photos) > 1:
            media = [telebot.types.InputMediaPhoto(media=photo) for photo in photos]
            media[0].caption = caption
            media[0].parse_mode = 'HTML'
            bot.send_media_group(message.chat.id, media)
            bot.send_message(message.chat.id, "🔘 Подробнее:", reply_markup=keyboard)
        else:
            photo = photos[0] if photos else "https://example.com/default.jpg"
            bot.send_photo(message.chat.id, photo, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "🚫 Роза не найдена.")

@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_rose_details(call):
    action, rose_name = call.data.split("_", 1)
    rose = next((r for r in cached_roses if rose_name.lower() in r.get('Название', '').lower()), None)
    if not rose:
        bot.answer_callback_query(call.id, "🚫 Роза не найдена")
        return
    text = rose.get("Уход", "Нет данных") if action == "care" else rose.get("История", "Нет данных")
    title = "🪴 Уход:" if action == "care" else "📜 История:"
    bot.send_message(call.message.chat.id, f"{title}\n{text}")
    bot.answer_callback_query(call.id)

# Запуск
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
