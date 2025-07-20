# bot.py
import os
import json
import logging
import telebot
from flask import Flask, request
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import threading

# ===== Настройки и логирование =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_env_var(name):
    value = os.getenv(name)
    if not value:
        logger.error(f"❌ Не найдена переменная окружения: {name}")
        raise RuntimeError(f"Не найдена переменная окружения: {name}")
    return value

try:
    BOT_TOKEN = get_env_var("BOT_TOKEN")
    SPREADSHEET_URL = get_env_var("SPREADSHEET_URL")
    CREDS_JSON = json.loads(get_env_var("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
except Exception as e:
    logger.critical(f"❌ Критическая ошибка инициализации: {e}")
    raise

bot = telebot.TeleBot(BOT_TOKEN)

# ===== Авторизация Google Sheets =====
gs = None
sheet_roses = None
sheet_users = None
sheet_favorites = None

try:
    creds = Credentials.from_service_account_info(
        CREDS_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets "]
    )
    gs = gspread.authorize(creds)
    spreadsheet = gs.open_by_url(SPREADSHEET_URL)
    sheet_roses = spreadsheet.sheet1
    sheet_users = spreadsheet.worksheet("Пользователи")
    sheet_favorites = spreadsheet.worksheet("Избранное")
    logger.info("✅ Авторизация Google Sheets прошла успешно")
except Exception as e:
    logger.critical(f"❌ Ошибка авторизации Google Sheets: {e}")
    raise

# ===== Кэш данных =====
cached_roses = []
user_search_results = {}  # user_id: [roses]
user_favorites = {}       # user_id: [roses]

def load_roses():
    global cached_roses
    try:
        cached_roses = sheet_roses.get_all_records()
        logger.info(f"✅ Загружено {len(cached_roses)} роз из таблицы")
    except Exception as e:
        logger.error(f"❌ Не удалось загрузить розы: {e}")
        cached_roses = []

def load_favorites():
    try:
        all_rows = sheet_favorites.get_all_records()
        for row in all_rows:
            user_id = int(row['ID'])
            rose = {
                'Название': row['Название'],
                'Описание': row['Описание'],
                'photo': row['photo'],
                'Уход': row['Уход'],
                'История': row['История']
            }
            if user_id not in user_favorites:
                user_favorites[user_id] = []
            user_favorites[user_id].append(rose)
        logger.info("✅ Избранное загружено")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки избранного: {e}")

load_roses()
load_favorites()

# ===== Очистка кэша поиска =====
def clear_search_cache():
    user_search_results.clear()
    threading.Timer(600, clear_search_cache).start()  # каждые 10 минут

clear_search_cache()

# ===== Flask Webhook =====
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "")

try:
    bot.remove_webhook()
    if WEBHOOK_URL:
        bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
        logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
except Exception as e:
    logger.error(f"❌ Webhook не установлен: {e}")

@app.route('/')
def home():
    return 'Bot is running'

@app.route('/telegram', methods=['POST'])
def telegram():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# ===== Основные команды =====
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск")
    markup.row("📞 Связаться", "⭐ Избранное")
    bot.send_message(message.chat.id, "🌹 Добро пожаловать! Напишите название розы.", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "🌹 <b>Помощь по боту</b>\n"
        "— Введите название розы для поиска.\n"
        "— Используйте кнопки для просмотра ухода, истории и добавления в избранное.\n"
        "— Кнопка ⭐ Избранное покажет ваши любимые розы.\n"
        "— Кнопка 📞 Связаться — для обратной связи.",
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def search_prompt(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "⭐ Избранное")
def favorites(message):
    show_favorites(message)

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact(message):
    bot.send_message(message.chat.id, "📞 Для связи напишите: @your_support_username")

@bot.message_handler(func=lambda m: True)
def search(message):
    if message.text.startswith('/'):
        return
    query = message.text.strip().lower()
    results = [r for r in cached_roses if query in r.get("Название", "").lower()]
    if not results:
        bot.send_message(message.chat.id, "❌ Ничего не найдено.")
        return
    user_search_results[message.from_user.id] = results
    for idx, rose in enumerate(results[:5]):
        send_rose_card(message.chat.id, rose, message.from_user.id, idx)
        log_found_rose(message, rose)

def send_rose_card(chat_id, rose, user_id, idx):
    caption = (
        f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
        f"Описание: {rose.get('Описание', '?')}"
    )
    photo_url = rose.get('photo', '')
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
        telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{user_id}_{idx}")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{user_id}_{idx}")
    )
    try:
        if photo_url:
            bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
        else:
            bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=keyboard)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки карточки розы: {e}")
        bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=keyboard)

