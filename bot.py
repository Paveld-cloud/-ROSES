import os
import telebot
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация в Google Sheets
creds = Credentials.from_service_account_info(eval(creds_json), scopes=[
    "https://www.googleapis.com/auth/spreadsheets.readonly"
])
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1

def get_roses():
    return sheet.get_all_records()

# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🌸 Добро пожаловать! Введите название розы или слово 'все' для показа всех роз."
    )

# Обработка текстовых сообщений
@bot.message_handler(func=lambda m: True)
def search_rose(message):
    query = message.text.strip().lower()
    roses = get_roses()

    if query == "все":
        for rose in roses:
            send_rose_card(message.chat.id, rose)
        return

    rose = next((r for r in roses if r['Название'].lower() == query), None)
    if rose:
        send_rose_card(message.chat.id, rose)
    else:
        bot.send_message(message.chat.id, "❌ Роза не найдена. Попробуйте другое название.")

# Отправка карточки розы
def send_rose_card(chat_id, rose):
    caption = f"🌹 <b>{rose['Название']}</b>\n\n{rose['price']}"
    photo_url = rose['photo']
    bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML')

# Запуск бота
bot.infinity_polling()
