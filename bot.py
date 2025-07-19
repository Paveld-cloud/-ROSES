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
        # Авторизация Google Sheets
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

# Flask-приложение и Webhook
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

# 📥 Логирование запросов пользователей (только если настроено)
def log_user_query(message, query_text, found=False):
    try:
        if sheet_users and found:
            # Сохраняем название розы, а не входной запрос
            sheet_users.append_row([
                message.from_user.id,
                message.from_user.first_name,
                f"@{message.from_user.username}" if message.from_user.username else "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                query_text  # Здесь можно заменить на название розы, если нужно
            ])
            logger.info(f"✅ Запрос пользователя сохранён: {query_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в Google Таблицу: {e}")

# Обработчики
def setup_handlers():

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        send_main_menu(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:")

    @bot.message_handler(commands=['menu'])
    def show_menu(message):
        send_main_menu(message.chat.id, "📋 Главное меню:")

    def send_main_menu(chat_id, text):
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔎 Поиск")
        markup.row("📞 Связаться", "⭐ Избранное")
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

    @bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
    def handle_search_prompt(message):
        bot.send_message(message.chat.id, "🔍 Введите название розы")

    @bot.message_handler(func=lambda m: m.text == "📞 Связаться")
    def handle_contact(message):
        bot.reply_to(message, "💬 Напишите нам: @your_username")

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
            caption = (
                f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
                f"Описание: {rose.get('Описание', '?')}"
            )
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

    @bot.message_handler(func=lambda message: True)
    def handle_search_text(message):
        query = message.text.strip().lower()
        if query in ["меню", "начать", "/menu", "/start"]:
            send_main_menu(message.chat.id, "🔄 Меню восстановлено.")
            return

        # 💾 Сохраняем запрос пользователя
        log_user_query(message, query)  # Без сохранения в таблицу, только в логах

        results = [r for r in cached_roses if query in r.get('Название', '').lower()]
        if not results:
            bot.send_message(message.chat.id, "❌ Ничего не найдено.")
            return

        # Сохраняем в таблицу только успешные поиски
        log_user_query(message, query, found=True)

        # Увеличиваем статистику по найденным розам
        for rose in results:
            name = rose.get('Название', 'Без названия')
            if name in rose_search_stats:
                rose_search_stats[name] += 1
            else:
                rose_search_stats[name] = 1

        # Сохраняем результаты поиска для пользователя
        user_search_results[message.from_user.id] = results

        for idx, rose in enumerate(results[:5]):
            send_rose_card(message.chat.id, rose, message.from_user.id, idx)

    def send_rose_card(chat_id, rose, user_id, idx):
        caption = (
            f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n"
            f"Описание: {rose.get('Описание', '?')}"
        )

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

    @bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
    def handle_rose_details(call):
        try:
            action, user_id, idx = call.data.split("_")
            user_id = int(user_id)
            idx = int(idx)

            results = user_search_results.get(user_id, [])
            if not results or idx >= len(results):
                bot.answer_callback_query(call.id, "❌ Роза не найдена")
                return

            rose = results[idx]
            if action == "care":
                bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
            else:
                bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки callback: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Ошибка")

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

                # Сохраняем в Google Таблицу, если настроено
                if SPREADSHEET_URL and sheet_users:
                    save_favorite_to_sheet(user_id, call.from_user, selected_rose)
        except Exception as e:
            logger.error(f"❌ Ошибка добавления в избранное: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Ошибка")

    def save_favorite_to_sheet(user_id, user, rose):
        try:
            first_name = user.first_name
            username = f"@{user.username}" if user.username else ""
            date = datetime.now().strftime("%Y-%m-%d %H:%M")
            favorite_name = rose.get('Название', 'Без названия')

            sheet_favorites = gs.open_by_url(SPREADSHEET_URL).worksheet("Избранное")
            sheet_favorites.append_row([
                user_id,
                first_name,
                username,
                date,
                favorite_name
            ])
            logger.info(f"✅ Добавлено в Google Таблицу: {favorite_name} (Пользователь: {user_id})")
        except Exception as e:
            logger.error(f"❌ Ошибка записи в Google Таблицу: {e}", exc_info=True)

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
            logger.error(f"❌ Ошибка деталей избранного: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Ошибка")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_fav_"))
    def handle_delete_favorite(call):
        try:
            data_parts = call.data.split("_")
            if len(data_parts) < 2:
                logger.error(f"❌ Неверный формат callback_ {call.data}")
                bot.answer_callback_query(call.id, "❌ Ошибка формата")
                return

            idx = int(data_parts[2])  # delete_fav_1 → ['delete', 'fav', '1']
            user_id = call.from_user.id

            favorites = user_favorites.get(user_id, [])

            if not favorites or idx >= len(favorites):
                logger.warning(f"❌ Роза не найдена для удаления: {idx}")
                bot.answer_callback_query(call.id, "❌ Роза не найдена")
                return

            removed_rose = favorites.pop(idx)
            logger.info(f"✅ Удалено: {removed_rose.get('Название')} (ID: {user_id})")
            bot.answer_callback_query(call.id, f"✅ Удалено: {removed_rose.get('Название', 'Без названия')}")

            # Удаляем из Google Таблицы, если настроено
            if SPREADSHEET_URL:
                delete_favorite_from_sheet(user_id, removed_rose.get('Название', ''))
            else:
                logger.warning("❌ Google Таблица не настроена — удаление невозможно")

            bot.send_message(call.message.chat.id, "🔄 Обновлённый список избранного:")
            show_favorites(call.message)

        except Exception as e:
            logger.error(f"❌ Ошибка удаления из избранного: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Ошибка при удалении")

    def delete_favorite_from_sheet(user_id, rose_name):
        try:
            logger.info(f"🔍 Ищем в таблице: пользователь {user_id}, роза '{rose_name}'")

            sheet_favorites = gs.open_by_url(SPREADSHEET_URL).worksheet("Избранное")
            all_data = sheet_favorites.get_all_values()

            found = False
            for row_idx, row in enumerate(all_data[1:], start=2):  # Пропускаем заголовок
                if str(user_id) == row[0].strip() and rose_name.strip() == row[4].strip():
                    logger.info(f"🗑 Удаляем строку {row_idx}: {row}")
                    sheet_favorites.delete_rows(row_idx)
                    found = True
                    break

            if not found:
                logger.warning(f"⚠️ Запись не найдена: пользователь {user_id}, роза '{rose_name}'")

        except Exception as e:
            logger.error(f"❌ Ошибка удаления из Google Таблицы: {e}", exc_info=True)

    @bot.message_handler(commands=['stats'])
    def send_stats(message):
        if not rose_search_stats:
            bot.send_message(message.chat.id, "📊 Пока нет статистики по поиску роз.")
            return

        bot.send_message(message.chat.id, "📈 Статистика поиска роз:")

        sorted_stats = sorted(rose_search_stats.items(), key=lambda x: x[1], reverse=True)
        for name, count in sorted_stats:
            bot.send_message(message.chat.id, f"🌹 {name}: {count} поисков")

        # Сохраняем статистику в Google Таблицу
        if SPREADSHEET_URL:
            save_stats_to_sheet()

    def save_stats_to_sheet():
        if not SPREADSHEET_URL:
            logger.warning("❌ Google Таблица не настроена — статистика не сохранена")
            return

        try:
            sheet_stats = gs.open_by_url(SPREADSHEET_URL).worksheet("Статистика")

            # Очищаем таблицу и добавляем заголовок
            sheet_stats.clear()
            sheet_stats.append_row(["Сорт розы", "Количество поисков"])

            # Сортируем по популярности
            sorted_stats = sorted(rose_search_stats.items(), key=lambda x: x[1], reverse=True)

            for name, count in sorted_stats:
                sheet_stats.append_row([name, count])

            logger.info("📊 Статистика поиска успешно сохранена в Google Таблицу")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения статистики: {e}")

setup_handlers()

# Запуск Flask
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)
