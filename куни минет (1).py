import asyncio
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message

# Конфигурация
BOT_TOKEN = "ТВОЙ_ТОКЕН_БОТА"
OWNER_ID = 7564741700
STATS_FILE = "mystery.json"

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
cooldowns = {}


# ========== РАБОТА С JSON ==========

def load_stats() -> dict:
    """Загружает статистику из JSON файла."""
    if not os.path.exists(STATS_FILE):
        default_stats = {
            "users": {},
            "total": {
                "kuni": 0,
                "minet": 0,
                "drink": 0,
                "drink_with": 0
            }
        }
        save_stats(default_stats)
        return default_stats
    
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stats(stats: dict):
    """Сохраняет статистику в JSON файл."""
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def update_user_stats(user_id: int, user_name: str, action: str, target_id: int = None):
    """Обновляет статистику пользователя."""
    stats = load_stats()
    user_id_str = str(user_id)
    
    if user_id_str not in stats["users"]:
        stats["users"][user_id_str] = {
            "name": user_name,
            "kuni": 0,
            "minet": 0,
            "drink": 0,
            "drink_with": 0,
            "last_action": None
        }
    else:
        stats["users"][user_id_str]["name"] = user_name
    
    if action == "kuni":
        stats["users"][user_id_str]["kuni"] += 1
        stats["total"]["kuni"] += 1
    elif action == "minet":
        stats["users"][user_id_str]["minet"] += 1
        stats["total"]["minet"] += 1
    elif action == "drink":
        stats["users"][user_id_str]["drink"] += 1
        stats["total"]["drink"] += 1
    elif action == "drink_with":
        stats["users"][user_id_str]["drink_with"] += 1
        stats["total"]["drink_with"] += 1
    
    stats["users"][user_id_str]["last_action"] = datetime.now().isoformat()
    
    if target_id and action in ["kuni", "minet"]:
        target_id_str = str(target_id)
        if target_id_str not in stats["users"]:
            stats["users"][target_id_str] = {
                "name": "Неизвестно",
                "kuni": 0,
                "minet": 0,
                "drink": 0,
                "drink_with": 0,
                "last_action": None
            }
        
        if action == "kuni":
            stats["users"][target_id_str]["kuni_received"] = stats["users"][target_id_str].get("kuni_received", 0) + 1
        elif action == "minet":
            stats["users"][target_id_str]["minet_received"] = stats["users"][target_id_str].get("minet_received", 0) + 1
    
    save_stats(stats)


# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🍆 Привет! команды:\n"
        "• <code>куни</code> — ответь на сообщение\n"
        "• <code>минет</code> — ответь на сообщение\n"
        "• <code>выпить</code> — можно с реплаем или без\n"
        "• <code>стата</code> — показать свою статистику\n"
        "• <code>топ куни</code> — топ по куни\n"
        "• <code>топ минет</code> — топ по минетам\n"
        "• <code>топ выпивки</code> — топ по выпивке\n"
        parse_mode="HTML"
    )


@dp.message(F.text.func(lambda text: text and text.lower() == "куни"))
async def cmd_kuni(message: Message):
    """Команда .куни (игнорирует регистр)"""
    user = message.from_user
    current_time = datetime.now().strftime("%H:%M")
    
    if user.id in cooldowns:
        time_diff = (datetime.now() - cooldowns[user.id]).total_seconds()
        if time_diff < 10:
            await message.answer(f"⏳ Подожди {int(10 - time_diff)} сек.")
            return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответь на сообщение человека!")
        return
    
    target = message.reply_to_message.from_user
    
    if target.id == user.id:
        await message.answer("❌ Нельзя отправить самому себе!")
        return
    
    sender_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    
    if target.username:
        target_link = f"<a href='https://t.me/{target.username}'>{target.first_name}</a>"
    else:
        target_link = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
    
    await message.answer(f"😛 {sender_link} отлизал у {target_link}", parse_mode="HTML")
    
    update_user_stats(user.id, user.first_name, "kuni", target.id)
    cooldowns[user.id] = datetime.now()
    
    print(f"[{current_time}] .куни | @{user.username} -> @{target.username if target.username else target.id}")


