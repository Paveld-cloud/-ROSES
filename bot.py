# bot.py — Telegram бот для каталога роз с кнопками "Уход" и "История" + Поиск по названию

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
    "https://www.googleapis.com/auth/spreadsheets.readonly"])
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1  # лист с розами

def get_roses():
    return sheet.get_all_records()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "🌹 Добро пожаловать! Введите название розы или напишите /all для показа всех.")

@bot.message_handler(commands=['all'])
def show_all_roses(message):
    roses = get_roses()
    for rose in roses:
        send_rose_card(message.chat.id, rose)

@bot.message_handler(func=lambda m: True)
def search_rose(message):
    query = message.text.strip().lower()
    roses = get_roses()
    rose = next((r for r in roses if r['Название'].lower() == query), None)

    if not rose:
        bot.send_message(message.chat.id, "🚫 Роза не найдена.")
        return

    send_rose_card(message.chat.id, rose)

def send_rose_card(chat_id, rose):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🌿 Уход", callback_data=f"care_{rose['Название']}"),
        InlineKeyboardButton("📖 История", callback_data=f"history_{rose['Название']}")
    )
    caption = f"<b>{rose['Название']}</b>\n{rose.get('Описание', '')}\nЦена: {rose['Цена']}"
    bot.send_photo(
        chat_id,
        photo=rose['Фото'],
        caption=caption,
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    roses = get_roses()
    name = call.data.split('_')[1]
    rose = next((r for r in roses if r['Название'] == name), None)
    if not rose:
        bot.answer_callback_query(call.id, "Роза не найдена")
        return
    if call.data.startswith('care_'):
        bot.send_message(call.message.chat.id, f"🌿 Уход за {name}:\n{rose['Уход']}")
    elif call.data.startswith('history_'):
        bot.send_message(call.message.chat.id, f"📖 История розы {name}:\n{rose['История']}")

if __name__ == '__main__':
    bot.infinity_polling()
