# bot.py
import os
import json
import logging
import telebot
from flask import Flask, request, render_template, send_from_directory
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
app = Flask(__name__, 
           template_folder='templates',
           static_folder='static')

# URL для мини-приложения
WEB_APP_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/app"
WEBHOOK_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/telegram"

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ===== Маршруты для мини-приложения =====
@app.route("/")
def home():
    return "Бот работает"

@app.route("/app")
def web_app():
    """Главная страница мини-приложения"""
    return render_template('index.html')

@app.route("/app/roses")
def get_roses():
    """API endpoint для получения списка роз"""
    try:
        # Возвращаем список роз в формате JSON
        roses_data = []
        for rose in cached_roses:
            roses_data.append({
                'name': rose.get('Название', ''),
                'description': rose.get('Описание', ''),
                'photo': rose.get('photo', ''),
                'care': rose.get('Уход', ''),
                'history': rose.get('История', '')
            })
        return {'roses': roses_data}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route("/app/favorites/<int:user_id>")
def get_user_favorites(user_id):
    """API endpoint для получения избранных роз пользователя"""
    try:
        favorites = user_favorites.get(user_id, [])
        favorites_data = []
        for rose in favorites:
            favorites_data.append({
                'name': rose.get('Название', ''),
                'description': rose.get('Описание', ''),
                'photo': rose.get('photo', ''),
                'care': rose.get('Уход', ''),
                'history': rose.get('История', '')
            })
        return {'favorites': favorites_data}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route("/app/search")
def search_roses():
    """API endpoint для поиска роз"""
    query = request.args.get('q', '').lower()
    try:
        if not query:
            results = cached_roses[:20]  # Первые 20 роз
        else:
            results = [r for r in cached_roses if query in r["Название"].lower()][:20]
        
        results_data = []
        for rose in results:
            results_data.append({
                'name': rose.get('Название', ''),
                'description': rose.get('Описание', ''),
                'photo': rose.get('photo', ''),
                'care': rose.get('Уход', ''),
                'history': rose.get('История', '')
            })
        return {'results': results_data}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory('static', path)

@app.route("/telegram", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ===== Команды бота =====
@bot.message_handler(commands=["start"])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться", "⭐ Избранное")
        # Добавляем кнопку для мини-приложения
        web_app_btn = telebot.types.KeyboardButton("📱 Мини-приложение", web_app=telebot.types.WebAppInfo(WEB_APP_URL))
        markup.add(web_app_btn)
        
        bot.send_message(message.chat.id, 
                        "🌹 Добро пожаловать!\n"
                        "Выберите действие или откройте мини-приложение для расширенных возможностей.",
                        reply_markup=markup)
    except Exception as e:
        logger.error(f"❌ Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте позже.")

@bot.message_handler(commands=["app"])
def open_app(message):
    """Команда для открытия мини-приложения"""
    try:
        bot.send_message(message.chat.id, 
                        "📱 Открываю мини-приложение...",
                        reply_markup=telebot.types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                            telebot.types.KeyboardButton("📱 Открыть приложение", web_app=telebot.types.WebAppInfo(WEB_APP_URL))
                        ))
    except Exception as e:
        logger.error(f"❌ Ошибка в open_app: {e}")

# ===== Остальные функции (остаются без изменений) =====
# ... (все остальные функции как в предыдущей версии)

# ===== Функции для хэширования и удаления сообщений =====
def get_rose_hash(rose_name):
    hash_object = hashlib.md5(rose_name.encode())
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

# ===== Загрузка данных =====
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
# bot.py

import os
import json
import logging
import telebot
from flask import Flask, request, render_template, send_from_directory, jsonify
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
app = Flask(__name__, 
           template_folder='templates',
           static_folder='static')

# URL для мини-приложения
DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN')
if DOMAIN:
    WEB_APP_URL = f"https://{DOMAIN}/app"
    WEBHOOK_URL = f"https://{DOMAIN}/telegram"
else:
    WEB_APP_URL = "https://your-app-url.railway.app/app"
    WEBHOOK_URL = "https://your-app-url.railway.app/telegram"

try:
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
except Exception as e:
    logger.error(f"❌ Ошибка установки webhook: {e}")

# ===== Маршруты для мини-приложения =====
@app.route("/")
def home():
    return "Бот работает"

@app.route("/app")
def web_app():
    """Главная страница мини-приложения"""
    return render_template('index.html')

