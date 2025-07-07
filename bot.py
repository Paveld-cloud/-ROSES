import os
import json
import time
import telebot
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=[
    "https://www.googleapis.com/auth/spreadsheets.readonly"
])
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1

def get_roses():
    return sheet.get_all_records()

# Храним ID сообщений
user_messages = {}

# Приветствие
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_chat_action(message.chat.id, 'typing')
    time.sleep(1.5)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔁 Старт"))
    bot.send_message(
        message.chat.id,
        "🌸 <b>Добро пожаловать!</b>\n\nВведите название розы для поиска.",
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🔁 Старт")
def handle_restart(message):
    send_welcome(message)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.chat.id
    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(message.message_id)
    search_rose(message)

def search_rose(message):
    query = message.text.strip().lower()
    roses = get_roses()
    for idx, rose in enumerate(roses):
        if query in rose['Название'].lower():
            send_rose_card(message.chat.id, rose, idx)
            return
    bot.send_chat_action(message.chat.id, 'typing')
    time.sleep(1)
    bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.")

def send_rose_card(chat_id, rose, rose_index):
    caption = f"🌹 <b>{rose['Название']}</b>\n\n{rose['Цена']}"
    photo_url = rose['Фото']
    bot.send_chat_action(chat_id, 'upload_photo')
    time.sleep(1)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📜 История", callback_data=f"history|{rose_index}"),
        InlineKeyboardButton("🪴 Уход", callback_data=f"care|{rose_index}"),
        InlineKeyboardButton("📹 Видео", callback_data=f"video|{rose_index}"),
        InlineKeyboardButton("📦 Описание", callback_data=f"description|{rose_index}")
    )

    msg = bot.send_photo(
        chat_id,
        photo_url,
        caption=caption,
        parse_mode='HTML',
        reply_markup=keyboard
    )

    if chat_id in user_messages:
        user_messages[chat_id].append(msg.message_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    action, idx = call.data.split('|', 1)
    roses = get_roses()
    try:
        rose = roses[int(idx)]
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    bot.send_chat_action(call.message.chat.id, 'typing')
    time.sleep(1)

    if action == "care":
        msg = bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Нет информации')}")
    elif action == "history":
        msg = bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Нет информации')}")
    elif action == "video":
        video_data = rose.get('Видео', '')
        if video_data.startswith("http"):
            msg = bot.send_message(call.message.chat.id, f"📹 Видео:\n{video_data}")
        elif len(video_data) > 10:  # file_id
            msg = bot.send_video(call.message.chat.id, video_data, caption="📹 Видео")
        else:
            msg = bot.send_message(call.message.chat.id, "📹 Видео не указано")
    elif action == "description":
        msg = bot.send_message(call.message.chat.id, f"📦 Описание:\n{rose.get('Описание', 'Нет описания')}")

    if call.message.chat.id in user_messages:
        user_messages[call.message.chat.id].append(msg.message_id)

# (Необязательно) получить file_id от загруженного видео
@bot.message_handler(content_types=['video'])
def get_file_id(message):
    bot.send_message(message.chat.id, f"🎥 File ID:\n{message.video.file_id}")

bot.infinity_polling()
