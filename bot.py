import os
import random
import sqlite3
from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "potuzhno_drop.db")
CASE_COST = 50

RARITIES = [
    ("Обычный", 45, "⚪"),
    ("Ржавый", 25, "🟤"),
    ("Серебряный", 15, "⚪"),
    ("Золотой", 8, "🟡"),
    ("Бриллиантовый", 4, "💎"),
    ("Изумрудный", 2, "🟢"),
    ("Чёрный «БОГ»", 0.9, "⚫"),
    ("Камуфляжный «ПАНТЕРА»", 0.1, "🐆"),
]
ITEMS = [
    ("Бусик", "🚐"),
    ("Развед-дрон", "🛸"),
    ("Мини-дрон", "🚁"),
    ("Грузовой бусик", "🚐"),
    ("Турбо-дрон", "🛸"),
]

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, coins INTEGER NOT NULL DEFAULT 100,
        last_daily TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT,
        emoji TEXT, rarity TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit()
    return con

def ensure_user(user):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)",
                    (user.id, user.username or user.first_name or "Игрок"))
        con.execute("UPDATE users SET username=? WHERE user_id=?",
                    (user.username or user.first_name or "Игрок", user.id))

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Открыть кейс — 50 🪙", callback_data="case")],
        [InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory"),
         InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("⚡ Апгрейд", callback_data="upgrade"),
         InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily")],
        [InlineKeyboardButton("🏆 Топ игроков", callback_data="top")],
    ])

def rarity_roll():
    rarity, _, emoji = random.choices(RARITIES, weights=[r[1] for r in RARITIES], k=1)[0]
    return rarity, emoji

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.message.reply_text(
        "🚐 Добро пожаловать в POTUZHNO DROP!\n\n"
        "Собирай бусики и дроны, открывай кейсы и улучшай коллекцию. "
        "Все монеты и предметы здесь игровые — никаких реальных денег.",
        reply_markup=menu())

async def show_balance(q, uid):
    with db() as con:
        coins = con.execute("SELECT coins FROM users WHERE user_id=?", (uid,)).fetchone()[0]
    await q.edit_message_text(f"💰 Твой баланс: {coins} 🪙", reply_markup=menu())

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ensure_user(q.from_user)

    if q.data == "balance":
        return await show_balance(q, uid)

    if q.data == "daily":
        with db() as con:
            row = con.execute("SELECT last_daily FROM users WHERE user_id=?", (uid,)).fetchone()
            if row[0] == date.today().isoformat():
                return await q.edit_message_text("⏳ Ежедневный бонус уже забран. Возвращайся завтра!", reply_markup=menu())
            con.execute("UPDATE users SET coins=coins+100, last_daily=? WHERE user_id=?",
                        (date.today().isoformat(), uid))
        return await q.edit_message_text("🎁 Ты получил 100 🪙! Заглядывай завтра за новым бонусом.", reply_markup=menu())

    if q.data == "case":
        with db() as con:
            coins = con.execute("SELECT coins FROM users WHERE user_id=?", (uid,)).fetchone()[0]
            if coins < CASE_COST:
                return await q.edit_message_text("Не хватает монет. Забери ежедневный бонус! 🎁", reply_markup=menu())
            con.execute("UPDATE users SET coins=coins-? WHERE user_id=?", (CASE_COST, uid))
            rarity, rarity_emoji = rarity_roll()
            item, item_emoji = random.choice(ITEMS)
            con.execute("INSERT INTO inventory(user_id,item,emoji,rarity) VALUES(?,?,?,?)",
                        (uid, item, item_emoji, rarity))
        return await q.edit_message_text(
            f"🎉 В кейсе попалось:\n{item_emoji} **{item}**\n"
            f"{rarity_emoji} Редкость: **{rarity}**\n\n-50 🪙",
            parse_mode="Markdown", reply_markup=menu())

    if q.data == "inventory":
        with db() as con:
            rows = con.execute("SELECT item,emoji,rarity,COUNT(*) FROM inventory "
                               "WHERE user_id=? GROUP BY item,emoji,rarity ORDER BY COUNT(*) DESC",
                               (uid,)).fetchall()
        if not rows:
            text = "🎒 Инвентарь пуст. Открой первый кейс!"
        else:
            text = "🎒 ТВОЯ КОЛЛЕКЦИЯ\n\n" + "\n".join(
                f"{emoji} {item} — {rarity} ×{count}" for item, emoji, rarity, count in rows)
        return await q.edit_message_text(text, reply_markup=menu())

    if q.data == "upgrade":
        with db() as con:
            rows = con.execute("SELECT id,item,emoji,rarity FROM inventory WHERE user_id=? ORDER BY id",
                               (uid,)).fetchall()
        if not rows:
            return await q.edit_message_text("Сначала получи предмет из кейса 🎁", reply_markup=menu())
        buttons = [[InlineKeyboardButton(f"{r[2]} {r[1]} · {r[3]}", callback_data=f"up:{r[0]}")]
                   for r in rows[-10:]]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="home")])
        return await q.edit_message_text("⚡ Выбери предмет для попытки апгрейда. Шанс успеха — 35%.",
                                          reply_markup=InlineKeyboardMarkup(buttons))

    if q.data.startswith("up:"):
        item_id = int(q.data.split(":")[1])
        with db() as con:
            row = con.execute("SELECT item,emoji,rarity FROM inventory WHERE id=? AND user_id=?",
                              (item_id, uid)).fetchone()
            if not row:
                return await q.edit_message_text("Этот предмет уже недоступен.", reply_markup=menu())
            current = next((i for i, r in enumerate(RARITIES) if r[0] == row[2]), 0)
            if current >= len(RARITIES)-1:
                return await q.edit_message_text("🐆 Этот предмет уже максимальной редкости!", reply_markup=menu())
            if random.random() < 0.35:
                new_rarity = RARITIES[current+1][0]
                con.execute("UPDATE inventory SET rarity=? WHERE id=?", (new_rarity, item_id))
                result = f"🎉 УСПЕХ! {row[0]} улучшен: {row[2]} → {new_rarity}!"
            else:
                result = f"Не получилось улучшить {row[0]}. Предмет сохранён."
        return await q.edit_message_text("⚡ " + result, reply_markup=menu())

    if q.data == "top":
        with db() as con:
            rows = con.execute("SELECT u.username, COUNT(i.id) FROM users u "
                               "LEFT JOIN inventory i ON i.user_id=u.user_id "
                               "GROUP BY u.user_id ORDER BY COUNT(i.id) DESC LIMIT 10").fetchall()
        text = "🏆 ТОП КОЛЛЕКЦИОНЕРОВ\n\n" + "\n".join(
            f"{n}. {name} — {count} предметов" for n, (name, count) in enumerate(rows, 1))
        return await q.edit_message_text(text, reply_markup=menu())

    if q.data == "home":
        return await q.edit_message_text("🚐 POTUZHNO DROP — главное меню", reply_markup=menu())

def main():
    if not TOKEN:
        raise RuntimeError("Добавь BOT_TOKEN в переменные окружения.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    print("Potuzhno Drop bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