@app.route("/api/roses")
def get_roses():
    """API endpoint для получения списка роз"""
    try:
        # Получаем параметры поиска
        query = request.args.get('search', '').lower()
        
        # Фильтруем розы
        if query:
            filtered_roses = [r for r in cached_roses if query in r.get("Название", "").lower()]
        else:
            filtered_roses = cached_roses[:50]  # Ограничиваем для производительности
        
        # Преобразуем данные
        roses_data = []
        for rose in filtered_roses:
            roses_data.append({
                'id': hashlib.md5(rose.get('Название', '').encode()).hexdigest()[:10],
                'name': rose.get('Название', 'Без названия'),
                'description': rose.get('Описание', 'Нет описания')[:200] + '...' if len(rose.get('Описание', '')) > 200 else rose.get('Описание', 'Нет описания'),
                'photo': rose.get('photo', ''),
                'care': rose.get('Уход', 'Нет информации об уходе'),
                'history': rose.get('История', 'Нет исторической информации')
            })
        
        return jsonify({'roses': roses_data, 'count': len(roses_data)})
    except Exception as e:
        logger.error(f"❌ Ошибка API /api/roses: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/roses/<rose_id>")
def get_rose_detail(rose_id):
    """API endpoint для получения детальной информации о розе"""
    try:
        # Ищем розу по ID (в реальном приложении лучше использовать настоящий ID)
        for rose in cached_roses:
            if hashlib.md5(rose.get('Название', '').encode()).hexdigest()[:10] == rose_id:
                return jsonify({
                    'id': rose_id,
                    'name': rose.get('Название', 'Без названия'),
                    'description': rose.get('Описание', 'Нет описания'),
                    'photo': rose.get('photo', ''),
                    'care': rose.get('Уход', 'Нет информации об уходе'),
                    'history': rose.get('История', 'Нет исторической информации')
                })
        
        return jsonify({'error': 'Роза не найдена'}), 404
    except Exception as e:
        logger.error(f"❌ Ошибка API /api/roses/{rose_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/favorites/<int:user_id>")
def get_user_favorites(user_id):
    """API endpoint для получения избранных роз пользователя"""
    try:
        favorites = user_favorites.get(user_id, [])
        favorites_data = []
        for rose in favorites:
            favorites_data.append({
                'id': hashlib.md5(rose.get('Название', '').encode()).hexdigest()[:10],
                'name': rose.get('Название', 'Без названия'),
                'description': rose.get('Описание', 'Нет описания')[:200] + '...' if len(rose.get('Описание', '')) > 200 else rose.get('Описание', 'Нет описания'),
                'photo': rose.get('photo', ''),
                'care': rose.get('Уход', 'Нет информации об уходе'),
                'history': rose.get('История', 'Нет исторической информации')
            })
        return jsonify({'favorites': favorites_data, 'count': len(favorites_data)})
    except Exception as e:
        logger.error(f"❌ Ошибка API /api/favorites/{user_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory('static', path)

@app.route("/telegram", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ===== Команды бота =====
@bot.message_handler(commands=["start"])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться", "⭐ Избранное")
        # Добавляем кнопку для мини-приложения
        web_app_btn = telebot.types.KeyboardButton("📱 Мини-приложение", web_app=telebot.types.WebAppInfo(WEB_APP_URL))
        markup.add(web_app_btn)
        
        bot.send_message(message.chat.id, 
                        "🌹 Добро пожаловать в мир роз!\n"
                        "✨ Используйте мини-приложение для расширенных возможностей\n"
                        "🔍 Или продолжайте в обычном режиме",
                        reply_markup=markup)
    except Exception as e:
        logger.error(f"❌ Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте позже.")

@bot.message_handler(commands=["app"])
def open_app(message):
    """Команда для открытия мини-приложения"""
    try:
        web_app_btn = telebot.types.KeyboardButton("📱 Открыть приложение", web_app=telebot.types.WebAppInfo(WEB_APP_URL))
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True).add(web_app_btn)
        
        bot.send_message(message.chat.id, 
                        "📱 Нажмите кнопку ниже для открытия мини-приложения:",
                        reply_markup=markup)
    except Exception as e:
        logger.error(f"❌ Ошибка в open_app: {e}")

# ===== Остальные функции (остаются без изменений) =====
# ... (все остальные функции как в предыдущей версии)

# ===== Загрузка данных =====
load_roses()
load_favorites()

# ===== Запуск =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
load_roses()
load_favorites()

# ===== Запуск =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
