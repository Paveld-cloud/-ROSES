import os
import json
import logging
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

# Инициализация Telegram-бота
bot = telebot.TeleBot(BOT_TOKEN)

# Авторизация Google Sheets (если настроено)
gs = None
sheet = None
sheet_users = None
if SPREADSHEET_URL and CREDS_JSON:
    try:
        creds = Credentials.from_service_account_info(
            CREDS_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets "]
        )
        gs = gspread.authorize(creds)
        sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
        sheet_users = gs.open_by_url(SPREADSHEET_URL).worksheet("Пользователи")
        logger.info("✅ Google Sheets авторизован")
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets не настроен: {e}")
else:
    logger.warning("⚠️ Google Sheets не настроена — отключена запись в таблицу")

# Кэш данных роз и пользовательские данные
cached_roses = []
user_search_results = {}  # {user_id: [results]}
user_favorites = {}       # {user_id: [roses]}

# Хранение статистики поиска роз
rose_search_stats = {}  # {название_розы: количество_поисков}

def refresh_cached_roses():
    global cached_roses
    try:
        if sheet:
            cached_roses = sheet.get_all_records()
            logger.info("✅ Данные роз загружены из Google Таблицы")
        else:
            cached_roses = []
            logger.warning("⚠️ Google Таблица не настроена — данные роз не загружены")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки данных: {e}")
        cached_roses = []

refresh_cached_roses()

# Flask и Webhook
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
def index():
    return 'Бот работает!'

@app.route('/telegram', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

# 📥 Новый логгер для реальных результатов поиска
def log_found_rose(message, rose_name):
    try:
        if sheet_users:
            sheet_users.append_row([
                message.from_user.id,
                message.from_user.first_name,
                f"@{message.from_user.username}" if message.from_user.username else "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                rose_name
            ])
            logger.info(f"✅ Сохранён найденный сорт: {rose_name}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи розы в Google Таблицу: {e}")

# Обработчики
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск")
    markup.row("📞 Связаться", "⭐ Избранное")
    bot.send_message(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nНажмите кнопку \"Поиск\" и введите название розы.", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search_prompt(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: True)
def handle_search_text(message):
    query = message.text.strip().lower()
    results = [r for r in cached_roses if query in r.get('Название', '').lower()]

    if not results:
        bot.send_message(message.chat.id, "❌ Ничего не найдено.")
        return

    user_search_results[message.from_user.id] = results

    for idx, rose in enumerate(results[:5]):
        send_rose_card(message.chat.id, rose, message.from_user.id, idx)
        log_found_rose(message, rose.get("Название", "Неизвестно"))

# Отправка карточки розы
def send_rose_card(chat_id, rose, user_id, idx):
    caption = f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\nОписание: {rose.get('Описание', '?')}"
    photo_url = rose.get('photo', 'https://example.com/default.jpg ')
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
        telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{user_id}_{idx}")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("⭐ Добавить в избранное", callback_data=f"favorite_{user_id}_{idx}")
    )
    bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

# Добавление в избранное
@bot.callback_query_handler(func=lambda call: call.data.startswith("favorite_"))
def handle_add_to_favorites(call):
    try:
        _, user_id, idx = call.data.split("_")
        user_id = int(user_id)
        idx = int(idx)

        results = user_search_results.get(user_id, [])
        if not results or idx >= len(results):
            bot.answer_callback_query(call.id, "❌ Роза не найдена")
            return

        selected_rose = results[idx]

        if user_id not in user_favorites:
            user_favorites[user_id] = []

        if any(r.get('Название') == selected_rose.get('Название') for r in user_favorites[user_id]):
            bot.answer_callback_query(call.id, "⚠️ Уже в избранном")
        else:
            user_favorites[user_id].append(selected_rose)
            bot.answer_callback_query(call.id, "✅ Добавлено в избранное")
            save_favorite_to_sheet(user_id, call.from_user, selected_rose)

    except Exception as e:
        logger.error(f"❌ Ошибка добавления в избранное: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

def save_favorite_to_sheet(user_id, user, rose):
    try:
        first_name = user.first_name
        username = f"@{user.username}" if user.username else ""
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        favorite_name = rose.get("Название", "Без названия")

        sheet_favorites = gs.open_by_url(SPREADSHEET_URL).worksheet("Избранное")
        sheet_favorites.append_row([
            user_id,
            first_name,
            username,
            date,
            favorite_name
        ])
        logger.info(f"✅ Добавлено в избранное: {favorite_name} (ID: {user_id})")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в Google Таблицу: {e}")

# Просмотр избранного
@bot.message_handler(func=lambda m: m.text == "⭐ Избранное")
def handle_favorites(message):
    show_favorites(message)

@bot.message_handler(commands=['favorites'])
def handle_favorites_command(message):
    show_favorites(message)

def show_favorites(message):
    user_id = message.from_user.id
    favorites = user_favorites.get(user_id, [])

    if not favorites:
        bot.send_message(message.chat.id, "💔 У вас пока нет избранных роз.")
        return

    bot.send_message(message.chat.id, "⭐ Ваши избранные розы:")

    for idx, rose in enumerate(favorites):
        caption = f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\nОписание: {rose.get('Описание', '?')}"
        photo_url = rose.get('photo', 'https://example.com/default.jpg ')
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.row(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"fav_care_{idx}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"fav_history_{idx}")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("❌ Удалить из избранного", callback_data=f"delete_fav_{idx}")
        )
        bot.send_photo(message.chat.id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)

# Удаление из избранного
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_fav_"))
def handle_delete_favorite(call):
    try:
        _, idx = call.data.split("_")
        idx = int(idx)
        user_id = call.from_user.id

        favorites = user_favorites.get(user_id, [])

        if not favorites or idx >= len(favorites):
            bot.answer_callback_query(call.id, "❌ Роза не найдена")
            return

        removed_rose = favorites.pop(idx)
        bot.answer_callback_query(call.id, f"✅ Удалено: {removed_rose.get('Название', 'Без названия')}")

        delete_favorite_from_sheet(user_id, removed_rose.get('Название', ''))
        bot.send_message(call.message.chat.id, "🔄 Обновлённый список избранного:")
        show_favorites(call.message)

    except Exception as e:
        logger.error(f"❌ Ошибка удаления из избранного: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при удалении")

def delete_favorite_from_sheet(user_id, rose_name):
    try:
        sheet_favorites = gs.open_by_url(SPREADSHEET_URL).worksheet("Избранное")
        all_data = sheet_favorites.get_all_values()

        for row_idx, row in enumerate(all_data[1:], start=2):  # Пропускаем заголовок
            if str(user_id) == row[0].strip() and rose_name.strip() == row[4].strip():
                sheet_favorites.delete_rows(row_idx)
                logger.info(f"✅ Удалено из Google Таблицы: {rose_name} (ID: {user_id})")
                return
    except Exception as e:
        logger.error(f"❌ Ошибка удаления из Google Таблицы: {e}")

# Обработка деталей избранного
@bot.callback_query_handler(func=lambda call: call.data.startswith(("fav_care_", "fav_history_")))
def handle_favorite_details(call):
    try:
        action, idx = call.data.split("_")
        idx = int(idx)
        user_id = call.from_user.id

        favorites = user_favorites.get(user_id, [])
        if not favorites or idx >= len(favorites):
            bot.answer_callback_query(call.id, "❌ Роза не найдена")
            return

        rose = favorites[idx]
        if action == "fav_care":
            bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
        elif action == "fav_history":
            bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки избранного: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