@dp.message(F.text.func(lambda text: text and text.lower() == "минет"))
async def cmd_minet(message: Message):
    """Команда .минет (игнорирует регистр)"""
    user = message.from_user
    current_time = datetime.now().strftime("%H:%M")
    
    if user.id in cooldowns:
        time_diff = (datetime.now() - cooldowns[user.id]).total_seconds()
        if time_diff < 10:
            await message.answer(f"⏳ Подожди {int(10 - time_diff)} сек.")
            return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответь на сообщение человека!")
        return
    
    target = message.reply_to_message.from_user
    
    if target.id == user.id:
        await message.answer("❌ Нельзя отправить самому себе!")
        return
    
    sender_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    
    if target.username:
        target_link = f"<a href='https://t.me/{target.username}'>{target.first_name}</a>"
    else:
        target_link = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
    
    await message.answer(f"💦 {sender_link} отсосала у {target_link}", parse_mode="HTML")
    
    update_user_stats(user.id, user.first_name, "minet", target.id)
    cooldowns[user.id] = datetime.now()
    
    print(f"[{current_time}] .минет | @{user.username} -> @{target.username if target.username else target.id}")


@dp.message(F.text.func(lambda text: text and text.lower() == "выпить"))
async def cmd_drink(message: Message):
    """Команда .выпить (игнорирует регистр)"""
    user = message.from_user
    current_time = datetime.now().strftime("%H:%M")
    
    if user.id in cooldowns:
        time_diff = (datetime.now() - cooldowns[user.id]).total_seconds()
        if time_diff < 10:
            await message.answer(f"⏳ Подожди {int(10 - time_diff)} сек.")
            return
    
    sender_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        
        if target.id == user.id:
            await message.answer("❌ Нельзя выпить с самим собой!")
            return
        
        if target.username:
            target_link = f"<a href='https://t.me/{target.username}'>{target.first_name}</a>"
        else:
            target_link = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
        
        await message.answer(
            f"🍺 {sender_link} набухался с {target_link} в хлам и уснули на асфальте 🛌",
            parse_mode="HTML"
        )
        update_user_stats(user.id, user.first_name, "drink_with")
    else:
        await message.answer(f"🍺 {sender_link} набухался 🥴", parse_mode="HTML")
        update_user_stats(user.id, user.first_name, "drink")
    
    cooldowns[user.id] = datetime.now()
    print(f"[{current_time}] .выпить | @{user.username}")


@dp.message(F.text.func(lambda text: text and text.lower() == "стата"))
async def cmd_stats(message: Message):
    """Показывает статистику пользователя."""
    user = message.from_user
    stats = load_stats()
    user_id_str = str(user.id)
    
    if user_id_str not in stats["users"]:
        await message.answer(
            f"📊 <b>Статистика {user.first_name}</b>\n\n"
            f"😛 Куни: 0\n"
            f"💦 Минет: 0\n"
            f"🍺 Выпил в одиночку: 0\n"
            f"🍻 Выпил с компанией: 0\n\n"
            f"🎯 Соверши первое действие!",
            parse_mode="HTML"
        )
        return
    
    user_stats = stats["users"][user_id_str]
    
    await message.answer(
        f"📊 <b>Статистика {user.first_name}</b>\n\n"
        f"😛 <b>Куни:</b> {user_stats.get('kuni', 0)}\n"
        f"💦 <b>Минет:</b> {user_stats.get('minet', 0)}\n"
        f"🍺 <b>Выпил в одиночку:</b> {user_stats.get('drink', 0)}\n"
        f"🍻 <b>Выпил с компанией:</b> {user_stats.get('drink_with', 0)}\n\n"
        f"📅 <b>Последнее действие:</b> {user_stats.get('last_action', '—')[:16] if user_stats.get('last_action') else '—'}",
        parse_mode="HTML"
    )


