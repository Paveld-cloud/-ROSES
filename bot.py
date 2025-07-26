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

# ===== Функции форматирования =====
def format_characteristics(rose):
    """Форматирует характеристики розы в красивый список"""
    characteristics = []
    
    # Цвет
    if rose.get('Цвет'):
        characteristics.append(f"🎨 Цвет: {rose.get('Цвет')}")
    elif 'бел' in str(rose.get('Описание', '')).lower():
        characteristics.append("🎨 Цвет: Белый")
    elif 'красн' in str(rose.get('Описание', '')).lower():
        characteristics.append("🎨 Цвет: Красный")
    elif 'розов' in str(rose.get('Описание', '')).lower():
        characteristics.append("🎨 Цвет: Розовый")
    else:
        characteristics.append("🎨 Цвет: Разноцветная")
    
    # Размер
    if rose.get('Размер'):
        characteristics.append(f"📏 Высота: {rose.get('Размер')}")
    elif 'крупн' in str(rose.get('Описание', '')).lower():
        characteristics.append("📏 Высота: Крупная (60-90 см)")
    else:
        characteristics.append("📏 Высота: Средняя (40-60 см)")
    
    # Сезон цветения
    if rose.get('Сезон'):
        characteristics.append(f"🌸 Сезон: {rose.get('Сезон')}")
    else:
        characteristics.append("🌸 Сезон: Весна-Осень")
    
    # Аромат
    if rose.get('Аромат'):
        characteristics.append(f"👃 Аромат: {rose.get('Аромат')}")
    elif 'аромат' in str(rose.get('Описание', '')).lower():
        characteristics.append("👃 Аромат: Присутствует")
    else:
        characteristics.append("👃 Аромат: Отсутствует")
    
    return "\n".join(characteristics)

def get_fragrance_level(rose):
    """Определяет уровень аромата"""
    description = str(rose.get('Описание', '')).lower()
    if 'сильн' in description or 'насыщенн' in description:
        return "Сильный 🌟🌟🌟"
    elif 'средн' in description:
        return "Средний 🌟🌟"
    elif 'слаб' in description:
        return "Слабый 🌟"
    else:
        return "Умеренный 🌟🌟"

def get_care_difficulty(care_text):
    """Определяет сложность ухода"""
    care_text = care_text.lower()
    if 'прост' in care_text or 'легк' in care_text:
        return "Легкая 🟢"
    elif 'средн' in care_text:
        return "Средняя 🟡"
    elif 'сложн' in care_text:
        return "Сложная 🔴"
    else:
        return "Средняя 🟡"

def send_care_info(chat_id, care_text, rose_name):
    """Отправляет информацию об уходе с улучшенным оформлением"""
    formatted_care = f"""
🪴 <b>Уход за розой "{rose_name}"</b>

{care_text}

🌡️ <b>Оптимальные условия:</b>
• Температура: +18...+25°C
• Освещение: Яркий свет, но без прямых солнечных лучей
• Влажность: Умеренная
    """
    
    # Ограничиваем длину до 4096 символов
    if len(formatted_care) > 4096:
        formatted_care = formatted_care[:4093] + "..."
    
    return bot.send_message(chat_id, formatted_care, parse_mode="HTML")

def send_history_info(chat_id, history_text, rose_name):
    """Отправляет историю сорта с улучшенным оформлением"""
    formatted_history = f"""
📜 <b>История сорта "{rose_name}"</b>

{history_text}
    """
    
    # Ограничиваем длину до 4096 символов
    if len(formatted_history) > 4096:
        formatted_history = formatted_history[:4093] + "..."
    
    return bot.send_message(chat_id, formatted_history, parse_mode="HTML")

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

def load_favorites():
    try:
        all_rows = sheet_favorites.get_all_records()
        logger.info(f"📊 Загружено строк избранного: {len(all_rows)}")
        
        # Очищаем старые данные
        user_favorites.clear()
        
        for row in all_rows:
            try:
                # Проверяем, что это не заголовок
                id_value = str(row.get('ID', '')).strip()
                if id_value.lower() in ['id', 'user_id', ''] or not id_value:
                    continue
                    
                uid = int(id_value)
                rose = {
                    "Название": str(row.get('Название', '')).strip() if row.get('Название') else 'Без названия',
                    "Описание": str(row.get('Описание', '')).strip() if row.get('Описание') else '',
                    "photo": str(row.get('photo', '')).strip() if row.get('photo') else '',
                    "Уход": str(row.get('Уход', '')).strip() if row.get('Уход') else '',
                    "История": str(row.get('История', '')).strip() if row.get('История') else ''
                }
                user_favorites.setdefault(uid, []).append(rose)
            except Exception as row_error:
                logger.warning(f"⚠️ Ошибка обработки строки избранного: {row_error}")
                continue
                
        logger.info("✅ Избранное загружено")
        logger.info(f"📊 Загружено избранных записей для пользователей: {list(user_favorites.keys())}")
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
                        "🌹 <b>Добро пожаловать в мир роз!</b>\n\n"
                        "✨ Используйте кнопки для навигации\n"
                        "🔍 Найдите свою идеальную розу\n"
                        "⭐ Сохраните любимые сорта",
                        reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка в start: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка. Попробуйте позже.")

