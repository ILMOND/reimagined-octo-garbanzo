import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

import pytz
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

DB_PATH = "bot_queue.db"
TIMEZONE = pytz.timezone("Africa/Cairo")
ADD_CHAPTER, SET_TIME = range(2)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.getenv("PORT", "8080"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def require_env_vars() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN environment variable")
    if not ADMIN_ID:
        raise RuntimeError("Missing ADMIN_ID environment variable")
    if not CHANNEL_ID:
        raise RuntimeError("Missing CHANNEL_ID environment variable")


def init_database() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            publish_time TEXT NOT NULL,
            last_published_date TEXT
        )
        """
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (id, publish_time, last_published_date) VALUES (1, '18:00', NULL)"
    )
    conn.commit()
    conn.close()
    logger.info("SQLite database initialized")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


async def db_execute(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def add_chapter_to_queue(text: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO queue (content) VALUES (?)", (text.strip(),))
    conn.commit()
    conn.close()
    logger.info("Added new chapter to queue")


def get_queue_count() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM queue")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_queue_preview(limit: int = 5) -> list[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, created_at FROM queue ORDER BY id ASC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_publish_time() -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT publish_time FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "18:00"


def set_publish_time(new_time: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET publish_time = ?, last_published_date = NULL WHERE id = 1",
        (new_time,),
    )
    conn.commit()
    conn.close()
    logger.info("Publish time set to %s", new_time)


def get_last_published_date() -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_published_date FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_last_published_date(date_str: str) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET last_published_date = ? WHERE id = 1",
        (date_str,),
    )
    conn.commit()
    conn.close()
    logger.info("Last published date updated to %s", date_str)


def get_next_chapter() -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, content FROM queue ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row


def delete_chapter(chapter_id: int) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM queue WHERE id = ?", (chapter_id,))
    conn.commit()
    conn.close()
    logger.info("Deleted chapter %s from queue", chapter_id)


def is_admin(user_id: Optional[int]) -> bool:
    return user_id == ADMIN_ID


def build_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ إضافة فصل جديد", callback_data="add_chapter")],
        [InlineKeyboardButton("📊 الفصول المنتظرة", callback_data="pending_chapters")],
        [InlineKeyboardButton("⚙️ إعدادات وقت النشر", callback_data="set_publish_time")],
        [InlineKeyboardButton("🚀 انشر فصلاً الآن", callback_data="publish_now")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin(user_id):
        await update.message.reply_text("هذا البوت مخصص لصاحب الآيدي فقط.")
        return

    await update.message.reply_text(
        "مرحباً بك في لوحة تحكم النشر. اختر أحد الأزرار:",
        reply_markup=build_admin_keyboard(),
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("غير مصرح لك باستخدام هذه الأزرار.")
        return ConversationHandler.END

    action = query.data
    if action == "add_chapter":
        await query.edit_message_text("أرسل نص الفصل الجديد الآن:")
        return ADD_CHAPTER

    if action == "pending_chapters":
        count = await db_execute(get_queue_count)
        publish_time = await db_execute(get_publish_time)
        preview = await db_execute(get_queue_preview, 5)
        preview_text = "\n".join(
            f"#{row['id']} - {row['created_at']}" for row in preview
        )
        if not preview_text:
            preview_text = "لا توجد فصول محفوظة حاليًا."

        await query.edit_message_text(
            f"📊 عدد الفصول في الطابور: {count}\n"
            f"⏰ وقت النشر اليومي: {publish_time}\n"
            f"أول 5 فصول في الطابور:\n{preview_text}",
            reply_markup=build_admin_keyboard(),
        )
        return ConversationHandler.END

    if action == "set_publish_time":
        await query.edit_message_text(
            "أرسل الوقت الجديد بصيغة HH:MM مثل 18:30:",
        )
        return SET_TIME

    if action == "publish_now":
        published = await publish_next_chapter(context.application)
        message = (
            "✅ تم نشر أول فصل الآن في القناة." if published else "⚠️ لا يوجد فصول في الطابور للنشر."
        )
        await query.edit_message_text(message, reply_markup=build_admin_keyboard())
        return ConversationHandler.END

    await query.edit_message_text("حدث خطأ غير متوقع، حاول مرة أخرى.")
    return ConversationHandler.END


async def receive_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin(user_id):
        await update.message.reply_text("غير مصرح لك بإضافة فصول.")
        return ConversationHandler.END

    chapter_text = update.message.text.strip()
    if not chapter_text:
        await update.message.reply_text("النص فارغ، أرسل الفصل مرة أخرى.")
        return ADD_CHAPTER

    await db_execute(add_chapter_to_queue, chapter_text)
    await update.message.reply_text(
        "✅ تم حفظ الفصل في الطابور بنجاح.",
        reply_markup=build_admin_keyboard(),
    )
    return ConversationHandler.END


async def receive_publish_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else None
    if not is_admin(user_id):
        await update.message.reply_text("غير مصرح لك بتغيير الإعدادات.")
        return ConversationHandler.END

    content = update.message.text.strip()
    try:
        hour, minute = map(int, content.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        new_time = f"{hour:02d}:{minute:02d}"
    except Exception:
        await update.message.reply_text(
            "صيغة غير صحيحة. أرسل الوقت بصيغة HH:MM مثل 18:30.",
        )
        return SET_TIME

    await db_execute(set_publish_time, new_time)
    await update.message.reply_text(
        f"✅ تم تحديث وقت النشر إلى {new_time}.",
        reply_markup=build_admin_keyboard(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "تم إلغاء العملية.", reply_markup=build_admin_keyboard()
    )
    return ConversationHandler.END


async def publish_next_chapter(application, manual: bool = False) -> bool:
    chapter = await db_execute(get_next_chapter)
    if not chapter:
        return False

    chapter_id = chapter["id"]
    content = chapter["content"]
    try:
        await application.bot.send_message(chat_id=CHANNEL_ID, text=content)
        await db_execute(delete_chapter, chapter_id)
        logger.info("Published chapter %s to channel %s", chapter_id, CHANNEL_ID)
        return True
    except Exception as exc:
        logger.error("Failed to publish chapter %s: %s", chapter_id, exc)
        if manual:
            raise
        return False


async def scheduler_loop(application) -> None:
    logger.info("Starting scheduler loop")
    while True:
        try:
            publish_time = await db_execute(get_publish_time)
            now = datetime.now(TIMEZONE)
            current_time = now.strftime("%H:%M")
            today = now.strftime("%Y-%m-%d")
            last_published = await db_execute(get_last_published_date)

            if current_time == publish_time and last_published != today:
                published = await publish_next_chapter(application)
                if published:
                    await db_execute(set_last_published_date, today)
                else:
                    logger.info("No chapter to publish at scheduled time %s", publish_time)
        except Exception as err:
            logger.exception("Scheduler exception: %s", err)

        await asyncio.sleep(30)


async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start_health_server() -> None:
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Health server listening on port %s", PORT)


async def on_startup(application) -> None:
    await asyncio.to_thread(init_database)
    application.create_task(start_health_server())
    application.create_task(scheduler_loop(application))


def main() -> None:
    require_env_vars()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_button)],
        states={
            ADD_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_chapter)],
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_publish_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", start))
    app.add_handler(conversation)

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
