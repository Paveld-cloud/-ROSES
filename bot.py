import os
import telebot
import gspread
import urllib.parse
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime

# Загрузка переменных из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

# Инициализация Google Sheets
creds = Credentials.from_service_account_info(eval(GOOGLE_APPLICATION_CREDENTIALS_JSON))
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet = spreadsheet.worksheet("List1")
users_sheet = spreadsheet.worksheet("Пользователи")

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# === Кнопка старт ===
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔍 Поиск"), KeyboardButton("📞 Связаться"), KeyboardButton("📦 Заказать"))
    return markup

# === Сохранение пользователя и запросов ===
def save_user_info(message, query=None):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if query:
        users_sheet.append_row([user_id, first_name, username, date, query])
    else:
        users_sheet.append_row([user_id, first_name, username, date, ""])

# === Команда /start ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    save_user_info(message)
    bot.send_message(
        message.chat.id,
        "🔍 Введите название розы",
        reply_markup=get_main_menu()
    )

# === Обработка обычных сообщений ===
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.lower()
    if text == "🔍 поиск":
        bot.send_message(message.chat.id, "🔍 Введите название розы", reply_markup=get_main_menu())
        return
    elif text in ["📞 связаться", "📦 заказать"]:
        bot.send_message(message.chat.id, "⏳ Функция в разработке", reply_markup=get_main_menu())
        return

    # Поиск розы
    rows = sheet.get_all_records()
    found = None
    for row in rows:
        name = str(row.get('Название', '')).lower()
        if text in name:
            found = row
            break

    # Сохраняем запрос в таблицу
    save_user_info(message, query=text)

    if not found:
        bot.send_message(message.chat.id, "❌ Розы не найдены.", reply_markup=get_main_menu())
        return

    # Картинка
    photo = found.get('photo')
    # Подпись
    caption = (
        f"🌹 <b>{found.get('Название', 'Без названия')}</b>\n"
        f"{found.get('price', '')}"
    )

    # Inline-кнопки
    buttons = []
    if found.get("Уход"):
        buttons.append(InlineKeyboardButton("🪴 Уход", callback_data="care_" + urllib.parse.quote_plus(found['Название'])))
    if found.get("История"):
        buttons.append(InlineKeyboardButton("📜 История", callback_data="history_" + urllib.parse.quote_plus(found['Название'])))
    markup = InlineKeyboardMarkup()
    if buttons:
        markup.add(*buttons)

    # Отправка
    bot.send_photo(message.chat.id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)

# === Обработка inline-кнопок ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("care_") or call.data.startswith("history_"))
def handle_callback(call):
    data_type, encoded_name = call.data.split("_", 1)
    name = urllib.parse.unquote_plus(encoded_name)

    rows = sheet.get_all_records()
    for row in rows:
        if name.strip() == row.get("Название", "").strip():
            if data_type == "care":
                bot.send_message(call.message.chat.id, f"🪴 Уход за {name}:\n{row.get('Уход', 'Нет данных')}")
            elif data_type == "history":
                bot.send_message(call.message.chat.id, f"📜 История сорта {name}:\n{row.get('История', 'Нет данных')}")
            break

# === Webhook или polling ===
if __name__ == '__main__':
    bot.polling(none_stop=True)
