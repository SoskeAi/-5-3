import json
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== КОНФИГ ==========
BOT_TOKEN = "8162631163:AAFnOQUe6ZohoMYPoWfa7MW7LKogeSzXLJM"
YOUR_USER_ID = 7564741700
CHANNEL_ID = -1003916314972
REACTION_EMOJIS = ['💥', '🔥', '😅', '🙃', '🎉']
COOLDOWN_SECONDS = 600
DATA_FILE = 'bot_data.json'

# ========== БАЗА ДАННЫХ (JSON) ==========
class Database:
    def __init__(self):
        self.data = {
            "messages": {},      # original_msg_id: channel_msg_id
            "reactions": {},     # f"{user_id}_{channel_msg_id}": {"emoji": "💥", "timestamp": 123456789}
            "counts": {}         # f"{channel_msg_id}_{emoji}": count
        }
        self._load()
        self._lock = asyncio.Lock()  # Для потокобезопасности
    
    def _load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Ошибка загрузки данных: {e}")
                self.data = {"messages": {}, "reactions": {}, "counts": {}}
    
    async def _save(self):
        async with self._lock:
            try:
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except IOError as e:
                print(f"Ошибка сохранения данных: {e}")
    
    async def save_message_pair(self, original_id: int, channel_id: int):
        self.data["messages"][str(original_id)] = channel_id
        await self._save()
    
    def get_user_reaction(self, user_id: int, channel_msg_id: int):
        key = f"{user_id}_{channel_msg_id}"
        if key in self.data["reactions"]:
            return self.data["reactions"][key]["emoji"], self.data["reactions"][key]["timestamp"]
        return None, None
    
    async def set_reaction(self, user_id: int, channel_msg_id: int, emoji: str, timestamp: int):
        key = f"{user_id}_{channel_msg_id}"
        
        # Удаляем старую реакцию если была
        old = self.data["reactions"].get(key)
        if old:
            old_emoji = old["emoji"]
            count_key = f"{channel_msg_id}_{old_emoji}"
            self.data["counts"][count_key] = self.data["counts"].get(count_key, 0) - 1
            if self.data["counts"][count_key] <= 0:
                del self.data["counts"][count_key]
        
        # Добавляем новую
        self.data["reactions"][key] = {"emoji": emoji, "timestamp": timestamp}
        count_key = f"{channel_msg_id}_{emoji}"
        self.data["counts"][count_key] = self.data["counts"].get(count_key, 0) + 1
        await self._save()
    
    async def remove_reaction(self, user_id: int, channel_msg_id: int):
        key = f"{user_id}_{channel_msg_id}"
        old = self.data["reactions"].get(key)
        if old:
            old_emoji = old["emoji"]
            count_key = f"{channel_msg_id}_{old_emoji}"
            self.data["counts"][count_key] = self.data["counts"].get(count_key, 0) - 1
            if self.data["counts"][count_key] <= 0:
                del self.data["counts"][count_key]
            del self.data["reactions"][key]
            await self._save()
            return True
        return False
    
    def get_counts(self, channel_msg_id: int):
        counts = {}
        for emoji in REACTION_EMOJIS:
            count_key = f"{channel_msg_id}_{emoji}"
            counts[emoji] = self.data["counts"].get(count_key, 0)
        return counts

db = Database()

