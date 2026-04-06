import asyncio
import json
import os
import random
from datetime import datetime, timedelta
import pytz
from pytz import timezone

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import aiofiles
OWNER_ID = 7564741700
# Конфигурация
BOT_TOKEN = "8162631163:AAFRs_BObrlgk2E-ygd4eYYBsXBHKL4NdCs"
DATA_FILE = "botUsersAi.json"
KRASNOYARSK_TZ = timezone('Asia/Krasnoyarsk')  # UTC+7

# Константы банка
BANK_CELL_CAPACITY = 5000  # Каждая ячейка дает +5000 к лимиту
BASE_CELL_COST = 3000  # Стоимость второй ячейки

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ----------------------------------- Работа с JSON -----------------------------------
async def load_users():
    """Загружает пользователей из JSON файла."""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        async with aiofiles.open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content) if content else {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

async def save_users(users):
    """Сохраняет пользователей в JSON файл."""
    async with aiofiles.open(DATA_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(users, indent=4, ensure_ascii=False))

async def get_user_avatar(user: types.User):
    """Получает ссылку на аватарку пользователя."""
    try:
        photos = await bot.get_user_profile_photos(user.id)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            file = await bot.get_file(file_id)
            avatar_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            return avatar_url
    except:
        pass
    return None

async def is_user_registered(user_id: int) -> bool:
    """Проверяет, зарегистрирован ли пользователь."""
    users = await load_users()
    return str(user_id) in users

async def check_registration(message: Message) -> bool:
    """Проверка регистрации и отправка сообщения если не зарегистрирован."""
    if not await is_user_registered(message.from_user.id):
        await message.answer(
            "❌ Ты еще не зарегистрирован!\n"
            "Напиши <code>.имя</code> чтобы зарегистрироваться и получить 1000 msg",
            parse_mode="HTML"
        )
        return False
    return True

async def get_current_krasnoyarsk_time():
    """Возвращает текущее время в Красноярске."""
    return datetime.now(KRASNOYARSK_TZ)

async def register_or_update_user(message: Message, username_text: str = None):
    """Регистрирует нового пользователя или обновляет данные существующего."""
    users = await load_users()
    user_id = str(message.from_user.id)
    current_time = (await get_current_krasnoyarsk_time()).isoformat()

    # Получаем аватарку
    avatar_url = await get_user_avatar(message.from_user)

    # Если пользователь уже существует
    if user_id in users:
        # Обновляем данные, но НЕ обнуляем msg_count
        users[user_id]["username"] = message.from_user.username
        users[user_id]["full_name"] = message.from_user.full_name
        users[user_id]["avatar"] = avatar_url
        users[user_id]["last_activity"] = current_time
        if username_text:  # Обновляем имя только если передали новое
            users[user_id]["registered_name"] = username_text
        
        # Проверяем и добавляем банковские поля, если их нет
        if "bank_cells" not in users[user_id]:
            users[user_id]["bank_cells"] = 1  # Количество ячеек
        if "bank_amount" not in users[user_id]:
            users[user_id]["bank_amount"] = 0  # Сколько msg в банке
        if "hourly_messages" not in users[user_id]:
            users[user_id]["hourly_messages"] = 0
        if "last_interest_hour" not in users[user_id]:
            users[user_id]["last_interest_hour"] = current_time
        
        await save_users(users)
        return users[user_id], False  # False = не новый пользователь
    else:
        # Новый пользователь - начисляем 1000 msg и создаем банковские поля
        user_data = {
            "id": message.from_user.id,
            "username": message.from_user.username,
            "full_name": message.from_user.full_name,
            "avatar": avatar_url,
            "registered_at": current_time,
            "last_activity": current_time,
            "msg_count": 1000,  # Начисляем 1000 за регистрацию
            "registered_name": username_text if username_text else message.from_user.full_name,
            "bank_cells": 1,  # Начинаем с 1 ячейки
            "bank_amount": 0,  # В банке пока пусто
            "hourly_messages": 0,  # Счетчик сообщений за текущий час
            "last_interest_hour": current_time,  # Время последнего начисления процентов
            "friends": [], 
            "friend_requests": [],
        }
        
        users[user_id] = user_data
        await save_users(users)
        return user_data, True  # True = новый пользователь

async def get_bank_limit(cells: int) -> int:
    """Возвращает лимит банка в зависимости от количества ячеек."""
    return cells * BANK_CELL_CAPACITY

async def get_cell_cost(cell_number: int) -> int:
    """Возвращает стоимость ячейки по ее номеру (1-я бесплатная)."""
    if cell_number == 1:
        return 0  # Первая ячейка бесплатная
    return BASE_CELL_COST + (cell_number - 2) * 1000  # 2-я: 3000, 3-я: 4000, 4-я: 5000...

async def check_and_apply_bank_interest(user_id: int):
    """Проверяет, наступил ли новый час, и начисляет проценты."""
    users = await load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        return
    
    user = users[user_id_str]
    current_time = await get_current_krasnoyarsk_time()
    
    # Получаем время последнего начисления процентов
    last_interest = datetime.fromisoformat(user.get("last_interest_hour", current_time.isoformat()))
    if last_interest.tzinfo is None:
        last_interest = KRASNOYARSK_TZ.localize(last_interest)
    
    # Проверяем, наступил ли новый час (00 минут)
    current_hour_start = current_time.replace(minute=0, second=0, microsecond=0)
    last_hour_start = last_interest.replace(minute=0, second=0, microsecond=0)
    
    # Если текущий час больше последнего часа начисления
    if current_hour_start > last_hour_start:
        # Проверяем, набрал ли пользователь 50 сообщений за прошедший час
        if user.get("hourly_messages", 0) >= 10:
            # Начисляем 1% от суммы в банке
            bank_amount = user.get("bank_amount", 0)
            interest = int(bank_amount * 0.01)  # 1%
            
            if interest > 0:
                # Проверяем, не превысит ли лимит
                bank_limit = await get_bank_limit(user.get("bank_cells", 1))
                if bank_amount + interest <= bank_limit:
                    users[user_id_str]["bank_amount"] += interest
                    hour_str = current_hour_start.strftime("%H:00")
                    print(f"  └─ 💰 [{hour_str}] Начислены проценты: +{interest} msg пользователю {user_id}")
                else:
                    # Если превышает лимит, начисляем только до лимита
                    available = bank_limit - bank_amount
                    if available > 0:
                        users[user_id_str]["bank_amount"] += available
                        print(f"  └─ 💰 [{hour_str}] Начислены проценты: +{available} msg (достигнут лимит банка)")
        
        # Сбрасываем счетчик сообщений и обновляем время последнего начисления
        users[user_id_str]["hourly_messages"] = 0
        users[user_id_str]["last_interest_hour"] = current_hour_start.isoformat()
        await save_users(users)

async def add_msg_coin(user_id: int):
    """Добавляет 1 монетку за сообщение и обновляет часовой счетчик."""
    users = await load_users()
    user_id_str = str(user_id)
    
    if user_id_str in users:
        # Увеличиваем баланс
        users[user_id_str]["msg_count"] = users[user_id_str].get("msg_count", 0) + 1
        
        # Увеличиваем счетчик сообщений за час
        users[user_id_str]["hourly_messages"] = users[user_id_str].get("hourly_messages", 0) + 1
        
        users[user_id_str]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
        await save_users(users)
        
        # Проверяем и начисляем проценты
        await check_and_apply_bank_interest(user_id)
        
        return True
    return False

async def get_user_data(user_id: int):
    """Получает данные пользователя."""
    users = await load_users()
    return users.get(str(user_id))

# ----------------------------------- Хэндлеры команд -----------------------------------

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 🚀 /start | {user_info} | {user.full_name}")
    
    user_name = message.from_user.first_name
    
    # Создаем инлайн-кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Команды", url="https://t.me/ReWorksAizen/28")
    builder.button(text="👑 Владелец", url="https://t.me/MaiNerHanzo")
    builder.adjust(1)

    await message.answer(
        f"👋 Привет, {user_name}!\n"
        f"💰 Это бот с интересными командами и играми.\n\n"
        f"✅ Ты получишь за регистрацию в боте 1000 msg!\n"
        f"📝 Регистрация: <code>.имя ТвоеИмя</code>\n"
        f"🏦 Банковская система:\n"
        f"💹 1% в час на остаток в банке (нужно 50 сообщений за час)\n"
        f"🕐 Начисление в 00 минут каждого часа (Красноярское время UTC+7)",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    print(f"  └─ ✅ Приветствие отправлено")



def calculate_level(msg_count):
    """
    Рассчитывает уровень и прогресс на основе количества сообщений.
    Возвращает (level, next_level_cost, progress, need_for_next)
    """
    total_msg = msg_count - 1000  # Вычитаем стартовый бонус
    
    if total_msg < 0:
        return 1, 200, 0, 200
    
    level = 1
    remaining = total_msg
    
    # 1-10 уровень (по 200)
    for lvl in range(1, 11):
        if remaining < 200:
            return lvl, 200, remaining, 200
        remaining -= 200
        level = lvl + 1
    
    # 11-30 уровень (по 300)
    for lvl in range(11, 31):
        if remaining < 300:
            return lvl, 300, remaining, 300
        remaining -= 300
        level = lvl + 1
    
    # 31-50 уровень (по 500)
    for lvl in range(31, 51):
        if remaining < 500:
            return lvl, 500, remaining, 500
        remaining -= 500
        level = lvl + 1
    
    # 51-100 уровень (по 700)
    for lvl in range(51, 101):
        if remaining < 700:
            return lvl, 700, remaining, 700
        remaining -= 700
        level = lvl + 1
    
    # 101-300 уровень (по 1000)
    for lvl in range(101, 301):
        if remaining < 1000:
            return lvl, 1000, remaining, 1000
        remaining -= 1000
        level = lvl + 1
    
    # 301-500 уровень (по 2000)
    for lvl in range(301, 501):
        if remaining < 2000:
            return lvl, 2000, remaining, 2000
        remaining -= 2000
        level = lvl + 1
    
    # 501-1000 уровень (по 3000)
    for lvl in range(501, 1001):
        if remaining < 3000:
            return lvl, 3000, remaining, 3000
        remaining -= 3000
        level = lvl + 1
    
    # Выше 1000 уровня
    while remaining >= 3000:
        remaining -= 3000
        level += 1
    
    return level, 3000, remaining, 3000

def get_level_emoji(level):
    """Возвращает эмодзи в зависимости от уровня."""
    if level < 10:
        return "🌱"  # Новичок
    elif level < 30:
        return "🌿"  # Растущий
    elif level < 50:
        return "🍀"  # Опытный
    elif level < 100:
        return "⭐"  # Звезда
    elif level < 300:
        return "👑"  # Король
    elif level < 500:
        return "🔥"  # Легенда
    elif level < 1000:
        return "⚡"  # Элита
    else:
        return "💎"  # Бог

@dp.message(F.text == ".ранк")
async def cmd_dot_rank(message: Message):
    """Показывает ранг и уровень пользователя."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 📊 .ранк | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        print(f"  └─ ❌ Пользователь не зарегистрирован")
        return
    
    user_data = await get_user_data(message.from_user.id)
    msg_count = user_data.get('msg_count', 1000)
    
    # Рассчитываем уровень
    level, next_cost, progress, need_for_next = calculate_level(msg_count)
    level_emoji = get_level_emoji(level)
    
    # Рассчитываем прогресс в процентах (как в банке)
    progress_percent = int((progress / need_for_next) * 10) if need_for_next > 0 else 0
    progress_bar = "▰" * progress_percent + "▱" * (10 - progress_percent)
    
    # Проценты для отображения
    percent_display = int((progress / need_for_next) * 100) if need_for_next > 0 else 0
    
    # Получаем общее количество сообщений (без стартового бонуса)
    total_messages = msg_count - 1000
    if total_messages < 0:
        total_messages = 0
    
    # Формируем текст ранга
    rank_text = (
        f"📊 <b>Ранг пользователя</b>\n\n"
        f"{level_emoji} <b>Уровень: {level}</b>\n"
        f"👤 <b>Имя:</b> {user_data.get('registered_name', 'Не указано')}\n"
        f"📝 <b>Сообщений:</b> {total_messages}\n\n"
        f"📈 <b>До {level + 1} уровня:</b>\n"
        f"└─ {progress_bar} {percent_display}%\n"
        f"└─ {progress} / {need_for_next} msg\n"
    )
    
    try:
        photos = await bot.get_user_profile_photos(message.from_user.id)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            await message.answer_photo(
                photo=file_id,
                caption=rank_text,
                parse_mode="HTML"
            )
            print(f"  └─ ✅ Ранг с аватаркой отправлен | Уровень: {level}")
        else:
            await message.answer(rank_text, parse_mode="HTML")
            print(f"  └─ ✅ Ранг отправлен | Уровень: {level}")
    except Exception as e:
        await message.answer(rank_text, parse_mode="HTML")
        print(f"  └─ ⚠️ Ранг отправлен (ошибка фото: {e}) | Уровень: {level}")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

class TicTacToeGame(StatesGroup):
    waiting_for_opponent = State()
    game_active = State()

# Хранилище активных игр
active_games = {}

@dp.message(F.text.startswith(".кн"))
async def cmd_tictactoe(message: Message, state: FSMContext):
    """Начинает игру в крестики-нолики с другим игроком."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    
    if not await check_registration(message):
        return
    
    # Парсим команду: .кн @username [ставка]
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ Неправильный формат!\n"
            "Использование: <code>.кн @username [ставка]</code>\n"
            "Пример: <code>.кн @durov 100</code>",
            parse_mode="HTML"
        )
        return
    
    # Получаем username оппонента
    opponent_username = parts[1].replace('@', '')
    if not opponent_username:
        await message.answer("❌ Укажи username игрока (например: @username)")
        return
    
    # Парсим ставку (если есть)
    bet = 0
    if len(parts) >= 3:
        try:
            bet = int(parts[2])
            if bet <= 0:
                await message.answer("❌ Ставка должна быть положительным числом!")
                return
        except ValueError:
            await message.answer("❌ Ставка должна быть числом!")
            return
    
    # Ищем оппонента по username в базе
    users = await load_users()
    opponent_id = None
    opponent_data = None
    
    for uid, data in users.items():
        if data.get('username', '').lower() == opponent_username.lower():
            opponent_id = uid
            opponent_data = data
            break
    
    if not opponent_id:
        await message.answer(f"❌ Пользователь @{opponent_username} не зарегистрирован в боте!")
        return
    
    if str(opponent_id) == str(message.from_user.id):
        await message.answer("❌ Нельзя играть с самим собой!")
        return
    
    # Проверяем балансы при наличии ставки
    if bet > 0:
        sender_data = await get_user_data(message.from_user.id)
        if sender_data["msg_count"] < bet:
            await message.answer(f"❌ У тебя недостаточно msg! Твой баланс: {sender_data['msg_count']} msg")
            return
        
        if opponent_data["msg_count"] < bet:
            await message.answer(f"❌ У @{opponent_username} недостаточно msg! Его баланс: {opponent_data['msg_count']} msg")
            return
    
    # Создаем игру (пока в ожидании подтверждения)
    game_id = f"{message.from_user.id}_{opponent_id}_{datetime.now().timestamp()}"
    
    # Создаем клавиатуру для подтверждения
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять", callback_data=f"ttt_accept_{game_id}")
    builder.button(text="❌ Отклонить", callback_data=f"ttt_decline_{game_id}")
    builder.adjust(2)
    
    # Отправляем приглашение оппоненту
    await message.answer(
        f"🎮 <b>Приглашение в крестики-нолики</b>\n\n"
        f"Игрок X: {message.from_user.first_name} (@{message.from_user.username})\n"
        f"Игрок O: {opponent_data['registered_name']} (@{opponent_username})\n"
        f"{f'💰 Ставка: {bet} msg' if bet > 0 else '🎮 Игра без ставки'}\n\n"
        f"@{opponent_username}, прими вызов!",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    
    # Сохраняем игру в ожидании
    active_games[game_id] = {
        'player_x': message.from_user.id,
        'player_x_name': message.from_user.first_name,
        'player_x_username': message.from_user.username,
        'player_o': int(opponent_id),
        'player_o_name': opponent_data['registered_name'],
        'player_o_username': opponent_username,
        'bet': bet,
        'status': 'waiting',  # waiting, active, finished
        'creator_id': message.from_user.id,
        'chat_id': message.chat.id
    }
    
    print(f"\n[{current_time}] 🎮 .кн | {user_info} пригласил @{opponent_username} | Ставка: {bet}")

@dp.callback_query(F.data.startswith('ttt_accept'))
async def accept_game(callback: CallbackQuery, state: FSMContext):
    """Принимает приглашение в игру."""
    game_id = callback.data.replace('ttt_accept_', '')
    
    if game_id not in active_games:
        await callback.answer("❌ Игра уже неактуальна!")
        return
    
    game = active_games[game_id]
    
    # Проверяем, что принимает именно тот, кого пригласили
    if callback.from_user.id != game['player_o']:
        await callback.answer("❌ Это не твое приглашение!")
        return
    
    if game['status'] != 'waiting':
        await callback.answer("❌ Игра уже начата или завершена!")
        return
    
    # Списываем ставки у обоих
    if game['bet'] > 0:
        users = await load_users()
        users[str(game['player_x'])]["msg_count"] -= game['bet']
        users[str(game['player_o'])]["msg_count"] -= game['bet']
        await save_users(users)
    
    # Обновляем статус игры
    game['status'] = 'active'
    game['board'] = [' '] * 9
    game['current_turn'] = game['player_x']  # Крестики ходят первыми
    game['message_id'] = None
    
    # Создаем игровое поле с кнопками
    await update_game_board(callback.message, game, game_id)
    
    await callback.answer("✅ Игра началась!")

@dp.callback_query(F.data.startswith('ttt_decline'))
async def decline_game(callback: CallbackQuery):
    """Отклоняет приглашение в игру."""
    game_id = callback.data.replace('ttt_decline_', '')
    
    if game_id in active_games:
        game = active_games[game_id]
        if callback.from_user.id == game['player_o']:
            await callback.message.edit_text(
                f"❌ Игрок @{game['player_o_username']} отклонил приглашение.",
                parse_mode="HTML"
            )
            del active_games[game_id]
    
    await callback.answer()

@dp.callback_query(F.data.startswith('ttt_move_'))
async def process_move(callback: CallbackQuery):
    """Обрабатывает ход в игре."""
    # Формат: ttt_move_GAMEID_POSITION
    data = callback.data.replace('ttt_move_', '')
    
    # Находим последнее нижнее подчеркивание, которое отделяет позицию
    last_underscore = data.rfind('_')
    if last_underscore == -1:
        await callback.answer("❌ Ошибка формата данных")
        return
    
    game_id = data[:last_underscore]
    position_str = data[last_underscore + 1:]
    
    try:
        position = int(position_str)
    except ValueError:
        await callback.answer("❌ Ошибка позиции")
        return
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!")
        return
    
    game = active_games[game_id]
    
    if game['status'] != 'active':
        await callback.answer("❌ Игра уже завершена!")
        return
    
    # Проверяем, что ходит нужный игрок
    if callback.from_user.id != game['current_turn']:
        await callback.answer("❌ Сейчас не твой ход!")
        return
    
    # Проверяем, что клетка свободна
    if game['board'][position] != ' ':
        await callback.answer("❌ Эта клетка уже занята!")
        return
    
    # Определяем символ игрока
    symbol_simple = 'X' if callback.from_user.id == game['player_x'] else 'O'
    
    # Делаем ход
    game['board'][position] = symbol_simple
    
    # Проверяем победителя
    winner = check_winner(game['board'])
    
    if winner:
        # Игра завершена
        game['status'] = 'finished'
        
        if winner == 'draw':
            # Ничья - возвращаем ставки
            if game['bet'] > 0:
                users = await load_users()
                users[str(game['player_x'])]["msg_count"] += game['bet']
                users[str(game['player_o'])]["msg_count"] += game['bet']
                await save_users(users)
            
            result_text = "🤝 Ничья! Ставки возвращены."
            winner_id = None
        else:
            # Есть победитель
            winner_id = game['player_x'] if winner == 'X' else game['player_o']
            winner_name = game['player_x_name'] if winner == 'X' else game['player_o_name']
            
            # Начисляем выигрыш
            if game['bet'] > 0:
                users = await load_users()
                # Победитель получает общий банк (ставки обоих)
                users[str(winner_id)]["msg_count"] += game['bet'] * 2
                await save_users(users)
            
            result_text = f"🏆 Победил {winner_name}!"
        
        # Показываем финальное поле
        await show_final_board(callback.message, game, result_text, winner_id)
        await callback.answer("🎮 Игра завершена!")
        
        # Удаляем игру из активных
        del active_games[game_id]
        return
    
    # Меняем ход
    game['current_turn'] = game['player_o'] if callback.from_user.id == game['player_x'] else game['player_x']
    
    # Обновляем поле
    await update_game_board(callback.message, game, game_id)
    await callback.answer()

async def update_game_board(message: types.Message, game: dict, game_id: str):
    """Обновляет игровое поле с кнопками."""
    board = game['board']
    current_turn_name = game['player_x_name'] if game['current_turn'] == game['player_x'] else game['player_o_name']
    current_turn_symbol = '❌' if game['current_turn'] == game['player_x'] else '⭕'
    
    # Создаем клавиатуру 3x3
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            pos = i + j
            cell = board[pos]
            
            if cell == ' ':
                # Пустая клетка - кнопка с номером
                text = f"{pos + 1}"
                callback_data = f"ttt_move_{game_id}_{pos}"
            elif cell == 'X':
                text = "❌"
                callback_data = "ignore"
            else:  # 'O'
                text = "⭕"
                callback_data = "ignore"
            
            row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
        keyboard.append(row)
    
    # Добавляем кнопку выхода
    keyboard.append([InlineKeyboardButton(text="🚪 Выйти из игры", callback_data=f"ttt_exit_{game_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    # Формируем текст игры
    game_text = (
        f"🎮 <b>Крестики-нолики</b>\n\n"
        f"❌ {game['player_x_name']} (@{game['player_x_username']})\n"
        f"⭕ {game['player_o_name']} (@{game['player_o_username']})\n"
        f"{f'💰 Ставка: {game["bet"]} msg' if game['bet'] > 0 else '🎮 Игра без ставки'}\n\n"
        f"⚡ Ходит: {current_turn_name} {current_turn_symbol}"
    )
    
    await message.edit_text(game_text, reply_markup=markup, parse_mode="HTML")

async def show_final_board(message: types.Message, game: dict, result_text: str, winner_id: int = None):
    """Показывает финальное поле после окончания игры."""
    board = game['board']
    
    # Создаем финальную клавиатуру (все кнопки неактивны)
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            pos = i + j
            cell = board[pos]
            
            if cell == ' ':
                text = "⬜"
            elif cell == 'X':
                text = "❌"
            else:  # 'O'
                text = "⭕"
            
            row.append(InlineKeyboardButton(text=text, callback_data="ignore"))
        keyboard.append(row)
    
    # Добавляем кнопку информации
    if winner_id:
        winner_name = game['player_x_name'] if winner_id == game['player_x'] else game['player_o_name']
        keyboard.append([InlineKeyboardButton(text=f"🏆 Победитель: {winner_name}", callback_data="ignore")])
    else:
        keyboard.append([InlineKeyboardButton(text="🤝 Ничья", callback_data="ignore")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    game_text = (
        f"🎮 <b>Крестики-нолики</b>\n\n"
        f"❌ {game['player_x_name']} (@{game['player_x_username']})\n"
        f"⭕ {game['player_o_name']} (@{game['player_o_username']})\n"
        f"{f'💰 Ставка: {game["bet"]} msg' if game['bet'] > 0 else '🎮 Игра без ставки'}\n\n"
        f"📊 <b>{result_text}</b>"
    )
    
    await message.edit_text(game_text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith('ttt_exit_'))
async def exit_game(callback: CallbackQuery):
    """Выход из игры (сдача)."""
    game_id = callback.data.replace('ttt_exit_', '')
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена!")
        return
    
    game = active_games[game_id]
    
    if game['status'] != 'active':
        await callback.answer()
        return
    
    # Тот, кто вышел - проигрывает
    loser_id = callback.from_user.id
    winner_id = game['player_o'] if loser_id == game['player_x'] else game['player_x']
    
    winner_name = game['player_o_name'] if winner_id == game['player_o'] else game['player_x_name']
    
    # Начисляем выигрыш победителю
    if game['bet'] > 0:
        users = await load_users()
        users[str(winner_id)]["msg_count"] += game['bet'] * 2
        await save_users(users)
    
    # Завершаем игру
    game['status'] = 'finished'
    
    # Показываем финальное поле
    await show_final_board(
        callback.message, 
        game, 
        f"🏆 Победил {winner_name} (соперник вышел)",
        winner_id
    )
    
    await callback.answer("🚪 Ты вышел из игры")
    
    # Удаляем игру из активных
    del active_games[game_id]

@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    """Игнорирует нажатия на неактивные кнопки."""
    await callback.answer()

def check_winner(board):
    """Проверяет, есть ли победитель."""
    win_combinations = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Горизонтали
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Вертикали
        [0, 4, 8], [2, 4, 6]              # Диагонали
    ]
    
    for combo in win_combinations:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != ' ':
            return board[combo[0]]
    
    if ' ' not in board:
        return 'draw'
    
    return None

@dp.message(F.text.startswith(".имя"))
async def cmd_dot_name(message: Message):
    """Обработчик команды .имя (регистрация)."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 📝 .имя | {user_info} | {user.full_name}")
    
    command_parts = message.text.split(maxsplit=1)
    name_text = command_parts[1] if len(command_parts) > 1 else None
    
    user_data, is_new = await register_or_update_user(message, name_text)
    
    if is_new:
        await message.answer(
            f"✅ <b>Регистрация успешна!</b>\n"
            f"└─ Твое имя: {user_data['registered_name']}\n\n"
            f"💰 <b>+1000 msg</b> за регистрацию!\n"
            f"🏦 <b>+1 ячейка в банке</b> (лимит 5000 msg)\n"
            f"💳 Текущий баланс: <b>{user_data['msg_count']} msg</b>",
            parse_mode="HTML"
        )
        print(f"  └─ ✅ Новый пользователь | Имя: {user_data['registered_name']} | +1000 msg")
    else:
        await message.answer(
    f"└─ Твое новое имя: {user_data['registered_name']}\n\n",
    parse_mode="HTML"
)

@dp.message(F.text == ".команды")
async def cmd_dot_commands(message: Message):
    """Показывает список команд через инлайн-кнопку."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    print(f"\n[{current_time}] 📋 .команды | {user_info} | {user.full_name}")
    
    # Создаем инлайн-кнопки
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📋 Список команд", 
        url="https://t.me/ReWorksAizen/28"
    )
    builder.button(
        text="👑 Владелец", 
        url="https://t.me/MaiNerHanzo"
    )
    builder.adjust(1)  # По одной в ряд
    
    await message.answer(
        "📚 <b>Команды бота</b>\n\n"
        "Нажми на кнопку, чтобы открыть полный список:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    print(f"  └─ ✅ Отправлена ссылка на команды")

# ----------------------------------- Команда перевода -----------------------------------
# Добавь в структуру пользователя:
# "friends": [],           # Список ID друзей
# "friend_requests": []    # Входящие заявки в друзья

# ----------------------------------- Команда подружиться (отправить заявку) -----------------------------------
# ----------------------------------- Команда подружиться (отправить заявку) -----------------------------------
@dp.message(F.text.startswith(".подружиться"))
async def cmd_friend_request(message: Message):
    """Отправляет заявку в друзья (предложение в чат, результат в ЛС)."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    print(f"\n[{current_time}] 🤝 .подружиться | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Парсим команду: .подружиться @username
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "❌ <b>Неправильный формат!</b>\n"
            "Использование: <code>.подружиться @username</code>\n"
            "Пример: <code>.подружиться @durov</code>",
            parse_mode="HTML"
        )
        return
    
    # Получаем username потенциального друга
    target_username = parts[1].replace('@', '')
    if not target_username:
        await message.answer("❌ Укажи username пользователя (например: @username)")
        return
    
    # Ищем пользователя по username в базе
    users = await load_users()
    target_id = None
    target_data = None
    
    for uid, data in users.items():
        if data.get('username', '').lower() == target_username.lower():
            target_id = uid
            target_data = data
            break
    
    if not target_id:
        await message.answer(f"❌ Пользователь @{target_username} не зарегистрирован в боте!")
        return
    
    if str(target_id) == str(message.from_user.id):
        await message.answer("❌ Нельзя отправить заявку самому себе!")
        return
    
    # Получаем данные отправителя
    sender_id = str(message.from_user.id)
    sender_data = users[sender_id]
    
    # Проверяем, есть ли уже в друзьях
    if "friends" not in sender_data:
        sender_data["friends"] = []
    
    if target_id in sender_data["friends"]:
        await message.answer(f"❌ Пользователь @{target_username} уже у тебя в друзьях!")
        return
    
    # Проверяем, есть ли уже отправленная заявка
    if "friend_requests_sent" not in sender_data:
        sender_data["friend_requests_sent"] = []
    
    if target_id in sender_data["friend_requests_sent"]:
        await message.answer(f"⏳ Ты уже отправил заявку @{target_username}. Ожидай ответа!")
        return
    
    # Добавляем заявку в исходящие
    sender_data["friend_requests_sent"].append(target_id)
    
    # Добавляем заявку во входящие получателя
    if "friend_requests" not in target_data:
        target_data["friend_requests"] = []
    
    target_data["friend_requests"].append(sender_id)
    
    # Сохраняем изменения
    await save_users(users)
    
    # Получаем имена
    sender_name = sender_data.get('registered_name', message.from_user.full_name)
    target_name = target_data.get('registered_name', f"@{target_username}")
    
    # Создаем клавиатуру для ответа в том же чате
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ПРИНЯТЬ", callback_data=f"friend_accept_{sender_id}")
    builder.button(text="❌ ОТКЛОНИТЬ", callback_data=f"friend_decline_{sender_id}")
    builder.adjust(2)
    
    # Отправляем предложение в тот же чат, упоминая получателя
    await message.answer(
        f"🤝 <b>Заявка в друзья</b>\n\n"
        f"Пользователь {sender_name} хочет добавить тебя в друзья!\n"
        f"💞 Комиссия на переводы с друзьями: 4%\n\n"
        f"@{target_username}, прими заявку:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    
    print(f"  └─ ✅ Заявка отправлена @{target_username} (ожидание ответа в чате)")

# ----------------------------------- Принять заявку -----------------------------------
@dp.callback_query(F.data.startswith('friend_accept_'))
async def accept_friend_request(callback: CallbackQuery):
    """Принимает заявку в друзья."""
    sender_id = callback.data.replace('friend_accept_', '')
    receiver_id = str(callback.from_user.id)
    
    users = await load_users()
    
    if sender_id not in users or receiver_id not in users:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    sender_data = users[sender_id]
    receiver_data = users[receiver_id]
    
    # Проверяем, есть ли заявка
    if "friend_requests" not in receiver_data:
        receiver_data["friend_requests"] = []
    
    if sender_id not in receiver_data["friend_requests"]:
        await callback.answer("❌ Заявка уже неактуальна!", show_alert=True)
        return
    
    # Добавляем в друзья
    if "friends" not in sender_data:
        sender_data["friends"] = []
    if "friends" not in receiver_data:
        receiver_data["friends"] = []
    
    if sender_id not in receiver_data["friends"]:
        receiver_data["friends"].append(sender_id)
    if receiver_id not in sender_data["friends"]:
        sender_data["friends"].append(receiver_id)
    
    # Удаляем заявки
    receiver_data["friend_requests"].remove(sender_id)
    
    if "friend_requests_sent" in sender_data and receiver_id in sender_data["friend_requests_sent"]:
        sender_data["friend_requests_sent"].remove(receiver_id)
    
    await save_users(users)
    
    # Получаем имена
    sender_name = sender_data.get('registered_name', f"ID: {sender_id}")
    receiver_name = receiver_data.get('registered_name', callback.from_user.full_name)
    
    # Редактируем сообщение с заявкой (в чате)
    await callback.message.edit_text(
        f"✅ <b>Заявка принята!</b>\n\n"
        f"{receiver_name} принял заявку в друзья от {sender_name}!",
        parse_mode="HTML"
    )
    
    # Отправляем уведомление отправителю в ЛС
    try:
        await callback.bot.send_message(
            int(sender_id),
            f"🎉 <b>Заявка принята!</b>\n\n"
            f"Пользователь {receiver_name} принял твою заявку в друзья!\n"
            f"💞 Теперь вы друзья!",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"  └─ ⚠️ Не удалось отправить уведомление в ЛС: {e}")
    
    await callback.answer("✅ Дружба подтверждена!")

# ----------------------------------- Отклонить заявку -----------------------------------
@dp.callback_query(F.data.startswith('friend_decline_'))
async def decline_friend_request(callback: CallbackQuery):
    """Отклоняет заявку в друзья."""
    sender_id = callback.data.replace('friend_decline_', '')
    receiver_id = str(callback.from_user.id)
    
    users = await load_users()
    
    if sender_id not in users or receiver_id not in users:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    receiver_data = users[receiver_id]
    
    # Проверяем, есть ли заявка
    if "friend_requests" not in receiver_data:
        receiver_data["friend_requests"] = []
    
    if sender_id not in receiver_data["friend_requests"]:
        await callback.answer("❌ Заявка уже неактуальна!", show_alert=True)
        return
    
    # Удаляем заявку
    receiver_data["friend_requests"].remove(sender_id)
    
    # Удаляем из исходящих у отправителя
    sender_data = users[sender_id]
    if "friend_requests_sent" in sender_data and receiver_id in sender_data["friend_requests_sent"]:
        sender_data["friend_requests_sent"].remove(receiver_id)
    
    await save_users(users)
    
    # Получаем имя отклонившего
    receiver_name = receiver_data.get('registered_name', callback.from_user.full_name)
    
    # Редактируем сообщение с заявкой (в чате)
    await callback.message.edit_text(
        f"❌ <b>Заявка отклонена</b>\n\n"
        f"{receiver_name} отклонил заявку в друзья.",
        parse_mode="HTML"
    )
    
    # Отправляем уведомление отправителю в ЛС
    try:
        await callback.bot.send_message(
            int(sender_id),
            f"💔 <b>Заявка отклонена</b>\n\n"
            f"Пользователь {receiver_name} отклонил твою заявку в друзья.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"  └─ ⚠️ Не удалось отправить уведомление в ЛС: {e}")
    
    await callback.answer("❌ Заявка отклонена")

# ----------------------------------- Команда список заявок -----------------------------------
@dp.message(F.text == ".заявки")
async def cmd_friend_requests(message: Message):
    """Показывает входящие заявки в друзья."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    print(f"\n[{current_time}] 📨 .заявки | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    users = await load_users()
    user_data = users[str(message.from_user.id)]
    
    requests = user_data.get("friend_requests", [])
    
    if not requests:
        await message.answer(
            "📨 <b>Входящие заявки</b>\n\n"
            "У тебя нет входящих заявок в друзья.",
            parse_mode="HTML"
        )
        return
    
    # Формируем список заявок
    requests_text = "📨 <b>Входящие заявки в друзья</b>\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for i, requester_id in enumerate(requests, 1):
        requester_data = users.get(str(requester_id))
        if requester_data:
            requester_name = requester_data.get('registered_name', 'Неизвестно')
            requester_username = requester_data.get('username', '')
            username_text = f" (@{requester_username})" if requester_username else ""
            requests_text += f"{i}. {requester_name}{username_text}\n"
            
            # Добавляем кнопки для каждой заявки
            builder.button(
                text=f"✅ {requester_name}", 
                callback_data=f"friend_accept_{requester_id}"
            )
            builder.button(
                text=f"❌ Отклонить", 
                callback_data=f"friend_decline_{requester_id}"
            )
            builder.adjust(2)
    
    await message.answer(requests_text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ----------------------------------- Обновленная команда список друзей -----------------------------------
@dp.message(F.text == ".друзья")
async def cmd_friends_list(message: Message):
    """Показывает список друзей."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    print(f"\n[{current_time}] 👥 .друзья | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    users = await load_users()
    user_data = users[str(message.from_user.id)]
    
    friends_list = user_data.get("friends", [])
    requests_count = len(user_data.get("friend_requests", []))
    
    if not friends_list:
        friends_text = "👥 <b>Список друзей</b>\n\n"
        friends_text += "У тебя пока нет друзей.\n"
        friends_text += "Добавь друга: <code>.подружиться @username</code>\n"
        
        if requests_count > 0:
            friends_text += f"\n📨 У тебя {requests_count} входящих заявок! (.заявки)"
        
        await message.answer(friends_text, parse_mode="HTML")
        return
    
    # Формируем список друзей
    friends_text = f"👥 <b>Твои друзья ({len(friends_list)})</b>\n\n"
    
    for i, friend_id in enumerate(friends_list, 1):
        friend_data = users.get(str(friend_id))
        if friend_data:
            friend_name = friend_data.get('registered_name', 'Неизвестно')
            friend_username = friend_data.get('username', '')
            username_text = f" (@{friend_username})" if friend_username else ""
            friends_text += f"{i}. {friend_name}{username_text}\n"
        else:
            friends_text += f"{i}. Пользователь ID: {friend_id} (не найден)\n"
    
    friends_text += f"\n💞 Комиссия на переводы с друзьями: 4%"
    
    if requests_count > 0:
        friends_text += f"\n📨 У тебя {requests_count} входящих заявок! (.заявки)"
    
    await message.answer(friends_text, parse_mode="HTML")

import random
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

import random
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

# Словарь для хранения времени последней игры каждого пользователя
user_cooldowns = {}

@dp.message(F.text.startswith(".казино"))
async def cmd_casino(message: Message):
    """Начинает игру в казино."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ)
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 🎰 .казино | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Проверяем кулдаун
    user_id = message.from_user.id
    if user_id in user_cooldowns:
        last_game = user_cooldowns[user_id]
        time_diff = (current_time - last_game).total_seconds()
        if time_diff < 20:
            remaining = int(20 - time_diff)
            await message.answer(
                f"⏳ <b>Подожди {remaining} сек.</b>\n"
                f"Казино отдыхает между играми...",
                parse_mode="HTML"
            )
            return
    
    # Парсим ставку
    parts = message.text.split()
    bet = 100  # Ставка по умолчанию
    
    if len(parts) == 2:
        try:
            bet = int(parts[1])
            if bet <= 0:
                await message.answer("❌ Ставка должна быть положительным числом!")
                return
        except ValueError:
            await message.answer("❌ Ставка должна быть числом!\nИспользование: <code>.казино 100</code>", parse_mode="HTML")
            return
    
    # Проверяем баланс
    user_data = await get_user_data(message.from_user.id)
    if user_data["msg_count"] < bet:
        await message.answer(
            f"❌ <b>Недостаточно msg!</b>\n"
            f"└─ Твой баланс: {user_data['msg_count']} msg\n"
            f"└─ Требуется: {bet} msg",
            parse_mode="HTML"
        )
        return
    
    # Запускаем игру
    await play_casino(message, bet)

async def play_casino(message: Message, bet: int):
    """Основная логика казино с красивым оформлением."""
    user_id = message.from_user.id
    
    # Множители и шансы
    multipliers = [
        (0.5, 25, "⚫"),   # 25% шанс проиграть половину
        (0.8, 30, "⚪"),   # 30% шанс проиграть 20%
        (1.0, 20, "🔵"),   # 20% шанс вернуть ставку
        (1.2, 25, "🟢"),   # 25% шанс
        (1.4, 15, "🟣"),   # 15% шанс
        (1.8, 8,  "🟡"),   # 8% шанс
        (2.0, 4,  "🟠"),   # 4% шанс
        (3.0, 2,  "🔴"),   # 2% шанс
        (5.0, 0.8, "💎"),  # 0.8% шанс
        (10.0, 0.2, "👑")  # 0.2% шанс
    ]
    
    # Выбираем множитель
    rand = random.uniform(0, 100)
    cumulative = 0
    selected_multiplier = 1.0
    selected_color = "⚫"
    selected_chance = 0
    
    for mult, chance, color in multipliers:
        cumulative += chance
        if rand <= cumulative:
            selected_multiplier = mult
            selected_color = color
            selected_chance = chance
            break
    
    # Загружаем пользователя
    users = await load_users()
    user_id_str = str(user_id)
    
    # Списываем ставку
    users[user_id_str]["msg_count"] -= bet
    
    # Рассчитываем выигрыш
    win_amount = int(bet * selected_multiplier)
    users[user_id_str]["msg_count"] += win_amount
    
    # Обновляем время активности
    users[user_id_str]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
    await save_users(users)
    
    # Обновляем кулдаун
    user_cooldowns[user_id] = datetime.now(KRASNOYARSK_TZ)
    
    # Определяем результат
    profit = win_amount - bet
    
    if selected_multiplier < 1.0:
        result_emoji = "💔 ПРОИГРЫШ"
        result_color = "🔴"
    elif selected_multiplier == 1.0:
        result_emoji = "🔄 ВОЗВРАТ"
        result_color = "🔵"
    elif selected_multiplier < 2.0:
        result_emoji = "✅ ВЫИГРЫШ"
        result_color = "🟢"
    elif selected_multiplier < 5.0:
        result_emoji = "⚡ БОЛЬШОЙ ВЫИГРЫШ"
        result_color = "🟡"
    else:
        result_emoji = "👑 ДЖЕКПОТ"
        result_color = "💎"
    
    # Создаем красивый результат без рамок
    result_text = (
        f"🎰 <b>КАЗИНО</b> 🎰\n\n"
        f"{result_color} <b>{result_emoji}</b>\n\n"
        f"💰 <b>Ставка:</b> {bet} msg\n"
        f"{selected_color} <b>Множитель:</b> x{selected_multiplier}\n"
        f"📊 <b>Шанс:</b> {selected_chance}%\n"
        f"💎 <b>Выигрыш:</b> {win_amount} msg\n"
    )
    
    # Добавляем информацию о профите
    if profit > 0:
        result_text += f"✨ <b>Профит:</b> +{profit} msg\n"
    elif profit < 0:
        result_text += f"💔 <b>Потеря:</b> {profit} msg\n"
    else:
        result_text += f"🔄 <b>В нуле:</b> 0 msg\n"
    
    result_text += f"\n💳 <b>Новый баланс:</b> {users[user_id_str]['msg_count']} msg"
    
    # Создаем кнопку "Шансы"
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 ШАНСЫ КАЗИНО", callback_data="casino_stats")
    
    # Отправляем результат
    await message.answer(
        result_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "casino_stats")
async def casino_stats(callback: CallbackQuery):
    """Показывает статистику казино."""
    stats_text = (
        f"🎰 <b>ШАНСЫ КАЗИНО</b> 🎰\n\n"
        f"⚫ x0.5  — 25.0%\n"
        f"⚪ x0.8  — 30.0%\n"
        f"🔵 x1.0  — 20.0%\n"
        f"🟢 x1.2  — 25.0%\n"
        f"🟣 x1.4  — 15.0%\n"
        f"🟡 x1.8  —  8.0%\n"
        f"🟠 x2.0  —  4.0%\n"
        f"🔴 x3.0  —  2.0%\n"
        f"💎 x5.0  —  0.8%\n"
        f"👑 x10.0 —  0.2%\n\n"
        f"⏳ Кулдаун: 20 секунд"
    )
    
    await callback.message.answer(stats_text, parse_mode="HTML")
    await callback.answer()

# --- Командаы только для владельца ---

@dp.message(F.text.startswith(".сделай"))
async def cmd_set_balance(message: Message):
    """Устанавливает баланс пользователя (только для владельца)."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    
    # Проверяем, является ли пользователь владельцем
    if user.id != OWNER_ID:
        print(f"\n[{current_time}] ⚠️ .сделай | {user_info} | {user.full_name} | ПОПЫТКА НЕСАНКЦИОНИРОВАННОГО ДОСТУПА")
        await message.answer("❌ У тебя нет прав на использование этой команды!")
        return
    
    # Парсим команду: .сделай @username сумма
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "❌ Неправильный формат\nИспользование: <code>.сделай @username сумма</code>",
            parse_mode="HTML"
        )
        return
    
    # Получаем username пользователя
    target_username = parts[1].replace('@', '')
    if not target_username:
        await message.answer("❌ Укажи username пользователя (например: @username)")
        return
    
    # Парсим сумму
    try:
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    # Ищем пользователя по username в базе
    users = await load_users()
    target_id = None
    target_data = None
    
    for uid, data in users.items():
        if data.get('username', '').lower() == target_username.lower():
            target_id = uid
            target_data = data
            break
    
    if not target_id:
        await message.answer(f"❌ Пользователь @{target_username} не зарегистрирован в боте!")
        return
    
    # Устанавливаем новый баланс (может быть любым, даже отрицательным)
    old_balance = users[target_id]["msg_count"]
    users[target_id]["msg_count"] = amount
    users[target_id]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
    
    await save_users(users)
    
    # Получаем имя пользователя для красивого вывода
    target_name = target_data.get('registered_name', f"@{target_username}")
    
    # Определяем эмодзи в зависимости от изменения
    if amount > old_balance:
        emoji = "⬆️"
        change = f"+{amount - old_balance}"
    elif amount < old_balance:
        emoji = "⬇️"
        change = f"-{old_balance - amount}"
    else:
        emoji = "⏺️"
        change = "0"
    
    print(f"\n[{current_time}] 🔧 .сделай | {user_info} -> @{target_username} | {old_balance} -> {amount}")
    
    # ИСПРАВЛЕНО: убраны запятые между строками
    await message.answer(
        f"✅ <b>Баланс изменён!</b>\n"
        f"└─ Пользователь: {target_name}\n"
        f"└─ Старый баланс: {old_balance} msg\n"
        f"└─ Новый баланс: {amount} msg\n"
        f"└─ Изменение: {emoji} {change} msg",
        parse_mode="HTML"
    )
    
    # Уведомляем пользователя об изменении баланса
    try:
        await bot.send_message(
            int(target_id),
            f"⚙️ <b>Изменение баланса</b>\n"
            f"└─ Администратор изменил твой баланс\n"
            f"└─ Старый баланс: {old_balance} msg\n"
            f"└─ Новый баланс: {amount} msg\n"
            f"└─ Изменение: {emoji} {change} msg",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"  └─ ⚠️ Не удалось отправить уведомление пользователю: {e}")

import random
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

# Хранилище активных игр
active_mines_games = {}

class MinesGame:
    def __init__(self, user_id, bet):
        self.user_id = user_id
        self.bet = bet
        self.mines = []  # Позиции мин
        self.opened = []  # Открытые клетки
        self.multiplier = 1.0
        self.step = 0
        self.status = 'active'
        self.generate_mines()
    
    def generate_mines(self):
        """Генерирует случайное количество мин (от 3 до 7) в случайных позициях."""
        num_mines = random.randint(3, 7)
        all_positions = list(range(1, 26))  # Номера клеток 1-25
        self.mines = random.sample(all_positions, num_mines)
        print(f"DEBUG: Сгенерировано {num_mines} мин: {self.mines}")
    
    def get_multiplier_for_step(self, step):
        """Возвращает множитель в зависимости от количества ходов."""
        multipliers = {
            1: 1.2,
            2: 1.5,
            3: 2.0,
            4: 3.0
        }
        return multipliers.get(step, 1.0)
    
    def open_cell(self, cell_number):
        """Открывает клетку. Возвращает (success, win_amount, game_over)"""
        if cell_number in self.opened:
            return False, 0, False
        
        if cell_number in self.mines:
            # Попал на мину - проигрыш (теряет 50% ставки)
            self.status = 'lose'
            win_amount = int(self.bet * 0.5)  # Возвращаем 50%
            return True, win_amount, True
        
        # Открываем клетку
        self.opened.append(cell_number)
        self.step += 1
        
        # Проверяем, достигнут ли лимит ходов (4 хода)
        if self.step >= 4:
            self.status = 'win'
            win_amount = int(self.bet * 3.0)  # x3 за 4 хода
            return True, win_amount, True
        
        # Продолжаем игру
        self.status = 'active'
        win_amount = int(self.bet * self.get_multiplier_for_step(self.step))
        return True, win_amount, False

import random
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

# Хранилище активных игр
active_mines_games = {}

class MinesGame:
    def __init__(self, user_id, bet):
        self.user_id = user_id
        self.bet = bet
        self.mines = []  # Позиции мин
        self.opened = []  # Открытые клетки
        self.multiplier = 1.0
        self.step = 0
        self.status = 'active'
        self.message_id = None  # ID сообщения с игрой
        self.chat_id = None     # ID чата
        self.generate_mines()
    
    def generate_mines(self):
        """Генерирует случайное количество мин (от 3 до 7) в случайных позициях."""
        num_mines = random.randint(3, 7)
        all_positions = list(range(1, 26))  # Номера клеток 1-25
        self.mines = random.sample(all_positions, num_mines)
        print(f"DEBUG: Сгенерировано {num_mines} мин: {self.mines}")
    
    def get_multiplier_for_step(self, step):
        """Возвращает множитель в зависимости от количества ходов."""
        multipliers = {
            1: 1.2,
            2: 1.5,
            3: 2.0,
            4: 3.0
        }
        return multipliers.get(step, 1.0)
    
    def open_cell(self, cell_number):
        """Открывает клетку. Возвращает (success, win_amount, game_over)"""
        if cell_number in self.opened:
            return False, 0, False
        
        if cell_number in self.mines:
            # Попал на мину - проигрыш (теряет 50% ставки)
            self.status = 'lose'
            win_amount = int(self.bet * 0.5)  # Возвращаем 50%
            return True, win_amount, True
        
        # Открываем клетку
        self.opened.append(cell_number)
        self.step += 1
        
        # Проверяем, достигнут ли лимит ходов (4 хода)
        if self.step >= 4:
            self.status = 'win'
            win_amount = int(self.bet * 3.0)  # x3 за 4 хода
            return True, win_amount, True
        
        # Продолжаем игру
        self.status = 'active'
        win_amount = int(self.bet * self.get_multiplier_for_step(self.step))
        return True, win_amount, False

@dp.message(F.text.startswith(".мины"))
async def cmd_mines(message: Message):
    """Начинает игру в Мины."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ).strftime("%H:%M")
    print(f"\n[{current_time}] 💣 .мины | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Парсим ставку
    parts = message.text.split()
    bet = 100  # Ставка по умолчанию
    
    if len(parts) == 2:
        try:
            bet = int(parts[1])
            if bet <= 0:
                await message.answer("❌ Ставка должна быть положительным числом!")
                return
        except ValueError:
            await message.answer("❌ Ставка должна быть числом!\nИспользование: <code>.мины 100</code>", parse_mode="HTML")
            return
    
    # Проверяем баланс
    user_data = await get_user_data(message.from_user.id)
    if user_data["msg_count"] < bet:
        await message.answer(
            f"❌ <b>Недостаточно msg!</b>\n"
            f"└─ Твой баланс: {user_data['msg_count']} msg\n"
            f"└─ Требуется: {bet} msg",
            parse_mode="HTML"
        )
        return
    
    # Создаем новую игру
    game = MinesGame(message.from_user.id, bet)
    game.chat_id = message.chat.id
    active_mines_games[message.from_user.id] = game
    
    # Списываем ставку
    users = await load_users()
    users[str(message.from_user.id)]["msg_count"] -= bet
    users[str(message.from_user.id)]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
    await save_users(users)
    
    # Отправляем игровое поле и сохраняем ID сообщения
    sent_message = await send_mines_board(message, game)
    game.message_id = sent_message.message_id

async def send_mines_board(message: Message, game: MinesGame):
    """Отправляет игровое поле с кнопками."""
    
    # Создаем клавиатуру 5x5
    keyboard = []
    
    for row in range(5):
        row_buttons = []
        for col in range(5):
            cell_num = row * 5 + col + 1
            
            if cell_num in game.opened:
                # Открытая клетка (уже походили)
                text = "✅"
                callback_data = "ignore"
            else:
                # Закрытая клетка с номером
                text = f"{cell_num}"
                callback_data = f"mines_open_{cell_num}"
            
            row_buttons.append(InlineKeyboardButton(text=text, callback_data=callback_data))
        keyboard.append(row_buttons)
    
    # Добавляем кнопку выхода
    keyboard.append([InlineKeyboardButton(text="🚪 ЗАВЕРШИТЬ ИГРУ", callback_data="mines_stop")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    # Текущий множитель
    current_multiplier = game.get_multiplier_for_step(game.step + 1) if game.step < 4 else game.multiplier
    
    # Формируем текст
    if game.step == 0:
        progress_text = "🎯 Выбери первую клетку"
    else:
        progress_text = f"📊 Ходов: {game.step}/4 | Множитель: x{current_multiplier}"
    
    board_text = (
        f"💣 <b>МИНЫ</b> 💣\n\n"
        f"💰 Ставка: {game.bet} msg\n"
        f"{progress_text}\n\n"
        f"⚡ <b>Множители:</b>\n"
        f"1 ход — x1.2\n"
        f"2 хода — x1.5\n"
        f"3 хода — x2.0\n"
        f"4 хода — x3.0 💎\n\n"
        f"💥 Попал на мину — возврат 50%\n"
        f"⬜ Клетки с номерами — можно открыть"
    )
    
    # Отправляем или редактируем сообщение
    if hasattr(game, 'message_id') and game.message_id:
        return await message.bot.edit_message_text(
            board_text,
            chat_id=game.chat_id,
            message_id=game.message_id,
            reply_markup=markup,
            parse_mode="HTML"
        )
    else:
        return await message.answer(board_text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith('mines_open_'))
async def process_mines_move(callback: CallbackQuery):
    """Обрабатывает ход в игре Мины."""
    user_id = callback.from_user.id
    
    # Проверяем, есть ли активная игра
    if user_id not in active_mines_games:
        await callback.answer("❌ У тебя нет активной игры!", show_alert=True)
        return
    
    game = active_mines_games[user_id]
    
    if game.status != 'active':
        await callback.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    # Получаем номер клетки
    cell_num = int(callback.data.replace('mines_open_', ''))
    
    # Открываем клетку
    success, win_amount, game_over = game.open_cell(cell_num)
    
    if not success:
        await callback.answer("❌ Эта клетка уже открыта!", show_alert=True)
        return
    
    if game_over:
        # Игра завершена
        if game.status == 'win':
            # Выигрыш
            users = await load_users()
            users[str(user_id)]["msg_count"] += win_amount
            users[str(user_id)]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
            await save_users(users)
            
            # Показываем финальное поле (редактируем)
            await show_final_board(callback.message, game, win_amount, win=True)
            
        else:  # lose
            # Проигрыш (возврат 50%)
            users = await load_users()
            users[str(user_id)]["msg_count"] += win_amount  # win_amount = 50% ставки
            users[str(user_id)]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
            await save_users(users)
            
            # Показываем финальное поле с минами (редактируем)
            await show_final_board(callback.message, game, win_amount, win=False)
        
        # Удаляем игру из активных
        del active_mines_games[user_id]
        
    else:
        # Игра продолжается - редактируем сообщение
        await send_mines_board(callback.message, game)
    
    await callback.answer()

async def show_final_board(message: Message, game: MinesGame, win_amount: int, win: bool):
    """Показывает результат игры с одной кнопкой 'Играть ещё'."""
    
    # Определяем результат
    if win:
        result_text = (
            f"🎉 <b>ТЫ ВЫИГРАЛ!</b> 🎉\n\n"
            f"💰 Ставка: {game.bet} msg\n"
            f"💎 Выигрыш: +{win_amount} msg\n"
            f"💣 Мин на поле: {len(game.mines)}"
        )
    else:
        result_text = (
            f"💥 <b>ТЫ ПОДОРВАЛСЯ!</b> 💥\n\n"
            f"💰 Ставка: {game.bet} msg\n"
            f"💔 Возврат: {win_amount} msg (50%)\n"
            f"💣 Мин на поле: {len(game.mines)}"
        )
    
    # Создаем клавиатуру только с одной кнопкой
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 ИГРАТЬ ЕЩЁ", callback_data=f"mines_new_{game.bet}")
    
    markup = builder.as_markup()
    
    final_text = (
        f"💣 <b>ИГРА ОКОНЧЕНА</b> 💣\n\n"
        f"{result_text}\n"
    )
    
    # Редактируем существующее сообщение
    await message.bot.edit_message_text(
        final_text,
        chat_id=game.chat_id,
        message_id=game.message_id,
        reply_markup=markup,
        parse_mode="HTML"
    )
    
    # Удаляем игру из активных после показа результата
    if game.user_id in active_mines_games:
        del active_mines_games[game.user_id]

@dp.callback_query(F.data.startswith('mines_new_'))
async def mines_new_game(callback: CallbackQuery):
    """Начинает новую игру с той же ставкой (удаляет старое сообщение)."""
    bet = int(callback.data.replace('mines_new_', ''))
    user_id = callback.from_user.id
    
    # Проверяем баланс
    user_data = await get_user_data(user_id)
    if user_data["msg_count"] < bet:
        await callback.answer(f"❌ Недостаточно msg! Баланс: {user_data['msg_count']}", show_alert=True)
        return
    
    # Удаляем старое сообщение с результатом
    await callback.message.delete()
    
    # Создаем новую игру
    game = MinesGame(user_id, bet)
    game.chat_id = callback.message.chat.id
    active_mines_games[user_id] = game
    
    # Списываем ставку
    users = await load_users()
    users[str(user_id)]["msg_count"] -= bet
    users[str(user_id)]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
    await save_users(users)
    
    # Отправляем новое поле (новое сообщение)
    sent_message = await send_mines_board(callback.message, game)
    game.message_id = sent_message.message_id
    
    await callback.answer()

@dp.callback_query(F.data == "mines_stop")
async def mines_stop_game(callback: CallbackQuery):
    """Принудительно завершает игру."""
    user_id = callback.from_user.id
    
    if user_id not in active_mines_games:
        await callback.answer("❌ Нет активной игры!")
        return
    
    game = active_mines_games[user_id]
    
    # Возвращаем текущий выигрыш
    current_multiplier = game.get_multiplier_for_step(game.step) if game.step > 0 else 1.0
    win_amount = int(game.bet * current_multiplier)
    
    users = await load_users()
    users[str(user_id)]["msg_count"] += win_amount
    users[str(user_id)]["last_activity"] = (await get_current_krasnoyarsk_time()).isoformat()
    await save_users(users)
    
    # Показываем результат с одной кнопкой
    await show_final_board(callback.message, game, win_amount, win=True)
    
    await callback.answer("✅ Игра завершена!")

@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    """Игнорирует нажатия на неактивные кнопки."""
    await callback.answer()

import random
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

# Словарь для хранения времени последнего шипперинга
ship_cooldowns = {}

import random
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

# Словарь для хранения времени последнего шипперинга
ship_cooldowns = {}

@dp.message(F.text.startswith(".шипперим"))
async def cmd_ship(message: Message):
    """Показывает совместимость двух пользователей с анимацией."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = datetime.now(KRASNOYARSK_TZ)
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 💕 .шипперим | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Проверяем кулдаун (10 секунд)
    user_id = message.from_user.id
    if user_id in ship_cooldowns:
        last_ship = ship_cooldowns[user_id]
        time_diff = (current_time - last_ship).total_seconds()
        if time_diff < 10:
            remaining = int(10 - time_diff)
            await message.answer(
                f"⏳ <b>Подожди {remaining} сек.</b>\n"
                f"Метро не ходит так часто...",
                parse_mode="HTML"
            )
            return
    
    # Парсим команду: .шипперим @username
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "❌ <b>Неправильный формат!</b>\n"
            "Использование: <code>.шипперим @username</code>\n"
            "Пример: <code>.шипперим @durov</code>",
            parse_mode="HTML"
        )
        return
    
    # Получаем username второго пользователя
    target_username = parts[1].replace('@', '')
    if not target_username:
        await message.answer("❌ Укажи username пользователя (например: @username)")
        return
    
    # Ищем пользователя по username в базе
    users = await load_users()
    target_id = None
    target_data = None
    
    for uid, data in users.items():
        if data.get('username', '').lower() == target_username.lower():
            target_id = uid
            target_data = data
            break
    
    if not target_id:
        await message.answer(f"❌ Пользователь @{target_username} не зарегистрирован в боте!")
        return
    
    # Получаем данные первого пользователя (отправителя)
    sender_id = str(message.from_user.id)
    sender_data = users[sender_id]
    
    # Обновляем кулдаун
    ship_cooldowns[user_id] = current_time
    
    # Запускаем анимацию
    await animate_ship_metro(message, sender_data, target_data)

async def animate_ship_metro(message: Message, user1_data: dict, user2_data: dict):
    """Анимация шипперинга в стиле метро."""
    
    # Имена пользователей
    name1 = user1_data.get('registered_name', user1_data.get('full_name', 'Пользователь 1'))
    name2 = user2_data.get('registered_name', user2_data.get('full_name', 'Пользователь 2'))
    
    username1 = user1_data.get('username', '')
    username2 = user2_data.get('username', '')
    
    # Форматируем имена для отображения
    display_name1 = f"{name1} (@{username1})" if username1 else name1
    display_name2 = f"{name2} (@{username2})" if username2 else name2
    
    # Отправляем начальное сообщение
    anim_message = await message.answer(
        f"🚇 <b>ЛИНИЯ ЛЮБВИ</b> 🚇\n\n"
        f"{display_name1}\n"
        f"          🤔\n"
        f"{display_name2}\n\n"
        f"<i>Такс, я думаю.....</i>",
        parse_mode="HTML"
    )
    
    # Этап 1: Думаю (0.3 сек)
    await asyncio.sleep(0.3)
    await anim_message.edit_text(
        f"🚇 <b>ЛИНИЯ ЛЮБВИ</b> 🚇\n\n"
        f"{display_name1}\n"
        f"          😇\n"
        f"{display_name2}\n\n"
        f"<i>Проверяю твоё поведение и его...</i>",
        parse_mode="HTML"
    )
    
    # Этап 2: Проверяю поведение (0.4 сек)
    await asyncio.sleep(0.4)
    await anim_message.edit_text(
        f"🚇 <b>ЛИНИЯ ЛЮБВИ</b> 🚇\n\n"
        f"{display_name1}\n"
        f"          💢\n"
        f"{display_name2}\n\n"
        f"<i>Проверяю твою аву и его...</i>",
        parse_mode="HTML"
    )
    
    # Этап 3: Проверяю аву (0.3 сек)
    await asyncio.sleep(0.3)
    
    # Генерируем результат
    await show_ship_result_metro(anim_message, user1_data, user2_data, edit=True)

async def show_ship_result_metro(message: Message, user1_data: dict, user2_data: dict, edit: bool = False):
    """Показывает результат шипперинга в стиле метро."""
    
    # Генерируем случайный процент совместимости
    compatibility = random.randint(0, 100)
    
    # Определяем описание для станции
    if compatibility < 20:
        description = "🚉 Станция 'Лучше не встречаться'"
        station_emoji = "💔"
        line_color = "🔴"
    elif compatibility < 40:
        description = "🚉 Станция 'Просто знакомые'"
        station_emoji = "🟡"
        line_color = "🟡"
    elif compatibility < 60:
        description = "🚉 Станция 'Может быть'"
        station_emoji = "🟢"
        line_color = "🟢"
    elif compatibility < 80:
        description = "🚉 Станция 'Крепкая дружба'"
        station_emoji = "🔵"
        line_color = "🔵"
    else:
        description = "🚉 Станция 'ИДЕАЛЬНАЯ ПАРА 💞'"
        station_emoji = "💖"
        line_color = "💖"
    
    # Имена пользователей
    name1 = user1_data.get('registered_name', user1_data.get('full_name', 'Пользователь 1'))
    name2 = user2_data.get('registered_name', user2_data.get('full_name', 'Пользователь 2'))
    
    username1 = user1_data.get('username', '')
    username2 = user2_data.get('username', '')
    
    # Форматируем имена для отображения
    display_name1 = f"{name1} (@{username1})" if username1 else name1
    display_name2 = f"{name2} (@{username2})" if username2 else name2
    
    # Создаем линию метро
    line_length = 15
    filled = int((compatibility / 100) * line_length)
    
    # Разные символы для линии
    if compatibility < 20:
        line = "💔" * filled + "🖤" * (line_length - filled)
    elif compatibility < 40:
        line = "🟡" * filled + "🖤" * (line_length - filled)
    elif compatibility < 60:
        line = "🟢" * filled + "🖤" * (line_length - filled)
    elif compatibility < 80:
        line = "🔵" * filled + "🖤" * (line_length - filled)
    else:
        line = "💖" * filled + "🖤" * (line_length - filled)
    
    # Создаем текст результата
    result_text = (
        f"🚇 <b>ЛИНИЯ ЛЮБВИ</b> 🚇\n\n"
        f"{display_name1}\n"
        f"{line_color} {'—' * (line_length//2)}🚉{'—' * (line_length//2)} {line_color}\n"
        f"{display_name2}\n\n"
        f"          {compatibility}%\n\n"
        f"{description}\n\n"
        f"{station_emoji} <i>{get_ship_quote(compatibility)}</i>"
    )
    
    # Создаем кнопку "Попробовать снова"
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 ПОПРОБОВАТЬ СНОВА", 
        callback_data=f"ship_metro_{username2}_{user1_data['id']}_{user2_data['id']}"
    )
    
    # Отправляем или редактируем сообщение
    if edit:
        await message.edit_text(
            result_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            result_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

def get_ship_quote(percent):
    """Возвращает цитату в зависимости от процента."""
    if percent < 10:
        return "Вам лучше держаться подальше друг от друга"
    elif percent < 20:
        return "Слишком разные, как кошка и собака"
    elif percent < 30:
        return "Может быть, просто друзья?"
    elif percent < 40:
        return "Есть искра, но не более"
    elif percent < 50:
        return "Неплохо, но можно лучше"
    elif percent < 60:
        return "Уже что-то! Есть потенциал"
    elif percent < 70:
        return "Хорошая совместимость!"
    elif percent < 80:
        return "Очень крепкая пара!"
    elif percent < 90:
        return "Созданы друг для друга!"
    else:
        return "ИДЕАЛЬНО! СВАДЬБА ЗАВТРА! 💒"

@dp.callback_query(F.data.startswith('ship_metro_'))
async def ship_metro_again(callback: CallbackQuery):
    """Повторяет шипперинг в стиле метро."""
    # Проверяем кулдаун (10 секунд)
    user_id = callback.from_user.id
    current_time = datetime.now(KRASNOYARSK_TZ)
    
    if user_id in ship_cooldowns:
        last_ship = ship_cooldowns[user_id]
        time_diff = (current_time - last_ship).total_seconds()
        if time_diff < 10:
            remaining = int(10 - time_diff)
            await callback.answer(f"⏳ Подожди {remaining} сек.", show_alert=True)
            return
    
    # Формат: ship_metro_username_user1id_user2id
    data = callback.data.replace('ship_metro_', '')
    parts = data.split('_')
    
    if len(parts) < 3:
        await callback.answer("❌ Ошибка данных!")
        return
    
    # Последние два элемента - ID пользователей
    user1_id = int(parts[-2])
    user2_id = int(parts[-1])
    
    # Проверяем, что нажал тот же пользователь
    if callback.from_user.id != user1_id:
        await callback.answer("❌ Это не твой шипперинг!", show_alert=True)
        return
    
    # Загружаем данные пользователей
    users = await load_users()
    
    user1_data = users.get(str(user1_id))
    user2_data = users.get(str(user2_id))
    
    if not user1_data or not user2_data:
        await callback.answer("❌ Пользователи не найдены!", show_alert=True)
        return
    
    # Обновляем кулдаун
    ship_cooldowns[user_id] = current_time
    
    # Запускаем анимацию заново
    await callback.message.delete()
    await animate_ship_metro(callback.message, user1_data, user2_data)
    await callback.answer()

# ------- Банковские команды ---------

@dp.message(F.text == ".банк")
async def cmd_dot_bank(message: Message):
    """Показывает состояние банка."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 🏦 .банк | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    user_data = await get_user_data(message.from_user.id)
    
    bank_cells = user_data.get("bank_cells", 1)
    bank_amount = user_data.get("bank_amount", 0)
    bank_limit = await get_bank_limit(bank_cells)
    bank_free = bank_limit - bank_amount
    
    hourly_msgs = user_data.get("hourly_messages", 0)
    
    # Стоимость следующей ячейки
    next_cell_cost = await get_cell_cost(bank_cells + 1)
    
    # Время следующего начисления процентов
    next_interest = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    time_to_next = next_interest - current_time
    minutes_to_next = int(time_to_next.total_seconds() / 60)
    
    # Визуализация заполненности банка
    fill_percent = int((bank_amount / bank_limit) * 10) if bank_limit > 0 else 0
    fill_bar = "▰" * fill_percent + "▱" * (10 - fill_percent)
    
    bank_text = (
        f"🏦 <b>Банк {user_data.get('registered_name')}</b>\n"
        f"├─ Хранится: {bank_amount} msg\n"
        f"├─ Лимит: {bank_limit} msg\n"
        f"├─ Заполнено: [{fill_bar}]\n\n"
        f"💹 <b>Проценты:</b>\n"
        f"├─ Ставка: 1%/час\n"
        f"├─ Сообщений за час: {hourly_msgs}/10\n"
        f"├─ До начисления: {minutes_to_next} мин\n\n"
    )
    
    await message.answer(bank_text, parse_mode="HTML")
    print(f"  └─ ✅ Банк показан | В банке: {bank_amount}/{bank_limit} msg | Ячеек: {bank_cells}")

@dp.message(F.text.startswith(".банк положить"))
async def cmd_dot_bank_deposit(message: Message):
    """Кладет msg в банк."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 💰 .банк положить | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Парсим сумму
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "❌ Неправильный формат!\n"
            "Использование: <code>.банк положить 100</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    # Проверка на отрицательное число
    if amount <= 0:
        await message.answer(
            "❌ Сумма должна быть положительным числом!",
            parse_mode="HTML"
        )
        return
    
    # Получаем данные пользователя
    users = await load_users()
    user_id_str = str(message.from_user.id)
    user_data = users[user_id_str]
    
    # Проверка: хватает ли денег на балансе
    if user_data["msg_count"] < amount:
        await message.answer(
            f"❌ Недостаточно msg на балансе!\n"
            f"└─ Твой баланс: {user_data['msg_count']} msg\n"
            f"💡 Напиши больше сообщений, чтобы накопить нужную сумму!",
            parse_mode="HTML"
        )
        return
    
    # Проверка: есть ли место в банке
    bank_cells = user_data.get("bank_cells", 1)
    bank_amount = user_data.get("bank_amount", 0)
    bank_limit = await get_bank_limit(bank_cells)
    
    if bank_amount + amount > bank_limit:
        free_space = bank_limit - bank_amount
        await message.answer(
            f"❌ Недостаточно места в банке!\n"
            f"└─ Свободно места: {free_space} msg\n"
            f"└─ Лимит банка: {bank_limit} msg\n\n"
            f"💡 Купи новую ячейку: <code>.банк купить ячейку</code>",
            parse_mode="HTML"
        )
        return
    
    # Кладем деньги в банк
    users[user_id_str]["bank_amount"] += amount
    users[user_id_str]["msg_count"] -= amount
    users[user_id_str]["last_activity"] = current_time.isoformat()
    
    await save_users(users)
    
    print(f"  └─ ✅ +{amount} msg в банк")
    await message.answer(
        f"✅ <b>Успешно положено!</b>\n"
        f"└─ Сумма: {amount} msg\n"
        f"└─ Новый баланс: {users[user_id_str]['msg_count']} msg\n"
        f"└─ В банке: {users[user_id_str]['bank_amount']}/{bank_limit} msg",
        parse_mode="HTML"
    )

@dp.message(F.text.startswith(".банк снять"))
async def cmd_dot_bank_withdraw(message: Message):
    """Снимает msg из банка."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 💸 .банк снять | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Парсим сумму
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "❌ Неправильный формат!\n"
            "Использование: <code>.банк снять 100</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")
        return
    
    # Проверка на отрицательное число
    if amount <= 0:
        await message.answer(
            "❌ Сумма должна быть положительным числом!",
            parse_mode="HTML"
        )
        return
    
    # Получаем данные пользователя
    users = await load_users()
    user_id_str = str(message.from_user.id)
    user_data = users[user_id_str]
    
    bank_amount = user_data.get("bank_amount", 0)
    bank_cells = user_data.get("bank_cells", 1)
    bank_limit = await get_bank_limit(bank_cells)
    
    # Проверка: хватает ли денег в банке
    if bank_amount < amount:
        await message.answer(
            f"❌ В банке недостаточно msg!\n"
            f"└─ Ты пытаешься снять: {amount} msg\n"
            f"└─ В банке: {bank_amount} msg",
            parse_mode="HTML"
        )
        return
    
    # Снимаем деньги из банка
    users[user_id_str]["bank_amount"] -= amount
    users[user_id_str]["msg_count"] += amount
    users[user_id_str]["last_activity"] = current_time.isoformat()
    
    await save_users(users)
    
    print(f"  └─ ✅ -{amount} msg из банка")
    await message.answer(
        f"✅ <b>Успешно снято!</b>\n"
        f"└─ Сумма: {amount} msg\n"
        f"└─ Новый баланс: {users[user_id_str]['msg_count']} msg\n"
        f"└─ В банке: {users[user_id_str]['bank_amount']}/{bank_limit} msg",
        parse_mode="HTML"
    )

@dp.message(F.text == ".банк купить ячейку")
async def cmd_dot_bank_buy_cell(message: Message):
    """Покупает новую ячейку в банке."""
    user = message.from_user
    user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%H:%M")
    print(f"\n[{time_str}] 🏦 .банк купить ячейку | {user_info} | {user.full_name}")
    
    if not await check_registration(message):
        return
    
    # Получаем данные пользователя
    users = await load_users()
    user_id_str = str(message.from_user.id)
    user_data = users[user_id_str]
    
    bank_cells = user_data.get("bank_cells", 1)
    next_cell_number = bank_cells + 1
    cell_cost = await get_cell_cost(next_cell_number)
    new_limit = (bank_cells + 1) * BANK_CELL_CAPACITY
    
    # Проверяем, хватает ли денег
    if user_data["msg_count"] < cell_cost:
        await message.answer(
            f"❌ Недостаточно msg для покупки ячейки!\n"
            f"└─ Стоимость ячейки {next_cell_number}: {cell_cost} msg\n"
            f"└─ Твой баланс: {user_data['msg_count']} msg\n\n"
            f"💡 Не хватает: {cell_cost - user_data['msg_count']} msg",
            parse_mode="HTML"
        )
        return
    
    # Покупаем новую ячейку
    users[user_id_str]["bank_cells"] = next_cell_number
    users[user_id_str]["msg_count"] -= cell_cost
    users[user_id_str]["last_activity"] = current_time.isoformat()
    
    await save_users(users)
    
    print(f"  └─ ✅ Куплена ячейка {next_cell_number} за {cell_cost} msg")
    await message.answer(
        f"✅ <b>Ячейка куплена!</b>\n"
        f"└─ Новая ячейка: {next_cell_number}\n"
        f"└─ Стоимость: {cell_cost} msg\n"
        f"└─ Новый лимит: {new_limit} msg\n\n"
        f"💰 Баланс: {users[user_id_str]['msg_count']} msg\n"
        f"🏦 В банке: {users[user_id_str]['bank_amount']}/{new_limit} msg",
        parse_mode="HTML"
    )

# ----------------------------------- Экономика за сообщения -----------------------------------
@dp.message()
async def handle_all_messages(message: Message):
    """Обработчик всех остальных сообщений. Начисляет 1 msg за сообщение."""
    # Пропускаем команды (начинаются с / или .)
    if message.text and (message.text.startswith('/') or message.text.startswith('.')):
        return
    
    # Проверяем, зарегистрирован ли пользователь
    if await is_user_registered(message.from_user.id):
        # Начисляем монетку
        await add_msg_coin(message.from_user.id)
        
        # Логируем каждое 10-е сообщение (чтобы не спамить консоль)
        user_data = await get_user_data(message.from_user.id)
        if user_data and user_data.get('msg_count', 0) % 10 == 0:
            user = message.from_user
            user_info = f"@{user.username}" if user.username else f"ID: {user.id}"
            current_time = await get_current_krasnoyarsk_time()
            time_str = current_time.strftime("%H:%M")
            bank_info = f" | Банк: {user_data.get('bank_amount', 0)}/{user_data.get('bank_cells', 1)*5000}"
            print(f"[{time_str}] 💬 Сообщение | {user_info} | Баланс: {user_data.get('msg_count', 0)} msg{bank_info} | За час: {user_data.get('hourly_messages', 0)}/50")

# ----------------------------------- Запуск бота -----------------------------------
async def main():
    current_time = await get_current_krasnoyarsk_time()
    time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n{'='*60}")
    print(f"🚀 Бот запущен и готов к работе!")
    print(f"{'='*60}\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())