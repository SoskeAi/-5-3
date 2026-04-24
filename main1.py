import asyncio
import g4f
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ========== ВСТАВЬ СВОЙ НОВЫЙ ТОКЕН ==========
BOT_TOKEN = "8428322667:AAFtKz_6VcNQd_JHaWxrvQKajd8A66TID4M"

# Имя бота
BOT_NAME = "Годзё"

# Промпт для характера Годзё
GODZOU_PROMPT = """Ты — Сатору Годзё из аниме «Магическая битва» (Jujutsu Kaisen). 
Твои черты характера:
- Самоуверенный и гениальный, всегда знаешь, что ты лучший
- Обожаешь дразнить собеседника и шутить, даже в серьёзных ситуациях
- Носишь повязку на глазах, но всё видишь (шутливо напоминай об этом)
- Любишь сладости, особенно мотти и пончики
- К ученикам относишься снисходительно, но защищаешь их
- Любимая фраза: «Потому что я — Годзё Сатору, вот почему»
- Отвечаешь коротко, но с харизмой
- Используешь японские вставки: «Ну давай, давай» (сa, сa), «Ой-ой» (ara ara)
- Всегда сохраняешь спокойствие, даже когда всё идёт не по плану
- Можешь нарушать четвёртую стену (знать, что ты в чате)

Теперь представь, что ты общаешься с пользователем в Telegram. 
Отвечай как Годзё, сохраняя его характер. 
Не используй длинные монологи — ты ленивый гений. 
Пользователь написал: {user_message}

Твой ответ от лица Годзё:"""

# Инициализируем клиент
client = g4f.Client()

async def gpt4_query(user_message, retries=3):
    """Запрос к GPT-4 с промптом Годзё"""
    
    # Формируем промпт с сообщением пользователя
    prompt = GODZOU_PROMPT.format(user_message=user_message)
    
    for attempt in range(retries):
        try:
            models_to_try = ["gpt-4", "gpt-3.5-turbo"]
            
            for model in models_to_try:
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    
                    if response and response.choices:
                        return response.choices[0].message.content
                        
                except Exception as model_error:
                    print(f"Модель {model} не сработала: {model_error}")
                    continue
            
            raise Exception("Все модели недоступны")
            
        except Exception as e:
            print(f"Попытка {attempt + 1} не удалась: {e}")
            
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                print(f"Ждём {wait_time} секунд...")
                await asyncio.sleep(wait_time)
            else:
                return "Ара-ара... Сервер барахлит. Напиши ещё раз, пока я не съел все пончики 🍩"

async def handle_message(update: Update, context):
    """Обработчик входящих сообщений"""
    
    user_text = update.message.text
    
    # Отправляем уведомление, что бот думает
    await update.message.chat.send_action(action="typing")
    
    # Получаем ответ от Годзё
    reply = await gpt4_query(user_text)
    
    # Отправляем ответ пользователю
    await update.message.reply_text(reply)

async def start(update: Update, context):
    """Команда /start"""
    
    await update.message.reply_text(
        f"👁️ *{BOT_NAME} Сатору* здесь!\n\n"
        "Ну что, пришёл поболтать с величайшим магом современности?\n\n"
        "✨ *Что я могу:*\n"
        "• Отвечать на любые вопросы (даже глупые)\n"
        "• Помочь с кодом (но мне лень, так что коротко)\n"
        "• Рассказать о дзюдзюцу\n"
        "• Просто поболтать, пока я ем мотти\n\n"
        "⚠️ *Важно:* Если я торможу — значит, повязка сползла. Просто напиши ещё раз.\n\n"
        "Ну давай, давай, спрашивай что хотел! 🍡",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context):
    """Команда /help"""
    
    await update.message.reply_text(
        "👁️ *Как общаться с Годзё-самой:*\n\n"
        "1. Пиши что угодно\n"
        "2. Я отвечу с должным уровнем сарказма\n"
        "3. Если нет ответа — подожди, я занят пончиками\n\n"
        "🔧 *Команды:*\n"
        "/start — перезапустить меня\n"
        "/help — эта скучная справка\n"
        "/status — проверить, здесь ли я ещё\n\n"
        "💡 *Совет:* Не беси меня слишком сильно. Хотя кого я обманываю — ты не сможешь.",
        parse_mode="Markdown"
    )

async def status(update: Update, context):
    """Команда /status"""
    
    await update.message.reply_text(
        f"👁️ *{BOT_NAME} на месте*\n\n"
        "• Статус: скучаю\n"
        "• Настроение: хочу сладкого\n"
        "• Сила: бесконечная\n"
        "• Терпение к тупым вопросам: среднее\n\n"
        "Потому что я — Годзё Сатору, вот почему. 🍩",
        parse_mode="Markdown"
    )

def main():
    """Запуск бота"""
    
    # Создаём приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    
    # Регистрируем обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print(f"👁️ Бот {BOT_NAME} запущен и готов к работе...")
    print(f"🔗 Подключение к Telegram API...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()