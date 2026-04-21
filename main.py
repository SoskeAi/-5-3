import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Конфигурация
BOT_TOKEN = "8162631163:AAFnOQUe6ZohoMYPoWfa7MW7LKogeSzXLJM"
USER_ID = 7564741700           # ТОЛЬКО этот пользователь может использовать бота
CHANNEL_ID = -1003916314972    # Куда пересылать

# Хранилище для счётчиков реакций
# Формат: {message_id: {reaction: count}}
reactions_storage = {}

# Базовые кнопки (без счётчиков)
BASE_BUTTONS = ["❤️", "🥰", "🔥", "🤣", "😏"]

async def forward_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересылает ТОЛЬКО из ЛС разрешённого пользователя в канал"""
    
    if update.effective_chat.type != "private":
        return
    
    user = update.effective_user
    if user.id != USER_ID:
        return
    
    # Получаем текст и фото
    text = update.message.caption or update.message.text or ""
    photo = update.message.photo[-1] if update.message.photo else None
    
    # Создаём кнопки с нулевыми счётчиками
    buttons = [
        [InlineKeyboardButton(f"{btn} 0", callback_data=btn) for btn in BASE_BUTTONS]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    
    try:
        if photo:
            sent_message = await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo.file_id,
                caption=text,
                reply_markup=reply_markup
            )
        else:
            sent_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=text,
                reply_markup=reply_markup
            )
        
        # Инициализируем счётчики для этого сообщения
        reactions_storage[sent_message.message_id] = {btn: 0 for btn in BASE_BUTTONS}
        
        await update.message.reply_text("✅ Опубликовано в канале!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок — увеличиваем счётчик"""
    query = update.callback_query
    await query.answer()
    
    message_id = query.message.message_id
    reaction = query.data  # Например: "❤️"
    
    # Проверяем, есть ли счётчики для этого сообщения
    if message_id not in reactions_storage:
        # Если нет — создаём (на случай перезапуска бота)
        reactions_storage[message_id] = {btn: 0 for btn in BASE_BUTTONS}
    
    # Увеличиваем счётчик
    reactions_storage[message_id][reaction] += 1
    
    # Обновляем кнопки с новыми счётчиками
    buttons = [
        [InlineKeyboardButton(f"{btn} {reactions_storage[message_id][btn]}", callback_data=btn) 
         for btn in BASE_BUTTONS]
    ]
    new_markup = InlineKeyboardMarkup(buttons)
    
    # Обновляем клавиатуру (сообщение не меняется, только кнопки)
    await query.edit_message_reply_markup(reply_markup=new_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Только разрешённый пользователь может использовать /start"""
    
    if update.effective_chat.type != "private":
        return
    
    if update.effective_user.id == USER_ID:
        await update.message.reply_text("Привет! Присылай текст или фото с подписью — отправлю в канал с кнопками.\n\nНа кнопки могут нажимать все, счётчики обновляются автоматически!")
    else:
        return

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, forward_to_channel))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Бот запущен. Кнопки показывают количество нажатий!")
    app.run_polling()

if __name__ == "__main__":
    main()
