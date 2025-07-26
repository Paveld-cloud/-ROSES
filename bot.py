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
import requests

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
    """Главная страница мини-приложения - только избранное"""
    return render_template('favorites.html')

@app.route("/app/roses")
def get_all_roses():
    """API endpoint для получения всех роз"""
    try:
        roses_data = []
        for rose in cached_roses:
            roses_data.append({
                'id': hashlib.md5(str(rose.get('Название', '')).encode()).hexdigest()[:10],
                'name': str(rose.get('Название', '')).strip(),
                'description': str(rose.get('Описание', '')).strip(),
                'photo': str(rose.get('photo', '')).strip(),
                'care': str(rose.get('Уход', '')).strip(),
                'history': str(rose.get('История', '')).strip()
            })
        return {'roses': roses_data, 'count': len(roses_data)}
    except Exception as e:
        logger.error(f"❌ Ошибка API /app/roses: {e}")
        return {'error': str(e)}, 500

@app.route("/app/favorites")
def get_user_favorites():
    """API endpoint для получения избранных роз пользователя"""
    try:
        chat_id = request.args.get('chat_id')
        if not chat_id:
            return {'error': 'Не передан chat_id'}, 400
            
        # Загружаем избранное из Google Sheets
        favorites_data = []
        try:
            all_rows = sheet_favorites.get_all_records()
            for row in all_rows:
                try:
                    id_value = str(row.get('ID', '')).strip()
                    if id_value.lower() in ['id', 'user_id', ''] or not id_value:
                        continue
                        
                    if int(id_value) == int(chat_id):
                        favorites_data.append({
                            'id': hashlib.md5(str(row.get('Название', '')).encode()).hexdigest()[:10],
                            'name': str(row.get('Название', '')).strip(),
                            'description': str(row.get('Описание', '')).strip(),
                            'photo': str(row.get('photo', '')).strip(),
                            'care': str(row.get('Уход', '')).strip(),
                            'history': str(row.get('История', '')).strip()
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки избранного: {e}")
            
        return {'favorites': favorites_data, 'count': len(favorites_data)}
    except Exception as e:
        logger.error(f"❌ Ошибка API /app/favorites: {e}")
        return {'error': str(e)}, 500

@app.route("/app/favorites/add", methods=['POST'])
def add_to_favorites():
    """API endpoint для добавления розы в избранное"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        rose_data = data.get('rose')
        
        if not chat_id or not rose_data:
            return {'error': 'Не переданы необходимые данные'}, 400
            
        # Добавляем в Google Sheets
        sheet_favorites.append_row([
            chat_id,
            data.get('first_name', ''),
            data.get('username', ''),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            str(rose_data.get('name', '')).strip(),
            str(rose_data.get('description', '')).strip(),
            str(rose_data.get('photo', '')).strip(),
            str(rose_data.get('care', '')).strip(),
            str(rose_data.get('history', '')).strip()
        ])
        
        return {'success': True, 'message': 'Добавлено в избранное'}
    except Exception as e:
        logger.error(f"❌ Ошибка API /app/favorites/add: {e}")
        return {'error': str(e)}, 500

@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory('static', path)

@app.route("/telegram", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "", 200

# ===== Функции загрузки данных =====
def load_roses():
    global cached_roses
    try:
        cached_roses = sheet_roses.get_all_records()
        logger.info("✅ Розы загружены")
        logger.info(f"📊 Загружено роз: {len(cached_roses)}")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки роз: {e}")
        cached_roses = []

# ===== Загрузка данных при запуске =====
load_roses()

# ===== Команды бота =====
@bot.message_handler(commands=["start"])
def start(message):
    try:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться")
        # Добавляем кнопку для мини-приложения
        web_app_btn = telebot.types.KeyboardButton("⭐ Избранное", web_app=telebot.types.WebAppInfo(f"{WEB_APP_URL}?chat_id={message.chat.id}"))
        markup.add(web_app_btn)
        
        bot.send_message(message.chat.id, 
                        "🌹 Добро пожаловать!\n"
                        "Используйте кнопки для навигации.",
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
        
        # Отправляем сообщение с количеством найденных результатов
        bot.send_message(chat_id, f"🔍 Найдено результатов: {len(results[:5])}")
        
        for idx, rose in enumerate(results[:5]):
            send_rose_card(message.chat.id, rose, message.from_user.id, idx)
                
        log_search(message, results[0]["Название"])
        
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_query: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при поиске.")

def send_rose_card(chat_id, rose, user_id=None, idx=None):
    try:
        logger.info(f"📤 Отправка карточки розы: {rose.get('Название', 'Без названия')}")
        
        caption = f"🌹 <b>{str(rose.get('Название', 'Без названия')).strip()}</b>\nОписание: {rose.get('Описание', 'Нет описания')}"
        photo = rose.get("photo")
        markup = telebot.types.InlineKeyboardMarkup()
        
        markup.row(
            telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
            telebot.types.InlineKeyboardButton("📜 История", callback_data=f"hist_{user_id}_{idx}")
        )
        
        # Добавляем кнопку "Добавить в избранное"
        markup.add(
            telebot.types.InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{chat_id}_{idx}")
        )
        
        if photo:
            # Проверяем, что photo - валидный URL
            if isinstance(photo, str) and (photo.startswith('http://') or photo.startswith('https://')):
                logger.info(f"📷 Отправка фото: {photo}")
                bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)
            else:
                logger.warning(f"⚠️ Невалидный URL фото: {photo}")
                bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
        else:
            logger.info("📝 Отправка без фото")
            bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в send_rose_card: {e}")
        logger.error(f"❌ Данные розы: {rose}")
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
        
        # Отправляем информацию
        if "care" in call.data:
            info_text = f"🪴 Уход:\n{rose.get('Уход', 'Нет данных')}"
        else:
            info_text = f"📜 История:\n{rose.get('История', 'Нет данных')}"
            
        bot.send_message(chat_id, info_text)
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
        chat_id = call.message.chat.id
        
        # Добавляем в избранное через API
        try:
            response = requests.post(
                f"https://{DOMAIN}/app/favorites/add",
                json={
                    'chat_id': chat_id,
                    'first_name': call.from_user.first_name,
                    'username': call.from_user.username,
                    'rose': {
                        'name': rose.get('Название', ''),
                        'description': rose.get('Описание', ''),
                        'photo': rose.get('photo', ''),
                        'care': rose.get('Уход', ''),
                        'history': rose.get('История', '')
                    }
                }
            )
            
            if response.status_code == 200:
                bot.answer_callback_query(call.id, "✅ Добавлено в избранное")
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при добавлении в избранное")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении в избранное: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при добавлении в избранное")
            
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_favorite: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка при добавлении в избранное")
        except:
            pass

# ===== Запуск =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host="0.0.0.0", port=port)