@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def prompt_search(message):
    try:
        bot.send_message(message.chat.id, "🔍 <b>Введите название розы:</b>\n\n<i>Например: Аваланж, Ред, Пинк</i>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка в prompt_search: {e}")

@bot.message_handler(func=lambda m: m.text == "📞 Связаться")
def contact(message):
    try:
        contact_text = """
📞 <b>Связаться с нами:</b>

📧 Email: your-email@example.com
📱 Telegram: @your_support
🌐 Сайт: your-website.com

⏰ <b>Время работы:</b>
Пн-Пт: 9:00 - 18:00
Сб-Вс: 10:00 - 16:00
        """
        bot.send_message(message.chat.id, contact_text, parse_mode="HTML")
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
            bot.send_message(message.chat.id, "💔 <b>У вас нет избранных роз.</b>\n\n💡 Попробуйте найти и добавить розы в избранное!", parse_mode="HTML")
            return
            
        bot.send_message(message.chat.id, f"⭐ <b>Ваши избранные розы</b> ({len(roses)} шт.):", parse_mode="HTML")
        
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
            bot.send_message(message.chat.id, "❌ <b>Ничего не найдено.</b>\n\n💡 Попробуйте ввести другое название розы.", parse_mode="HTML")
            return
            
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Ограничиваем количество результатов для предотвращения переполнения памяти
        user_search_results[user_id] = results[:10]
        
        # Создаем список для хранения ID сообщений поиска
        if user_id not in user_search_result_messages:
            user_search_result_messages[user_id] = []
        
        # Отправляем сообщение с количеством найденных результатов
        result_msg = bot.send_message(chat_id, f"🔍 <b>Найдено результатов:</b> {len(results[:5])}", parse_mode="HTML")
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
        
        # Улучшенное форматирование карточки розы
        name = str(rose.get('Название', 'Без названия')).strip()
        description = str(rose.get('Описание', 'Нет описания')).strip()
        care = str(rose.get('Уход', 'Нет информации об уходе')).strip()
        history = str(rose.get('История', 'Нет исторической информации')).strip()
        photo = rose.get("photo")
        
        # Создаем красивое форматирование
        caption = f"""
🌺 <b>{name}</b>

📝 <b>Описание:</b>
{description}

📏 <b>Характеристики:</b>
{format_characteristics(rose)}

🌟 <b>Особенности:</b>
• Цветение: Круглый год
• Морозостойкость: Высокая
• Аромат: {get_fragrance_level(rose)}
• Сложность ухода: {get_care_difficulty(care)}

💡 <i>Нажмите кнопки ниже для подробной информации</i>
        """
        
        # Ограничиваем длину caption до 1024 символов (лимит Telegram)
        if len(caption) > 1024:
            caption = caption[:1021] + "..."
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        if from_favorites:
            # Используем хэш вместо полного названия для избежания превышения лимита
            rose_hash = get_rose_hash(rose.get("Название", ""))
            markup.row(
                telebot.types.InlineKeyboardButton("🪴 Уход и советы", callback_data=f"showcare_{rose_hash}"),
                telebot.types.InlineKeyboardButton("📜 История сорта", callback_data=f"showhist_{rose_hash}")
            )
        else:
            markup.row(
                telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{user_id}_{idx}"),
                telebot.types.InlineKeyboardButton("📜 История", callback_data=f"hist_{user_id}_{idx}")
            )
            markup.add(
                telebot.types.InlineKeyboardButton("⭐ Добавить в избранное", callback_data=f"fav_{user_id}_{idx}")
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
        if "care" in call.data:
            info_message = send_care_info(chat_id, rose.get('Уход', 'Нет данных'), rose.get('Название', 'Без названия'))
        else:
            info_message = send_history_info(chat_id, rose.get('История', 'Нет данных'), rose.get('Название', 'Без названия'))
            
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
                if field == "Уход":
                    info_message = send_care_info(chat_id, rose.get(field, 'Нет данных'), rose_name)
                else:
                    info_message = send_history_info(chat_id, rose.get(field, 'Нет данных'), rose_name)
                
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