# ========== КНОПКИ ==========
def get_reply_markup(channel_msg_id: int, counts: dict):
    # Разбиваем на 2 ряда по 3 и 2 кнопки для лучшего отображения
    buttons = []
    row = []
    for i, emoji in enumerate(REACTION_EMOJIS):
        row.append(InlineKeyboardButton(f"{emoji} {counts.get(emoji, 0)}", callback_data=f"react_{emoji}_{channel_msg_id}"))
        if len(row) == 3 or i == len(REACTION_EMOJIS) - 1:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def copy_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что сообщение от нужного пользователя и в личке
    if not update.effective_user or update.effective_user.id != YOUR_USER_ID:
        return
    
    if not update.effective_message or update.effective_chat.type != 'private':
        return
    
    msg = update.effective_message
    
    try:
        sent = None
        
        if msg.photo:
            sent = await context.bot.send_photo(
                chat_id=CHANNEL_ID, 
                photo=msg.photo[-1].file_id, 
                caption=msg.caption
            )
        elif msg.video:
            sent = await context.bot.send_video(
                chat_id=CHANNEL_ID, 
                video=msg.video.file_id, 
                caption=msg.caption
            )
        elif msg.document:
            sent = await context.bot.send_document(
                chat_id=CHANNEL_ID, 
                document=msg.document.file_id, 
                caption=msg.caption
            )
        elif msg.voice:
            sent = await context.bot.send_voice(
                chat_id=CHANNEL_ID, 
                voice=msg.voice.file_id, 
                caption=msg.caption
            )
        elif msg.text:
            sent = await context.bot.send_message(
                chat_id=CHANNEL_ID, 
                text=msg.text
            )
        else:
            # Неподдерживаемый тип сообщения
            return
        
        if sent:
            await db.save_message_pair(msg.message_id, sent.message_id)
            
            counts = db.get_counts(sent.message_id)
            await context.bot.edit_message_reply_markup(
                chat_id=CHANNEL_ID, 
                message_id=sent.message_id, 
                reply_markup=get_reply_markup(sent.message_id, counts)
            )
        
    except Exception as e:
        print(f"Ошибка при копировании сообщения: {e}")

# ========== ОБРАБОТЧИК КНОПОК ==========
async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not query.from_user or not query.data:
        return
    
    user_id = query.from_user.id
    data_parts = query.data.split('_')
    
    # Проверяем формат данных
    if len(data_parts) != 3 or data_parts[0] != 'react':
        return
    
    _, emoji, channel_msg_id_str = data_parts
    try:
        channel_msg_id = int(channel_msg_id_str)
    except ValueError:
        return
    
    current_emoji, timestamp = db.get_user_reaction(user_id, channel_msg_id)
    now = int(datetime.now().timestamp())
    
    # Проверка кулдауна
    if timestamp and (now - timestamp) < COOLDOWN_SECONDS and emoji != current_emoji:
        wait_seconds = COOLDOWN_SECONDS - (now - timestamp)
        wait_minutes = wait_seconds // 60
        wait_seconds_remain = wait_seconds % 60
        await query.answer(
            f"Подождите {wait_minutes} мин {wait_seconds_remain} сек", 
            show_alert=True
        )
        return
    
    if current_emoji == emoji:
        # Убираем реакцию
        await db.remove_reaction(user_id, channel_msg_id)
        await query.answer("Реакция убрана")
    else:
        # Меняем или ставим новую
        await db.set_reaction(user_id, channel_msg_id, emoji, now)
        await query.answer(f"Реакция {emoji} поставлена")
    
    # Обновляем кнопки
    counts = db.get_counts(channel_msg_id)
    try:
        await query.edit_message_reply_markup(reply_markup=get_reply_markup(channel_msg_id, counts))
    except Exception as e:
        print(f"Ошибка обновления кнопок: {e}")

# ========== ЗАПУСК ==========
def main():
    # Создаём приложение с увеличенными таймаутами
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    
    # Добавляем обработчики
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & filters.USER(YOUR_USER_ID), copy_to_channel))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO & filters.USER(YOUR_USER_ID), copy_to_channel))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.VIDEO & filters.USER(YOUR_USER_ID), copy_to_channel))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Document.ALL & filters.USER(YOUR_USER_ID), copy_to_channel))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.VOICE & filters.USER(YOUR_USER_ID), copy_to_channel))
    app.add_handler(CallbackQueryHandler(handle_reaction, pattern='^react_'))
    
    print("🤖 Бот запущен...")
    print(f"📁 Данные хранятся в {DATA_FILE}")
    print(f"👤 ID вашего пользователя: {YOUR_USER_ID}")
    print(f"📢 ID канала: {CHANNEL_ID}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()