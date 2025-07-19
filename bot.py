001| import os
002| import json
003| import logging
004| import telebot
005| from flask import Flask, request
006| from google.oauth2.service_account import Credentials
007| import gspread
008| from datetime import datetime
009| from urllib.parse import quote_plus, unquote_plus
010| 
011| # Логирование
012| logging.basicConfig(level=logging.INFO)
013| logger = logging.getLogger(__name__)
014| 
015| # Переменные окружения
016| BOT_TOKEN = os.getenv("BOT_TOKEN")
017| SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
018| CREDS_JSON = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
019| 
020| # Инициализация бота
021| bot = telebot.TeleBot(BOT_TOKEN)
022| 
023| # Авторизация Google Sheets
024| creds = Credentials.from_service_account_info(
025|     CREDS_JSON,
026|     scopes=["https://www.googleapis.com/auth/spreadsheets"]
027| )
028| gs = gspread.authorize(creds)
029| sheet = gs.open_by_url(SPREADSHEET_URL).sheet1
030| sheet_users = gs.open_by_url(SPREADSHEET_URL).worksheet("Пользователи")
031| 
032| # Кэш роз
033| cached_roses = []
034| def refresh_cached_roses():
035|     global cached_roses
036|     try:
037|         cached_roses = sheet.get_all_records()
038|         logger.info("✅ Данные роз загружены")
039|     except Exception as e:
040|         logger.error(f"❌ Ошибка загрузки данных: {e}")
041|         cached_roses = []
042| 
043| refresh_cached_roses()
044| 
045| # Flask + Webhook
046| app = Flask(__name__)
047| WEBHOOK_URL = "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
048| try:
049|     bot.remove_webhook()
050|     if WEBHOOK_URL:
051|         bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
052|         logger.info(f"🌐 Webhook установлен: {WEBHOOK_URL}/telegram")
053| except Exception as e:
054|     logger.error(f"❌ Webhook не установлен: {e}")
055| 
056| @app.route('/')
057| def index():
058|     return 'Бот работает!'
059| 
060| @app.route('/telegram', methods=['POST'])
061| def webhook():
062|     update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
063|     bot.process_new_updates([update])
064|     return '', 200
065| 
066| # 📥 Логирование поисковых запросов
067| def log_user_query(message, query_text):
068|     try:
069|         sheet_users.append_row([
070|             message.from_user.id,
071|             message.from_user.first_name,
072|             f"@{message.from_user.username}" if message.from_user.username else "",
073|             datetime.now().strftime("%Y-%m-%d %H:%M"),
074|             query_text
075|         ])
076|         logger.info(f"✅ Запрос пользователя сохранён: {query_text}")
077|     except Exception as e:
078|         logger.error(f"❌ Ошибка записи в Google Таблицу: {e}")
079| 
080| # Обработчики
081| def setup_handlers():
082| 
083|     @bot.message_handler(commands=['start'])
084|     def send_welcome(message):
085|         send_main_menu(message.chat.id, "🌹 <b>Добро пожаловать!</b>\n\nВыберите действие:")
086| 
087|     @bot.message_handler(commands=['menu'])
088|     def show_menu(message):
089|         send_main_menu(message.chat.id, "📋 Главное меню:")
090| 
091|     def send_main_menu(chat_id, text):
092|         markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
093|         markup.add("🔎 Поиск")
094|         markup.row("📞 Связаться")
095|         bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)
096| 
097|     @bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
098|     def handle_search_prompt(message):
099|         bot.send_message(message.chat.id, "🔍 Введите название розы")
100| 
101|     @bot.message_handler(func=lambda m: m.text == "📞 Связаться")
102|     def handle_contact(message):
103|         bot.reply_to(message, "💬 Напишите нам: @your_username")
104| 
105|     @bot.message_handler(func=lambda message: True)
106|     def handle_search_text(message):
107|         query = message.text.strip().lower()
108|         if query in ["меню", "начать", "/menu", "/start"]:
109|             send_main_menu(message.chat.id, "🔄 Меню восстановлено.")
110|             return
111| 
112|         log_user_query(message, query)
113| 
114|         results = [r for r in cached_roses if query in r.get('Название', '').lower()]
115|         if not results:
116|             bot.send_message(message.chat.id, "❌ Ничего не найдено.")
117|             return
118| 
119|         for rose in results[:5]:
120|             send_rose_card(message.chat.id, rose)
121| 
122|     def send_rose_card(chat_id, rose):
123|         name = rose.get('Название', '')
124|         description = rose.get('Описание', '')
125|         price = rose.get('price', 'нет данных').strip()
126| 
127|         caption = (
128|             f"🌹 <b>{name}</b>\n"
129|             f"{description}\n"
130|             f"Описание: {price}"
131|         )
132| 
133|         photo_url = rose.get('photo', 'https://example.com/default.jpg')
134|         encoded_name = quote_plus(name)
135| 
136|         keyboard = telebot.types.InlineKeyboardMarkup()
137|         keyboard.add(
138|             telebot.types.InlineKeyboardButton("🪴 Уход", callback_data=f"care_{encoded_name}"),
139|             telebot.types.InlineKeyboardButton("📜 История", callback_data=f"history_{encoded_name}")
140|         )
141|         bot.send_photo(chat_id, photo_url, caption=caption, parse_mode='HTML', reply_markup=keyboard)
142| 
143|     @bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_")))
144|     def handle_rose_details(call):
145|         try:
146|             action, encoded_name = call.data.split("_", 1)
147|             name = unquote_plus(encoded_name)
148| 
149|             rose = next((r for r in cached_roses if r.get('Название', '').strip() == name), None)
150|             if not rose:
151|                 bot.answer_callback_query(call.id, "Роза не найдена.")
152|                 return
153| 
154|             if action == "care":
155|                 bot.send_message(call.message.chat.id, f"🪴 Уход:\n{rose.get('Уход', 'Не указано')}")
156|             else:
157|                 bot.send_message(call.message.chat.id, f"📜 История:\n{rose.get('История', 'Не указана')}")
158|         except Exception as e:
159|             logger.error(f"Ошибка обработки callback: {e}")
160|             bot.answer_callback_query(call.id, "Произошла ошибка")
161| 
162| setup_handlers()
163| 
164| # Запуск Flask
165| if __name__ == '__main__':
166|     port = int(os.environ.get("PORT", 8080))
167|     logger.info(f"🚀 Запуск Flask на порту {port}")
168|     app.run(host="0.0.0.0", port=port)
