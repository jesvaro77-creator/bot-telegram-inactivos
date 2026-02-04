import os
import sqlite3
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8080))
URL = os.getenv("APP_URL")

DEFAULT_INACTIVE_DAYS = 14
DEFAULT_NEW_USER_DAYS = 3

conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER,
    chat_id INTEGER,
    last_activity TEXT,
    join_date TEXT,
    PRIMARY KEY (user_id, chat_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS config (
    chat_id INTEGER PRIMARY KEY,
    inactive_days INTEGER,
    new_user_days INTEGER
)
""")

conn.commit()


def get_config(chat_id):
    cursor.execute("SELECT inactive_days, new_user_days FROM config WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    return row if row else (DEFAULT_INACTIVE_DAYS, DEFAULT_NEW_USER_DAYS)


async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or user.is_bot:
        return

    now = datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO users (user_id, chat_id, last_activity, join_date)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(user_id, chat_id)
    DO UPDATE SET last_activity=?
    """, (user.id, chat.id, now, now, now))

    conn.commit()


async def check_inactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    inactive_days, new_user_days = get_config(chat.id)

    admins = await chat.get_administrators()
    admin_ids = {admin.user.id for admin in admins}

    now = datetime.utcnow()
    warned = 0

    cursor.execute("SELECT user_id, last_activity, join_date FROM users WHERE chat_id=?", (chat.id,))
    for user_id, last_activity, join_date in cursor.fetchall():
        if user_id in admin_ids:
            continue

        if (now - datetime.fromisoformat(join_date)).days < new_user_days:
            continue

        if (now - datetime.fromisoformat(last_activity)).days >= inactive_days:
            await context.bot.send_message(
                chat.id,
                f"⚠️ <a href='tg://user?id={user_id}'>Usuario</a> inactivo {inactive_days} días.",
                parse_mode="HTML"
            )
            warned += 1

    await update.message.reply_text(f"Usuarios advertidos: {warned}")


async def set_inactive_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0])
    chat_id = update.effective_chat.id

    cursor.execute("""
    INSERT INTO config (chat_id, inactive_days, new_user_days)
    VALUES (?, ?, ?)
    ON CONFLICT(chat_id)
    DO UPDATE SET inactive_days=?
    """, (chat_id, days, DEFAULT_NEW_USER_DAYS, days))

    conn.commit()
    await update.message.reply_text(f"Inactividad configurada a {days} días")


async def set_new_user_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(context.args[0])
    chat_id = update.effective_chat.id

    inactive_days, _ = get_config(chat_id)

    cursor.execute("""
    INSERT INTO config (chat_id, inactive_days, new_user_days)
    VALUES (?, ?, ?)
    ON CONFLICT(chat_id)
    DO UPDATE SET new_user_days=?
    """, (chat_id, inactive_days, days, days))

    conn.commit()
    await update.message.reply_text(f"Usuarios nuevos excluidos {days} días")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_activity))
    app.add_handler(CommandHandler("revisar", check_inactive))
    app.add_handler(CommandHandler("set_inactivo", set_inactive_days))
    app.add_handler(CommandHandler("set_nuevo", set_new_user_days))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{URL}/{TOKEN}",
    )


if __name__ == "__main__":
    main()