@dp.message(F.text.func(lambda text: text and text.lower() == "топ куни"))
async def cmd_top_kuni(message: Message):
    """Топ по куни."""
    stats = load_stats()
    
    users_list = []
    for uid, data in stats["users"].items():
        users_list.append({
            "id": uid,
            "name": data.get("name", "Неизвестно"),
            "count": data.get("kuni", 0)
        })
    
    users_list.sort(key=lambda x: x["count"], reverse=True)
    top = users_list[:10]
    
    if not top or top[0]["count"] == 0:
        await message.answer("😛 Пока никто не делал куни!")
        return
    
    text = "🏆 <b>ТОП ПО КУНИ</b> 🏆\n\n"
    for i, u in enumerate(top, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        text += f"{medal} {u['name']} — {u['count']} 🍆\n"
    
    await message.answer(text, parse_mode="HTML")


@dp.message(F.text.func(lambda text: text and text.lower() == "топ минет"))
async def cmd_top_minet(message: Message):
    """Топ по минетам."""
    stats = load_stats()
    
    users_list = []
    for uid, data in stats["users"].items():
        users_list.append({
            "id": uid,
            "name": data.get("name", "Неизвестно"),
            "count": data.get("minet", 0)
        })
    
    users_list.sort(key=lambda x: x["count"], reverse=True)
    top = users_list[:10]
    
    if not top or top[0]["count"] == 0:
        await message.answer("💦 Пока никто не делал минет!")
        return
    
    text = "🏆 <b>ТОП ПО МИНЕТУ</b> 🏆\n\n"
    for i, u in enumerate(top, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        text += f"{medal} {u['name']} — {u['count']} 💦\n"
    
    await message.answer(text, parse_mode="HTML")


@dp.message(F.text.func(lambda text: text and text.lower() == "топ выпивки"))
async def cmd_top_drinker(message: Message):
    """Топ по выпивке."""
    stats = load_stats()
    
    users_list = []
    for uid, data in stats["users"].items():
        total = data.get("drink", 0) + data.get("drink_with", 0)
        users_list.append({
            "id": uid,
            "name": data.get("name", "Неизвестно"),
            "alone": data.get("drink", 0),
            "with": data.get("drink_with", 0),
            "total": total
        })
    
    users_list.sort(key=lambda x: x["total"], reverse=True)
    top = users_list[:10]
    
    if not top or top[0]["total"] == 0:
        await message.answer("🍺 Пока никто не пил!")
        return
    
    text = "🏆 <b>ТОП ВЫПИВОХИ</b> 🏆\n\n"
    for i, u in enumerate(top, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        text += f"{medal} {u['name']} — {u['total']} 🍺 (один: {u['alone']}, в компании: {u['with']})\n"
    
    await message.answer(text, parse_mode="HTML")


@dp.message(F.text.func(lambda text: text and text.lower() == ".очистить"))
async def cmd_clear_cooldown(message: Message):
    """Очищает кулдаун (только для владельца)."""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Нет доступа!")
        return
    
    cooldowns.clear()
    await message.answer("✅ Кулдауны очищены!")


@dp.message(F.text.func(lambda text: text and text.lower() == ".всястата"))
async def cmd_total_stats(message: Message):
    """Общая статистика по всем (только для владельца)."""
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Нет доступа!")
        return
    
    stats = load_stats()
    total = stats.get("total", {})
    
    await message.answer(
        f"📊 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
        f"😛 Всего куни: {total.get('kuni', 0)}\n"
        f"💦 Всего минет: {total.get('minet', 0)}\n"
        f"🍺 Всего выпил один: {total.get('drink', 0)}\n"
        f"🍻 Всего выпил в компании: {total.get('drink_with', 0)}\n"
        f"👥 Всего пользователей: {len(stats['users'])}",
        parse_mode="HTML"
    )


async def main():
    print("\n" + "="*50)
    print("🍆 Бот с статистикой запущен!")
    print("="*50 + "\n")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())