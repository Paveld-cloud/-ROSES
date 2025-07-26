# bot.py
import os
import json
import logging
import telebot
from flask import Flask, request
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import urllib.parse

# ===== Настройки и логирование =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_env_var(name):
    value = os.getenv(name)
    if not value:
        logger.error(f"❌ Переменная окружения не найдена: {name}")
        raise RuntimeError(f"ОШИБКА: Не найдена переменная: {name}")
    return value

BOT_TOKEN = get_env_var("BOT_TOKEN")
SPREADSHEET_URL = get_env_var("SPREADSHEET_URL")
CREDS_JSON = json.loads(get_env_var("GOOGLE_APPLICATION_CREDENTIALS_JSON"))

bot = telebot.TeleBot(BOT_TOKEN)

# ===== Авторизация Google Sheets =====
# Исправлено: убран лишний пробел в scope
creds = Credentials.from_service_account_info(CREDS_JSON, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gs = gspread.authorize(creds)
spreadsheet = gs.open_by_url(SPREADSHEET_URL)
sheet_roses = spreadsheet.sheet1
sheet_users = spreadsheet.worksheet("Пользователи")
sheet_favorites = spreadsheet.worksheet("Избранное")

# ===== Кэш =====
cached_roses = []
user_search_results = {}
user_favorites = {}

def load_roses():
    global cached_roses
    try:
        cached_roses = sheet_roses.get_all_records()
        logger.info("✅ Розы загружены")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки роз: {e}")
        cached_roses = []

def load_favorites():
    try:
        all_rows = sheet_favorites.get_all_records()
        for row in all_rows:
            uid = int(row['ID'])
            rose = {
                "Название": row['Название'],
                "Описание": row['Описание'],
                "photo": row['photo'],
                "Уход": row['Уход'],
                "История": row['История']
            }
            user_favorites.setdefault(uid, []).append(rose)
        logger.info("✅ Избранное загружено")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки избранного: {e}")

load_roses()
load_favorites()

# ===== Flask и Webhook =====
app = Flask(__name__)
WEBHOOK_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/telegram"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

@app.route("/")
def home():
    return "Бот работает"

@app.route("/telegram", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ===== Команды =====
@bot.message_handler(commands=["start"])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться", "⭐ Избранное")
        bot.send_message(message.chat.id, "🌹 Добро пожаловать!\nВведите название розы для поиска.", reply_markup=markup)
    except Exception as e:
        logger.error(f"❌ Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте позже.")

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def prompt_search(message):
    try:
        bot.send_message(message.chat.id, "🔍 Введите название розы:")
    except Exception as e:
        logger.error(f"❌ Ошибка в prompt_search: {e}")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact(message):
    try:
        bot.send_message(message.chat.id, "📞 Напишите нам: @your_support")
    except Exception as e:
        logger.error(f"❌ Ошибка в contact: {e}")

@bot.message_handler(func=lambda m: m.text == "⭐ Избранное")
def show_favorites(message):
    try:
        user_id = message.from_user.id
        roses = user_favorites.get(user_id, [])
        if not roses:
            bot.send_message(message.chat.id, "💔 У вас нет избранных роз.")
            return
        for rose in roses:
            send_rose_card(message.chat.id, rose, from_favorites=True)
    except Exception as e:
        logger.error(f"❌ Ошибка в show_favorites: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке избранного.")

# ===== Поиск =====
@bot.message_handler(func=lambda m: True)
def handle_query(message):
    try:
        text = message.text.strip().lower()
        if not text or text.startswith("/"):
            return
        results = [r for r in cached_roses if text in r["Название"].lower()]
        if not results:
            bot.send_message(message.chat.id, "❌ Ничего не найдено.")
            return
        # Ограничиваем количество результатов для предотвращения переполнения памяти
        user_search_results[message.from_user.id] = results[:10]
        for idx, rose in enumerate(results[:5]):
            send_rose_card(message.chat.id, rose, message.from_user.id, idx)
            log_search(message, rose["Название"])
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_query: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при поиске.")

def send_rose_card(chat_id, rose, user_id=None, idx=None, from_favorites=False):
    try:
        caption = f"🌹 <b>{rose.get('Название')}</b>\nОписание: {rose.get('Описание')}"
        photo = rose.get("photo")
        markup = telebot.types.InlineKeyboardMarkup()
        if from_favorites:
            name_encoded = urllib.parse.quote_plus(rose.get("Название", ""))
            markup.row(
                telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"showcare_{name_encoded}"),
                telebot.types.InlineKeyboardButton("📜 История", callback_data=f"showhist_{name_encoded}")
            )
        else:
            markup.row(
                telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
                telebot.types.InlineKeyboardButton("📜 История", callback_data=f"hist_{user_id}_{idx}")
            )
            markup.add(
                telebot.types.InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{user_id}_{idx}")
            )
        if photo:
            # Проверяем, что photo - валидный URL
            if isinstance(photo, str) and (photo.startswith('http://') or photo.startswith('https://')):
                bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
            else:
                bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"❌ Ошибка в send_rose_card: {e}")
        try:
            bot.send_message(chat_id, "❌ Ошибка при отправке карточки розы.")
        except:
            pass