def log_found_rose(message, rose):
    try:
        sheet_users.append_row([
            message.from_user.id,
            message.from_user.first_name,
            f"@{message.from_user.username}" if message.from_user.username else "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            rose.get("Название", "Неизвестно")
        ])
    except Exception as e:
        logger.warning(f"⚠️ Не удалось записать пользователя: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
def handle_details(call):
    try:
        action, user_id, idx = call.data.split("_")
        user_id = int(user_id)
        idx = int(idx)
        rose_list = user_search_results.get(user_id, [])
        if idx >= len(rose_list):
            bot.answer_callback_query(call.id, "❌ Роза не найдена")
            return
        rose = rose_list[idx]
        field = "Уход" if action == "care" else "История"
        text = rose.get(field, "Нет данных")
        bot.send_message(call.message.chat.id, f"{'🪴' if field == 'Уход' else '📜'} {field}:\n{text}")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_details: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки запроса")

@bot.callback_query_handler(func=lambda call: call.data.startswith("fav_"))
def add_favorite(call):
    try:
        _, user_id, idx = call.data.split("_")
        user_id = int(user_id)
        idx = int(idx)
        rose_list = user_search_results.get(user_id, [])
        if idx >= len(rose_list):
            bot.answer_callback_query(call.id, "❌ Роза не найдена")
            return
        rose = rose_list[idx]
        if user_id not in user_favorites:
            user_favorites[user_id] = []
        if any(r.get("Название") == rose.get("Название") for r in user_favorites[user_id]):
            bot.answer_callback_query(call.id, "⚠️ Уже в избранном")
            return
        user_favorites[user_id].append(rose)
        try:
            sheet_favorites.append_row([
                user_id,
                call.from_user.first_name,
                f"@{call.from_user.username}" if call.from_user.username else "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                rose.get("Название", ""),
                rose.get("Описание", ""),
                rose.get("photo", ""),
                rose.get("Уход", ""),
                rose.get("История", "")
            ])
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения избранного: {e}")
        bot.answer_callback_query(call.id, "✅ Добавлено в избранное")
    except Exception as e:
        logger.error(f"❌ Ошибка в add_favorite: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка добавления в избранное")

def show_favorites(message):
    user_id = message.from_user.id
    favs = user_favorites.get(user_id, [])
    if not favs:
        bot.send_message(message.chat.id, "💔 У вас нет избранных роз.")
        return
    bot.send_message(message.chat.id, "⭐ Ваши избранные розы:")
    for rose in favs:
        caption = f"🌹 <b>{rose.get('Название')}</b>\nОписание: {rose.get('Описание')}"
        photo_url = rose.get('photo', '')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"showcare_{rose.get('Название')}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"showhist_{rose.get('Название')}")
        )
        try:
            if photo_url:
                bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
            else:
                bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки избранного: {e}")
            bot.send_message(message.chat.id, caption, parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("showcare_") or call.data.startswith("showhist_"))
def handle_fav_details(call):
    try:
        prefix, name = call.data.split("_", 1)
        field = "Уход" if prefix == "showcare" else "История"
        user_id = call.from_user.id
        favs = user_favorites.get(user_id, [])
        for rose in favs:
            if rose.get("Название") == name:
                bot.send_message(call.message.chat.id, f"{'🪴' if field == 'Уход' else '📜'} {field}:\n{rose.get(field, 'Нет данных')}")
                return
        bot.answer_callback_query(call.id, "❌ Не найдено")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_fav_details: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки запроса")

# ===== Запуск Flask =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
    
