import os
import json
import telebot
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# Устанавливаем команды в меню Telegram
bot.set_my_commands([
    BotCommand("start", "🔁 Старт"),
    BotCommand("all", "Показать все розы"),
    BotCommand("clear", "Очистить чат")
])

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=[
    "https://www.googleapis.com/auth/spreadsheets.readonly"
])
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1

def get_roses():
    return sheet.get_all_records()

# Храним последние сообщения для очистки
user_messages = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔁 Старт"), KeyboardButton("🧹 Очистить чат"))
    bot.send_message(message.chat.id, "🌸 Добро пожаловать! Введите название розы или нажмите одну из кнопок.", reply_markup=markup)

@bot.message_handler(commands=['all'])
def show_all_roses(message):
    roses = get_roses()
    for idx, rose in enumerate(roses):
        send_rose_card(message.chat.id, rose, idx)

@bot.message_handler(func=lambda m: m.text == "🧹 Очистить чат")
def clear_user_chat(message):
    user_id = message.chat.id
    count = 0
    if user_id in user_messages:
        for msg_id in user_messages[user_id][-20:]:
            try:
                bot.delete_message(chat_id=user_id, message_id=msg_id)
                count += 1
            except Exception as e:
                print(f"Не удалось удалить сообщение {msg_id}: {e}")
        bot.send_message(user_id, f"🧹 Удалено {count} сообщений.", reply_markup=ReplyKeyboardRemove())
        user_messages[user_id] = []
    else:
        bot.send_message(user_id, "❌ Нет сообщений для очистки.")

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
    bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.")

def send_rose_card(chat_id, rose, rose_index):
    caption = f"🌹 <b>{rose['Название']}</b>\n\n{rose['price']}"
    photo_url = rose['photo']
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🪴 Уход", callback_data=f"care|{rose_index}"),
        InlineKeyboardButton("📜 История", callback_data=f"history|{rose_index}")
    )
    msg = bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
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

    if action == "care":
        msg = bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Нет информации')}")
    elif action == "history":
        msg = bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Нет информации')}")

    if call.message.chat.id in user_messages:
        user_messages[call.message.chat.id].append(msg.message_id)

bot.infinity_polling()
