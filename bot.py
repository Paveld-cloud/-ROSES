import os
import json
import time
import logging
import telebot
import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request

# ================== Настройки ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
MAKE_COM_WEBHOOK_URL = os.getenv("MAKE_COM_WEBHOOK_URL")
AUTHORIZED_USERS = [123456789]
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")

# ================ Логирование ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============== Инициализация бота ===============
bot = telebot.TeleBot(BOT_TOKEN)

# =============== Авторизация Google Sheets ===============
creds = Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1

# =============== Кэширование данных ===============
cached_roses = []

def refresh_cached_roses():
    global cached_roses
    cached_roses = sheet.get_all_records()

refresh_cached_roses()

# =============== Храним ID сообщений ===============
user_messages = {}

def delete_previous_messages(chat_id):
    if chat_id in user_messages:
        for msg_id in user_messages[chat_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        user_messages[chat_id] = []
    else:
        user_messages[chat_id] = []

def send_typing_action(chat_id):
    try:
        bot.send_chat_action(chat_id, 'typing')
        time.sleep(0.8)
    except:
        pass

# =============== Команды ===============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    delete_previous_messages(message.chat.id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔎 Поиск"), KeyboardButton("📚 Каталог"))
    markup.row(KeyboardButton("📦 Заказать"), KeyboardButton("❓ Помощь"))
    msg = bot.send_message(message.chat.id, "🌸 <b>Добро пожаловать!</b>\n\nВыберите действие:",
                           parse_mode='HTML', reply_markup=markup)
    user_messages[message.chat.id].append(msg.message_id)

@bot.message_handler(commands=['refresh'])
def refresh_data(message):
    if message.from_user.id not in AUTHORIZED_USERS:
        bot.send_message(message.chat.id, "🚫 У вас нет доступа к этой команде.")
        return
    refresh_cached_roses()
    bot.send_message(message.chat.id, "🔄 Данные обновлены!")

# Другие хендлеры (поиск, каталог, callback, видео и т.д.) можно оставить как есть

# =============== Обработка текста ===============
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    if message.text in ["🔎 Поиск", "❓ Помощь", "📦 Заказать", "📚 Каталог"]:
        return
    delete_previous_messages(message.chat.id)
    send_typing_action(message.chat.id)
    query = message.text.strip().lower()
    found = False
    for idx, rose in enumerate(cached_roses):
        if query in rose.get('Название', '').lower():
            send_rose_card(message.chat.id, rose, idx)
            found = True
            break
    if not found:
        time.sleep(1)
        msg = bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.")
        user_messages[message.chat.id].append(msg.message_id)
    send_to_make_com(message)

def send_to_make_com(message):
    if not MAKE_COM_WEBHOOK_URL:
        return
    payload = {
        "chat_id": message.chat.id,
        "username": message.from_user.username or "no_username",
        "first_name": message.from_user.first_name or "Аноним",
        "text": message.text,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        requests.post(MAKE_COM_WEBHOOK_URL, json=payload)
    except:
        pass

def send_rose_card(chat_id, rose, idx):
    caption = f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n\n{rose.get('price', 'Цена не указана')}"
    photo_url = rose.get('photo', 'https://example.com/default.jpg ')
    send_typing_action(chat_id)
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx}_search"),
        InlineKeyboardButton("📜 История", callback_data=f"history_{idx}_search"),
        InlineKeyboardButton("📹 Видео", callback_data=f"video_{idx}_search"),
        InlineKeyboardButton("📦 Описание", callback_data=f"description_{idx}_search"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )
    msg = bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    user_messages[chat_id].append(msg.message_id)

# =============== Webhook с Flask ===============
app = Flask(__name__)

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return '', 200

@app.route('/', methods=['GET'])
def index():
    return 'Bot is running via webhook', 200

if __name__ == '__main__':
    bot.remove_webhook()
    full_webhook_url = f"{RAILWAY_PUBLIC_DOMAIN}/{BOT_TOKEN}"
    bot.set_webhook(url=full_webhook_url)
    logger.info(f"🌐 Webhook установлен: {full_webhook_url}")
    app.run(host='0.0.0.0', port=8080)

