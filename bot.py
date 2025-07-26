# bot.py
import os
import json
import logging
from flask import Flask, request
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import telebot

# === Настройки и логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_env_var(name):
    value = os.getenv(name)
    if not value:
        logger.error(f"❌ Не найдена переменная окружения: {name}")
        raise RuntimeError(f"Не найдена переменная окружения: {name}")
    return value

BOT_TOKEN = get_env_var("BOT_TOKEN")
SPREADSHEET_URL = get_env_var("SPREADSHEET_URL")
CREDS_JSON = json.loads(get_env_var("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

bot = telebot.TeleBot(BOT_TOKEN)

# === Авторизация Google Sheets ===
creds = Credentials.from_service_account_info(
    CREDS_JSON, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet_roses = spreadsheet.sheet1
sheet_users = spreadsheet.worksheet("Пользователи")
sheet_favorites = spreadsheet.worksheet("Избранное")

# === Кэш и состояния ===
cached_roses = sheet_roses.get_all_records()
user_search_results = {}   # user_id: [roses]
user_message_ids = {}      # user_id: [msg_ids]
user_favorites = {}        # user_id: [roses]

# === Flask Webhook ===
app = Flask(__name__)
WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
bot.remove_webhook()
if WEBHOOK_URL:
    bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")

@app.route('/')
def home():
    return 'Bot is running'

@app.route('/telegram', methods=['POST'])
def telegram():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return '', 200

# === Команды ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔎 Поиск")
    markup.row("📞 Связаться", "⭐ Избранное")
    bot.send_message(message.chat.id, "🌹 Добро пожаловать! Напишите название розы.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def search_prompt(message):
    bot.send_message(message.chat.id, "🔍 Введите название розы")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact(message):
    bot.send_message(message.chat.id, "📞 Напишите @your_support_username")

@bot.message_handler(func=lambda m: m.text == "⭐ Избранное")
def show_favorites(message):
    user_id = message.from_user.id
    favs = user_favorites.get(user_id, [])
    if not favs:
        bot.send_message(message.chat.id, "💔 У вас нет избранных роз.")
        return
    for rose in favs:
        send_rose_card(message.chat.id, rose, user_id)

@bot.message_handler(func=lambda m: True)
def handle_search(message):
    query = message.text.strip().lower()
    if not query or query.startswith('/'):
        return
    user_id = message.from_user.id

    # Удаление предыдущих карточек
    for msg_id in user_message_ids.get(user_id, []):
        try:
            bot.delete_message(message.chat.id, msg_id)
        except:
            pass
    bot.send_animation(message.chat.id, "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMThjMGxvZXVrOTNwNmFiNzhvdm80N3k4Nm16ZGRqejFqaTIzNTRhaSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/MaJS1QwAKoBMQzr1CJ/giphy.gif")

    results = [r for r in cached_roses if query in r.get("Название", "").lower()]
    if not results:
        bot.send_message(message.chat.id, "❌ Ничего не найдено.")
        return

    user_search_results[user_id] = results
    user_message_ids[user_id] = []

    for idx, rose in enumerate(results[:5]):
        msg = send_rose_card(message.chat.id, rose, user_id, idx)
        if msg:
            user_message_ids[user_id].append(msg.message_id)
        log_rose(message, rose)

# === Карточка розы ===
def send_rose_card(chat_id, rose, user_id, idx=None):
    caption = f"🌹 <b>{rose.get('Название')}</b>\nОписание: {rose.get('Описание')}"
    photo = rose.get("photo", "")
    keyboard = telebot.types.InlineKeyboardMarkup()
    if idx is not None:
        keyboard.row(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"hist_{user_id}_{idx}")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{user_id}_{idx}")
        )
    try:
        if photo:
            return bot.send_photo(chat_id, photo, caption=caption, parse_mode='HTML', reply_markup=keyboard)
        else:
            return bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=keyboard)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки карточки: {e}")
        return None

def log_rose(message, rose):
    try:
        sheet_users.append_row([
            message.from_user.id,
            message.from_user.first_name,
            f"@{message.from_user.username or ''}",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            rose.get("Название", "")
        ])
    except Exception as e:
        logger.warning(f"⚠️ Не удалось записать лог: {e}")

# === Callback ===
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "hist_")))
def handle_info(call):
    action, user_id, idx = call.data.split("_")
    idx = int(idx)
    user_id = int(user_id)
    rose = user_search_results.get(user_id, [])[idx]
    field = "Уход" if action == "care" else "История"
    bot.send_message(call.message.chat.id, f"{'🪴' if field == 'Уход' else '📜'} {field}:\n{rose.get(field, 'Нет данных')}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("fav_"))
def add_to_favorites(call):
    _, user_id, idx = call.data.split("_")
    idx = int(idx)
    user_id = int(user_id)
    rose = user_search_results.get(user_id, [])[idx]
    if user_id not in user_favorites:
        user_favorites[user_id] = []
    if any(r["Название"] == rose["Название"] for r in user_favorites[user_id]):
        bot.answer_callback_query(call.id, "⚠️ Уже в избранном")
        return
    user_favorites[user_id].append(rose)
    try:
        sheet_favorites.append_row([
            user_id,
            call.from_user.first_name,
            f"@{call.from_user.username or ''}",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            rose.get("Название", ""),
            rose.get("Описание", ""),
            rose.get("photo", ""),
            rose.get("Уход", ""),
            rose.get("История", "")
        ])
    except Exception as e:
        logger.error(f"❌ Ошибка добавления в избранное: {e}")
    bot.answer_callback_query(call.id, "✅ Добавлено в избранное")

# === Запуск ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
