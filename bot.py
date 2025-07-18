import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
creds = Credentials.from_service_account_info(
    CREDS_JSON,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
users_sheet = gs.worksheet("Пользователи")
cached_roses = []

def refresh_cached_roses():
    global cached_roses
    cached_roses = sheet.get_all_records()
refresh_cached_roses()

app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")

try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Не удалось установить webhook: {e}")

@app.route('/')
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# Главное меню
def send_main_menu(chat_id, text="🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:"):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск", "📞 Связаться")
    markup.row("📦 Заказать")
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

# Сохраняем пользователя
def save_user(user):
    try:
        user_id = str(user.id)
        if not any(row[0] == user_id for row in users_sheet.get_all_values()):
            users_sheet.append_row([user_id, user.first_name, user.username or "", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    except Exception as e:
        logger.warning(f"⚠️ Не удалось сохранить пользователя: {e}")

@bot.message_handler(commands=['start'])
def handle_start(message):
    save_user(message.from_user)
    send_main_menu(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def handle_contact(message):
    bot.send_message(message.chat.id, "💬 Напишите нам: @your_username")

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    bot.send_message(message.chat.id, "🛒 Напишите, какие сорта вас интересуют")

# Поиск по названию
@bot.message_handler(func=lambda m: m.text and m.text not in ["🔎 Поиск", "📞 Связаться", "📦 Заказать"])
def find_rose_by_name(message):
    query = message.text.strip().lower()
    found = next((r for r in cached_roses if query in r.get('Название', '').lower()), None)

    if found:
        caption = (
            f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
            f"{found.get('Описание', '')}\n"
            f"Цена: {found.get('price', '?')}"
        )
        photos = [url.strip() for url in found.get('photo', '').split(',') if url.strip()]
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{found.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{found.get('Название')}")
        )

        if len(photos) > 1:
            media = [telebot.types.InputMediaPhoto(media=url, caption=caption if i == 0 else None, parse_mode='HTML') for i, url in enumerate(photos)]
            bot.send_media_group(message.chat.id, media)
            bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)
        else:
            bot.send_photo(message.chat.id, photos[0] if photos else 'https://example.com/default.jpg', caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "😕 Не найдено ни одной розы с таким названием.")
    
    send_main_menu(message.chat.id)

# Callback для Ухода и Истории
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
    send_main_menu(call.message.chat.id)

# Запуск для отладки
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
