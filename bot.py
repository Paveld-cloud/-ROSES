import os
import json
import logging
import telebot
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from functools import lru_cache
from time import sleep

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Константы
SPREADSHEET_COLUMNS = {
    'NAME': 'Название',
    'DESCRIPTION': 'Описание',
    'PRICE': 'Цена',
    'PHOTO': 'Фото',
    'CARE': 'Уход',
    'HISTORY': 'История'
}
ROSES_PER_PAGE = 5  # Количество роз на одной странице

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_FILE = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")

# Проверка переменных окружения
if not all([BOT_TOKEN, SPREADSHEET_URL, CREDS_FILE]):
    logger.error("Отсутствуют обязательные переменные окружения")
    raise ValueError("Необходимо задать BOT_TOKEN, SPREADSHEET_URL и GOOGLE_CREDS_FILE в .env")

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Настройка Google Sheets
try:
    creds = Credentials.from_service_account_file(
        CREDS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gs = gspread.authorize(creds)
    sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
except Exception as e:
    logger.error(f"Ошибка инициализации Google Sheets: {e}")
    raise

@lru_cache(maxsize=1)
def get_roses():
    """Получение и кэширование данных о розах из Google Sheets."""
    try:
        data = sheet.get_all_records()
        if not data:
            logger.warning("Таблица пуста")
            return []
        return data
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return []

def create_rose_card(rose):
    """Создание карточки розы с кнопками."""
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🌿 Уход", callback_data=f"care_{rose[SPREADSHEET_COLUMNS['NAME']]}"),
        InlineKeyboardButton("📖 История", callback_data=f"history_{rose[SPREADSHEET_COLUMNS['NAME']]}")
    )
    caption = (
        f"<b>{rose[SPREADSHEET_COLUMNS['NAME']]}</b>\n"
        f"{rose.get(SPREADSHEET_COLUMNS['DESCRIPTION'], '')}\n"
        f"Цена: {rose[SPREADSHEET_COLUMNS['PRICE']]}"
    )
    return caption, markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🌹 Добро пожаловать! Введите название розы для поиска или /all для списка всех роз."
    )

@bot.message_handler(commands=['all'])
def show_all_roses(message):
    roses = get_roses()
    if not roses:
        bot.send_message(message.chat.id, "🚫 Нет данных о розах.")
        return

    # Поддержка пагинации
    try:
        page = int(message.text.split()[1]) if len(message.text.split()) > 1 else 1
        total_pages = (len(roses) + ROSES_PER_PAGE - 1) // ROSES_PER_PAGE
        if page < 1 or page > total_pages:
            bot.send_message(message.chat.id, f"🚫 Неверная страница. Доступно: 1-{total_pages}")
            return
    except ValueError:
        page = 1

    start_idx = (page - 1) * ROSES_PER_PAGE
    end_idx = start_idx + ROSES_PER_PAGE

    for rose in roses[start_idx:end_idx]:
        try:
            caption, markup = create_rose_card(rose)
            bot.send_photo(
                message.chat.id,
                photo=rose[SPREADSHEET_COLUMNS['PHOTO']],
                caption=caption,
                parse_mode='HTML',
                reply_markup=markup
            )
            sleep(0.5)  # Защита от ограничений Telegram
        except Exception as e:
            logger.error(f"Ошибка отправки розы {rose[SPREADSHEET_COLUMNS['NAME']]}: {e}")
            bot.send_message(message.chat.id, f"Ошибка при отправке розы {rose[SPREADSHEET_COLUMNS['NAME']]}")

    if total_pages > 1:
        bot.send_message(
            message.chat.id,
            f"Страница {page} из {total_pages}. Для других страниц: /all <номер_страницы>"
        )

@bot.message_handler(func=lambda m: True)
def search_rose(message):
    query = message.text.strip().lower()
    roses = get_roses()
    if not roses:
        bot.send_message(message.chat.id, "🚫 Нет данных о розах.")
        return

    # Частичный поиск
    matches = [rose for rose in roses if query in rose[SPREADSHEET_COLUMNS['NAME']].lower()]
    if not matches:
        bot.send_message(message.chat.id, "🚫 Роза не найдена.")
        return

    for rose in matches[:ROSES_PER_PAGE]:
        try:
            caption, markup = create_rose_card(rose)
            bot.send_photo(
                message.chat.id,
                photo=rose[SPREADSHEET_COLUMNS['PHOTO']],
                caption=caption,
                parse_mode='HTML',
                reply_markup=markup
            )
            sleep(0.5)
        except Exception as e:
            logger.error(f"Ошибка отправки розы {rose[SPREADSHEET_COLUMNS['NAME']]}: {e}")
            bot.send_message(message.chat.id, f"Ошибка при отправке розы {rose[SPREADSHEET_COLUMNS['NAME']]}")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    roses = get_roses()
    if not roses:
        bot.answer_callback_query(call.id, "Нет данных о розах")
        return

    try:
        action, name = call.data.split('_', 1)
        rose = next((r for r in roses if r[SPREADSHEET_COLUMNS['NAME']] == name), None)
        if not rose:
            bot.answer_callback_query(call.id, "Роза не найдена")
            return

        if action == 'care':
            bot.send_message(
                call.message.chat.id,
                f"🌿 Уход за {name}:\n{rose[SPREADSHEET_COLUMNS['CARE']]}"
            )
            bot.answer_callback_query(call.id, "Информация об уходе отправлена")
        elif action == 'history':
            bot.send_message(
                call.message.chat.id,
                f"📖 История розы {name}:\n{rose[SPREADSHEET_COLUMNS['HISTORY']]}"
            )
            bot.answer_callback_query(call.id, "История розы отправлена")
    except Exception as e:
        logger.error(f"Ошибка обработки кнопки {call.data}: {e}")
        bot.answer_callback_query(call.id, "Произошла ошибка")

if __name__ == '__main__':
    logger.info("Запуск бота...")
    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            logger.error(f"Бот упал: {e}")
            sleep(5)  # Перезапуск через 5 секунд
