import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# إعدادات الـ Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- الإعدادات الأساسية من Railway ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID")

DB_PATH = "novels.db"
JOB_ID = "daily_novel_post"
scheduler = BackgroundScheduler(timezone=pytz.timezone("Africa/Cairo"))

# --- إعداد قاعدة البيانات وتخزين الوقت ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # جدول الفصول
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            is_posted INTEGER DEFAULT 0
        )
    ''')
    # جدول الإعدادات لحفظ الساعة والدقيقة
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # وضع قيم افتراضية للوقت لو مش موجودة (الساعة 6 مساءً مثلاً)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('hour', '18')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('minute', '0')")
    conn.commit()
    conn.close()

def get_setting(key, default):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else default

def update_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (str(value), key))
    conn.commit()
    conn.close()

def get_next_chapter():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, content FROM chapters WHERE is_posted = 0 ORDER BY id ASC LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return row

def mark_as_posted(chapter_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE chapters SET is_posted = 1 WHERE id = ?', (chapter_id,))
    conn.commit()
    conn.close()

# --- دالة النشر التلقائي ---
async def auto_publish(context: ContextTypes.DEFAULT_TYPE):
    chapter = get_next_chapter()
    if chapter:
        chapter_id, content = chapter
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=content, parse_mode="Markdown")
            mark_as_posted(chapter_id)
            if ADMIN_ID != 0:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ تم نشر الفصل رقم {chapter_id} تلقائياً في القناة!")
        except Exception as e:
            if ADMIN_ID != 0:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ فشل نشر الفصل رقم {chapter_id}. الخطأ: {e}")
    else:
        if ADMIN_ID != 0:
            await context.bot.send_message(chat_id=ADMIN_ID, text="⚠️ حان ميعاد النشر ولكن لا توجد فصول جديدة في الطابور!")

def scheduled_task(app):
    app.loop.create_task(auto_publish(ContextTypes.DEFAULT_TYPE(application=app)))

# تحديث وقت الجدولة ديناميكياً
def reschedule_job(app, hour, minute):
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    scheduler.add_job(scheduled_task, 'cron', hour=hour, minute=minute, id=JOB_ID, args=[app])

# --- لوحات التحكم (الأزرار) ---
def admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة فصل جديد", callback_data='add_chapter')],
        [InlineKeyboardButton("📊 الفصول المنتظرة", callback_data='view_status')],
        [InlineKeyboardButton("⚙️ إعدادات وقت النشر", callback_data='time_settings')],
        [InlineKeyboardButton("🚀 انشر فصلاً الآن", callback_data='publish_now')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("مرحباً بك في لوحة تحكم بوت الروايات! 📚", reply_markup=admin_keyboard())
    else:
        await update.message.reply_text("عذراً، هذا البوت مخصص للأدمن فقط.")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add_chapter':
        context.user_data['action'] = 'waiting_for_chapter'
        await query.edit_message_text("✍️ من فضلك قم بإرسال نص الفصل القادم الآن:")
        
    elif query.data == 'view_status':
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM chapters WHERE is_posted = 0')
        remaining = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM chapters WHERE is_posted = 1')
        posted = cursor.fetchone()[0]
        h = get_setting('hour', 18)
        m = get_setting('minute', 0)
        conn.close()
        
        text = f"📊 **إحصائيات الرواية:**\n\n🔹 فصول تم نشرها: {posted}\n⏳ فصول منتظرة: {remaining}\n⏰ ميعاد النشر الحالي: {h:02d}:{m:02d}"
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        
    elif query.data == 'time_settings':
        h = get_setting('hour', 18)
        m = get_setting('minute', 0)
        context.user_data['action'] = 'waiting_for_time'
        await query.edit_message_text(f"⏰ وقت النشر الحالي هو **{h:02d}:{m:02d}**.\n\nلتغييره، أرسل الوقت الجديد بصيغة (ساعة:دقيقة) بنظام 24 ساعة.\nمثال: `21:30` ليكون الساعة 9:30 مساءً، أو `15:00` ليكون الساعة 3 عصراً.")

    elif query.data == 'publish_now':
        await query.edit_message_text("🔄 جاري النشر الفوري...")
        await auto_publish(context)
        await context.bot.send_message(chat_id=ADMIN_ID, text="قائمة التحكم:", reply_markup=admin_keyboard())

# --- معالجة الرسائل النصية المكتوبة من الأدمن ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    action = context.user_data.get('action')

    # 1. حالة استقبال فصل جديد
    if action == 'waiting_for_chapter':
        chapter_text = update.message.text
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO chapters (content) VALUES (?)', (chapter_text,))
        conn.commit()
        conn.close()
        
        context.user_data['action'] = None
        await update.message.reply_text("✅ تم حفظ الفصل بنجاح وضمه للطابور!", reply_markup=admin_keyboard())

    # 2. حالة استقبال الوقت الجديد
    elif action == 'waiting_for_time':
        time_text = update.message.text.strip()
        try:
            parts = time_text.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                update_setting('hour', hour)
                update_setting('minute', minute)
                
                reschedule_job(context.application, hour, minute)
                
                context.user_data['action'] = None
                await update.message.reply_text(f"✅ تم تحديث وقت النشر التلقائي بنجاح إلى **{hour:02d}:{minute:02d}** يومياً!", reply_markup=admin_keyboard())
            else:
                await update.message.reply_text("❌ أرقام غير صحيحة! الساعة يجب أن تكون بين 0 و 23، والدقائق بين 0 و 59. جرب تاني:")
        except:
            await update.message.reply_text("❌ صيغة الوقت غير صحيحة. يرجى إرسالها بالشكل التالي `ساعة:دقيقة` مثل `18:30`:")

def main():
    init_db()
    
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على BOT_TOKEN!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    h = get_setting('hour', 18)
    m = get_setting('minute', 0)
    reschedule_job(app, h, m)
    scheduler.start()

    print("🚀 البوت يعمل الآن ولوحة التحكم بالوقت جاهزة...")
    app.run_polling()

if __name__ == '__main__':
    main()