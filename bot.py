import os
import telebot
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets
creds = Credentials.from_service_account_info(eval(creds_json), scopes=[
    "https://www.googleapis.com/auth/spreadsheets.readonly"
])
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1  # лист с розами

def get_roses():
    return sheet.get_all_records()

# Обработка команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "🌹 Добро пожаловать! Введите название розы или напишите /all для показа всех.")

# Обработка команды /all
@bot.message_handler(commands=['all'])
def show_all_roses(message):
    roses = get_roses()
    for rose in roses:
        send_rose_card(message.chat.id, rose)

# Поиск по названию
@bot.message_handler(func=lambda m: True)
def search_rose(message):
    query = message.text.strip().lower()
    roses = get_roses()
    rose = next((r for r in roses if r['Название'].lower() == query), None)

    if rose:
        send_rose_card(message.chat.id, rose)
    else:
        bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.")

# Отправка карточки розы с кнопками
def send_rose_card(chat_id, rose):
    caption = f"🌹 <b>{rose['Название']}</b>\n\n{rose['price']}"
    photo_url = rose['photo']

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🪴 Уход", callback_data=f"care|{rose['Название']}"),
        InlineKeyboardButton("📜 История", callback_data=f"history|{rose['Название']}")
    )

    bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

# Обработка кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    roses = get_roses()
    rose = next((r for r in roses if r['Название'] == call.data.split('|')[1]), None)

    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    if call.data.startswith("care"):
        bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Нет информации')}")
    elif call.data.startswith("history"):
        bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Нет информации')}")

# Запуск бота
bot.infinity_polling()
