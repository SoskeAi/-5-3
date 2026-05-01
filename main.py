import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== КОНФИГ ==========
BOT_TOKEN = "8162631163:AAFnOQUe6ZohoMYPoWfa7MW7LKogeSzXLJM"
YOUR_USER_ID = 7564741700
CHANNEL_ID = -1003916314972
REACTION_EMOJIS = ['💥', '🔥', '😅', '🙃', '🎉']
COOLDOWN_SECONDS = 600

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.db_path = 'bot.db'
        self._init_tables()
    
    def _init_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS messages (
                    original_msg_id INTEGER PRIMARY KEY,
                    channel_msg_id INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reactions (
                    user_id INTEGER,
                    channel_msg_id INTEGER,
                    emoji TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    PRIMARY KEY (user_id, channel_msg_id)
                );
                CREATE TABLE IF NOT EXISTS reaction_counts (
                    channel_msg_id INTEGER,
                    emoji TEXT,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY (channel_msg_id, emoji)
                );
            ''')
    
    def save_message_pair(self, original_id: int, channel_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('INSERT OR REPLACE INTO messages VALUES (?, ?)', (original_id, channel_id))
    
    def get_user_reaction(self, user_id: int, channel_msg_id: int):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('SELECT emoji, timestamp FROM reactions WHERE user_id = ? AND channel_msg_id = ?', (user_id, channel_msg_id)).fetchone()
        return row if row else (None, None)
    
    def set_reaction(self, user_id: int, channel_msg_id: int, emoji: str, timestamp: int):
        with sqlite3.connect(self.db_path) as conn:
            old = conn.execute('SELECT emoji FROM reactions WHERE user_id = ? AND channel_msg_id = ?', (user_id, channel_msg_id)).fetchone()
            if old:
                old_emoji = old[0]
                conn.execute('UPDATE reaction_counts SET count = count - 1 WHERE channel_msg_id = ? AND emoji = ?', (channel_msg_id, old_emoji))
                conn.execute('DELETE FROM reactions WHERE user_id = ? AND channel_msg_id = ?', (user_id, channel_msg_id))
            conn.execute('INSERT OR REPLACE INTO reactions VALUES (?, ?, ?, ?)', (user_id, channel_msg_id, emoji, timestamp))
            conn.execute('''INSERT INTO reaction_counts (channel_msg_id, emoji, count) VALUES (?, ?, 1) ON CONFLICT(channel_msg_id, emoji) DO UPDATE SET count = count + 1''', (channel_msg_id, emoji))
            conn.commit()
    
    def remove_reaction(self, user_id: int, channel_msg_id: int):
        with sqlite3.connect(self.db_path) as conn:
            old = conn.execute('SELECT emoji FROM reactions WHERE user_id = ? AND channel_msg_id = ?', (user_id, channel_msg_id)).fetchone()
            if old:
                old_emoji = old[0]
                conn.execute('UPDATE reaction_counts SET count = count - 1 WHERE channel_msg_id = ? AND emoji = ?', (channel_msg_id, old_emoji))
                conn.execute('DELETE FROM reactions WHERE user_id = ? AND channel_msg_id = ?', (user_id, channel_msg_id))
                conn.commit()
                return True
        return False
    
    def get_counts(self, channel_msg_id: int):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute('SELECT emoji, count FROM reaction_counts WHERE channel_msg_id = ?', (channel_msg_id,)).fetchall()
        counts = {emoji: count for emoji, count in rows}
        for emoji in REACTION_EMOJIS:
            if emoji not in counts:
                counts[emoji] = 0
        return counts
    
    def init_counts(self, channel_msg_id: int):
        with sqlite3.connect(self.db_path) as conn:
            for emoji in REACTION_EMOJIS:
                conn.execute('INSERT OR IGNORE INTO reaction_counts (channel_msg_id, emoji, count) VALUES (?, ?, 0)', (channel_msg_id, emoji))
            conn.commit()

db = Database()

# ========== КНОПКИ ==========
def get_reply_markup(channel_msg_id: int, counts: dict):
    buttons = [[InlineKeyboardButton(f"{emoji} {counts.get(emoji, 0)}", callback_data=f"react_{emoji}_{channel_msg_id}") for emoji in REACTION_EMOJIS]]
    return InlineKeyboardMarkup(buttons)

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def copy_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID or update.effective_chat.type != 'private':
        return
    
    msg = update.effective_message
    
    try:
        if msg.photo:
            sent = await context.bot.send_photo(chat_id=CHANNEL_ID, photo=msg.photo[-1].file_id, caption=msg.caption)
        elif msg.video:
            sent = await context.bot.send_video(chat_id=CHANNEL_ID, video=msg.video.file_id, caption=msg.caption)
        elif msg.document:
            sent = await context.bot.send_document(chat_id=CHANNEL_ID, document=msg.document.file_id, caption=msg.caption)
        elif msg.voice:
            sent = await context.bot.send_voice(chat_id=CHANNEL_ID, voice=msg.voice.file_id, caption=msg.caption)
        elif msg.text:
            sent = await context.bot.send_message(chat_id=CHANNEL_ID, text=msg.text)
        else:
            return
        
        db.save_message_pair(msg.message_id, sent.message_id)
        db.init_counts(sent.message_id)
        
        counts = db.get_counts(sent.message_id)
        await context.bot.edit_message_reply_markup(chat_id=CHANNEL_ID, message_id=sent.message_id, reply_markup=get_reply_markup(sent.message_id, counts))
        
    except Exception as e:
        print(f"Ошибка: {e}")

# ========== ОБРАБОТЧИК КНОПОК ==========
async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    _, emoji, channel_msg_id = data.split('_')
    channel_msg_id = int(channel_msg_id)
    
    current_emoji, timestamp = db.get_user_reaction(user_id, channel_msg_id)
    now = int(datetime.now().timestamp())
    
    # Проверка кулдауна
    if timestamp and (now - timestamp) < COOLDOWN_SECONDS and emoji != current_emoji:
        await query.answer(f"Подождите {(COOLDOWN_SECONDS - (now - timestamp)) // 60} минут", show_alert=True)
        return
    
    if current_emoji == emoji:
        # Убираем реакцию
        db.remove_reaction(user_id, channel_msg_id)
    else:
        # Меняем или ставим новую
        db.set_reaction(user_id, channel_msg_id, emoji, now)
    
    # Обновляем кнопки
    counts = db.get_counts(channel_msg_id)
    await query.edit_message_reply_markup(reply_markup=get_reply_markup(channel_msg_id, counts))

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, copy_to_channel))
    app.add_handler(CallbackQueryHandler(handle_reaction, pattern='^react_'))
    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()