def log_search(message, rose_name):
    try:
        sheet_users.append_row([
            message.from_user.id,
            message.from_user.first_name,
            f"@{message.from_user.username}" if message.from_user.username else "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            rose_name
        ])
    except Exception as e:
        logger.warning(f"⚠️ Ошибка записи поиска: {e}")

# ===== Обработка колбэков =====
@bot.callback_query_handler(func=lambda c: c.data.startswith("care_") or c.data.startswith("hist_"))
def handle_info(call):
    try:
        _, uid, idx = call.data.split("_")
        user_results = user_search_results.get(int(uid), [])
        
        # Проверка на выход за границы массива
        if int(idx) >= len(user_results):
            bot.answer_callback_query(call.id, "❌ Данные устарели, попробуйте поиск заново.")
            return
            
        rose = user_results[int(idx)]
        if "care" in call.data:
            bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Нет данных')}")
        else:
            bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Нет данных')}")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_info: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при получении информации")
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("fav_"))
def handle_favorite(call):
    try:
        _, uid, idx = call.data.split("_")
        user_id = int(uid)
        user_results = user_search_results.get(user_id, [])
        
        # Проверка на выход за границы массива
        if int(idx) >= len(user_results):
            bot.answer_callback_query(call.id, "❌ Данные устарели, попробуйте поиск заново.")
            return
            
        rose = user_results[int(idx)]
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
                f"@{call.from_user.username}" if call.from_user.username else "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                rose["Название"],
                rose["Описание"],
                rose["photo"],
                rose["Уход"],
                rose["История"]
            ])
            bot.answer_callback_query(call.id, "✅ Добавлено в избранное")
        except Exception as e:
            logger.error(f"❌ Ошибка записи в избранное: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при сохранении")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_favorite: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при добавлении в избранное")
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("showcare_") or c.data.startswith("showhist_"))
def handle_fav_details(call):
    try:
        prefix, encoded_name = call.data.split("_", 1)
        name = urllib.parse.unquote_plus(encoded_name)
        uid = call.from_user.id
        roses = user_favorites.get(uid, [])
        for rose in roses:
            if rose["Название"] == name:
                field = "Уход" if prefix == "showcare" else "История"
                bot.send_message(call.message.chat.id, f"{'🪴' if field == 'Уход' else '📜'} {field}:\n{rose.get(field, 'Нет данных')}")
                return
        bot.answer_callback_query(call.id, "❌ Роза не найдена")
    except Exception as e:
        logger.error(f"❌ Ошибка при показе избранного: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при получении данных")
        except:
            pass

# ===== Очистка устаревших данных (опционально) =====
def cleanup_old_search_results():
    """Очистка старых результатов поиска для предотвращения переполнения памяти"""
    # Можно реализовать очистку по времени или по количеству записей
    pass

# ===== Запуск =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
