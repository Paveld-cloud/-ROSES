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
import hashlib

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
user_last_info_messages = {}
rose_name_hashes = {}
user_search_result_messages = {}

# ===== Flask приложение =====
app = Flask(__name__)

# URL для webhook
WEBHOOK_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/telegram"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ===== Маршруты Flask =====
@app.route("/")
def home():
    return "Бот работает"

@app.route("/telegram", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ===== Функции для хэширования и удаления сообщений =====
def get_rose_hash(rose_name):
    hash_object = hashlib.md5(str(rose_name).encode())
    hash_hex = hash_object.hexdigest()[:10]
    rose_name_hashes[hash_hex] = rose_name
    return hash_hex

def get_rose_name_by_hash(hash_key):
    return rose_name_hashes.get(hash_key, "")

def delete_user_search_results(user_id, chat_id):
    if user_id in user_search_result_messages:
        for msg_id in user_search_result_messages[user_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка удаления сообщения поиска {msg_id}: {e}")
        del user_search_result_messages[user_id]
        logger.info(f"🗑️ Удалены все сообщения поиска для пользователя {user_id}")

def delete_previous_info_message(user_id, chat_id):
    if user_id in user_last_info_messages:
        try:
            msg_id = user_last_info_messages[user_id]
            bot.delete_message(chat_id, msg_id)
            del user_last_info_messages[user_id]
        except Exception as e:
            logger.warning(f"⚠️ Ошибка удаления сообщения: {e}")
            if user_id in user_last_info_messages:
                del user_last_info_messages[user_id]

# ===== Функции загрузки данных =====
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

# ===== Загрузка данных при запуске =====
load_roses()
load_favorites()

# ===== Команды бота =====
@bot.message_handler(commands=["start"])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться", "⭐ Избранное")
        
        bot.send_message(message.chat.id, 
                        "🌹 Добро пожаловать!\n"
                        "Введите название розы для поиска.",
                        reply_markup=markup)
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
        logger.info(f"📥 Пользователь {message.from_user.id} открыл избранное")
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Удаляем все сообщения с результатами поиска
        delete_user_search_results(user_id, chat_id)
        
        # Удаляем предыдущее информационное сообщение
        delete_previous_info_message(user_id, chat_id)
        
        roses = user_favorites.get(user_id, [])
        
        logger.info(f"📊 Найдено избранных роз для пользователя {user_id}: {len(roses)}")
        
        if not roses:
            bot.send_message(message.chat.id, "💔 У вас нет избранных роз.")
            return
            
        bot.send_message(message.chat.id, f"⭐ Ваши избранные розы ({len(roses)} шт.):")
        
        for i, rose in enumerate(roses):
            logger.info(f"📤 Отправка избранной розы {i+1}: {rose.get('Название', 'Без названия')}")
            send_rose_card(message.chat.id, rose, from_favorites=True)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в show_favorites для пользователя {message.from_user.id}: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке избранного.")

# ===== Поиск =====
@bot.message_handler(func=lambda m: True)
def handle_query(message):
    try:
        text = message.text.strip().lower()
        if not text or text.startswith("/"):
            return
        results = [r for r in cached_roses if text in str(r.get("Название", "")).lower()]
        if not results:
            bot.send_message(message.chat.id, "❌ Ничего не найдено.")
            return
            
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Ограничиваем количество результатов для предотвращения переполнения памяти
        user_search_results[user_id] = results[:10]
        
        # Создаем список для хранения ID сообщений поиска
        if user_id not in user_search_result_messages:
            user_search_result_messages[user_id] = []
        
        # Отправляем сообщение с количеством найденных результатов
        result_msg = bot.send_message(chat_id, f"🔍 Найдено результатов: {len(results[:5])}")
        user_search_result_messages[user_id].append(result_msg.message_id)
        
        for idx, rose in enumerate(results[:5]):
            msg_id = send_rose_card(message.chat.id, rose, message.from_user.id, idx)
            if msg_id:
                user_search_result_messages[user_id].append(msg_id)
                
        log_search(message, results[0]["Название"])
        
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_query: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при поиске.")

def send_rose_card(chat_id, rose, user_id=None, idx=None, from_favorites=False):
    try:
        logger.info(f"📤 Отправка карточки розы: {rose.get('Название', 'Без названия')}")
        
        caption = f"🌹 <b>{str(rose.get('Название', 'Без названия')).strip()}</b>\nОписание: {rose.get('Описание', 'Нет описания')}"
        photo = rose.get("photo")
        markup = telebot.types.InlineKeyboardMarkup()
        
        if from_favorites:
            # Используем хэш вместо полного названия для избежания превышения лимита
            rose_hash = get_rose_hash(rose.get("Название", ""))
            markup.row(
                telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"showcare_{rose_hash}"),
                telebot.types.InlineKeyboardButton("📜 История", callback_data=f"showhist_{rose_hash}")
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
                logger.info(f"📷 Отправка фото: {photo}")
                msg = bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
                return msg.message_id
            else:
                logger.warning(f"⚠️ Невалидный URL фото: {photo}")
                msg = bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
                return msg.message_id
        else:
            logger.info("📝 Отправка без фото")
            msg = bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
            return msg.message_id
            
    except Exception as e:
        logger.error(f"❌ Ошибка в send_rose_card: {e}")
        logger.error(f"❌ Данные розы: {rose}")
        try:
            error_msg = bot.send_message(chat_id, "❌ Ошибка при отправке карточки розы.")
            return error_msg.message_id
        except:
            return None

def log_search(message, rose_name):
    try:
        sheet_users.append_row([
            message.from_user.id,
            message.from_user.first_name,
            f"@{message.from_user.username}" if message.from_user.username else "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            str(rose_name).strip()
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
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        
        # Удаляем предыдущее информационное сообщение
        delete_previous_info_message(user_id, chat_id)
        
        # Отправляем новое сообщение и сохраняем его ID
        if "care" in call.
            info_text = f"🪴 Уход:\n{rose.get('Уход', 'Нет данных')}"
        else:
            info_text = f"📜 История:\n{rose.get('История', 'Нет данных')}"
            
        info_message = bot.send_message(chat_id, info_text)
        user_last_info_messages[user_id] = info_message.message_id
        
        bot.answer_callback_query(call.id, "✅ Информация загружена")
        
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
        if any(str(r.get("Название")).strip() == str(rose.get("Название")).strip() for r in user_favorites[user_id]):
            bot.answer_callback_query(call.id, "⚠️ Уже в избранном")
            return
        user_favorites[user_id].append(rose)
        try:
            sheet_favorites.append_row([
                user_id,
                call.from_user.first_name,
                f"@{call.from_user.username}" if call.from_user.username else "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                str(rose.get("Название", "")).strip(),
                str(rose.get("Описание", "")).strip(),
                str(rose.get("photo", "")).strip(),
                str(rose.get("Уход", "")).strip(),
                str(rose.get("История", "")).strip()
            ])
            bot.answer_callback_query(call.id, "✅ Добавлено в избранное")
            # Обновляем кэш избранного
            load_favorites()
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
        prefix, rose_hash = call.data.split("_", 1)
        rose_name = get_rose_name_by_hash(rose_hash)
        uid = call.from_user.id
        chat_id = call.message.chat.id
        roses = user_favorites.get(uid, [])
        
        logger.info(f"📥 Запрос деталей избранного от пользователя {uid}, роза hash: {rose_hash}")
        
        # Удаляем предыдущее информационное сообщение
        delete_previous_info_message(uid, chat_id)
        
        found = False
        for rose in roses:
            if str(rose.get("Название")).strip() == str(rose_name).strip():
                field = "Уход" if prefix == "showcare" else "История"
                info_text = f"{'🪴' if field == 'Уход' else '📜'} {field}:\n{rose.get(field, 'Нет данных')}"
                
                # Отправляем новое сообщение и сохраняем его ID
                info_message = bot.send_message(chat_id, info_text)
                user_last_info_messages[uid] = info_message.message_id
                
                bot.answer_callback_query(call.id, "✅ Информация загружена")
                found = True
                break
                
        if not found:
            bot.answer_callback_query(call.id, "❌ Роза не найдена в избранном")
            logger.warning(f"⚠️ Роза с hash '{rose_hash}' не найдена в избранном пользователя {uid}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при показе избранного: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при получении данных")
        except:
            pass

# ===== Запуск =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
