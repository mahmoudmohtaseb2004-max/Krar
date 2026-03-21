import logging
import redis
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ==================== الإعدادات ====================
BOT_TOKEN = "8770091738:AAFEcZuqJfs6jfloBq1y5lwZgNaRnwi11Fg"
ADMIN_GROUP_ID = -1003771199618

REDIS_HOST = "redis-18716.c244.us-east-1-2.ec2.cloud.redislabs.com"
REDIS_PORT = 18716
REDIS_PASSWORD = "fKKKwO2rExeB4jWXNMxCEVcXibRdbXiz"
REDIS_PREFIX = "bot1"

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Web Server ====================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    server.serve_forever()


# ==================== دوال Redis ====================

def save_user(user_id): r.sadd(f"{REDIS_PREFIX}:users", user_id)
def get_all_users(): return list(r.smembers(f"{REDIS_PREFIX}:users"))
def get_users_count(): return r.scard(f"{REDIS_PREFIX}:users")
def save_message_map(admin_msg_id, user_id): r.set(f"{REDIS_PREFIX}:msg:{admin_msg_id}", user_id)
def get_user_from_message(admin_msg_id): return r.get(f"{REDIS_PREFIX}:msg:{admin_msg_id}")
def get_messages_count(): return len(r.keys(f"{REDIS_PREFIX}:msg:*"))
def ban_user(user_id): r.sadd(f"{REDIS_PREFIX}:banned", user_id)
def unban_user(user_id): r.srem(f"{REDIS_PREFIX}:banned", user_id)
def is_banned(user_id): return r.sismember(f"{REDIS_PREFIX}:banned", str(user_id))
def set_broadcast_mode(admin_id, value):
    if value: r.set(f"{REDIS_PREFIX}:broadcast:{admin_id}", "1", ex=300)
    else: r.delete(f"{REDIS_PREFIX}:broadcast:{admin_id}")
def is_broadcast_mode(admin_id): return r.exists(f"{REDIS_PREFIX}:broadcast:{admin_id}") == 1


# ==================== مساعد ====================

def get_user_display(user):
    return f"{user.full_name} (@{user.username})" if user.username else f"{user.full_name} (ID: {user.id})"

def get_message_type(message):
    if message.text: return "💬 نص"
    elif message.photo: return "🖼 صورة"
    elif message.video: return "🎥 فيديو"
    elif message.voice: return "🎤 رسالة صوتية"
    elif message.audio: return "🎵 موسيقى"
    elif message.video_note: return "⭕ فيديو دائري"
    elif message.sticker: return "🎭 ملصق"
    elif message.animation: return "🎞 GIF"
    elif message.document: return "📄 ملف"
    elif message.location: return "📍 موقع"
    elif message.contact: return "👤 جهة اتصال"
    elif message.poll: return "📊 استطلاع"
    else: return "📨 رسالة"


# ==================== /start ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # تشخيص: أرسل معلومات المحادثة
    debug_info = (
        f"🔍 *معلومات تشخيصية:*\n"
        f"Chat ID: `{chat.id}`\n"
        f"Chat Type: `{chat.type}`\n"
        f"User ID: `{user.id}`\n"
        f"Admin Group ID المضبوط: `{ADMIN_GROUP_ID}`"
    )
    logger.info(f"START - Chat ID: {chat.id}, User ID: {user.id}")

    if is_banned(user.id):
        await update.message.reply_text("⛔ أنت محظور من التواصل مع الإدارة.")
        return

    save_user(user.id)
    await update.message.reply_text(
        f"أهلاً {user.first_name}! 👋\n\n"
        "يمكنك إرسال أي رسالة وسيتم تحويلها إلى فريق الإدارة.\n"
        "سنرد عليك في أقرب وقت ممكن. 💬\n\n"
        + debug_info,
        parse_mode="Markdown"
    )


# ==================== أمر تشخيص ====================

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    await update.message.reply_text(
        f"🔍 *تشخيص:*\n"
        f"Chat ID: `{chat.id}`\n"
        f"Chat Type: `{chat.type}`\n"
        f"Chat Title: `{chat.title}`\n"
        f"User ID: `{user.id}`\n"
        f"Admin Group ID: `{ADMIN_GROUP_ID}`\n"
        f"هل هذه المجموعة هي مجموعة الأدمن؟ `{chat.id == ADMIN_GROUP_ID}`",
        parse_mode="Markdown"
    )


# ==================== رسائل المستخدمين ====================

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    chat = update.effective_chat

    logger.info(f"رسالة واردة - Chat ID: {chat.id}, User ID: {user.id}, Type: {chat.type}")

    if chat.id == ADMIN_GROUP_ID:
        logger.info("الرسالة من مجموعة الأدمن - تجاهل")
        return

    if is_banned(user.id):
        await message.reply_text("⛔ أنت محظور من التواصل مع الإدارة.")
        return

    save_user(user.id)

    header = (
        f"📩 *رسالة جديدة* | {get_message_type(message)}\n"
        f"👤 {get_user_display(user)}\n"
        f"🆔 `{user.id}`\n"
        f"{'—' * 22}"
    )

    try:
        logger.info(f"محاولة إرسال للمجموعة: {ADMIN_GROUP_ID}")
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=header, parse_mode="Markdown")
        forwarded = await message.forward(chat_id=ADMIN_GROUP_ID)
        save_message_map(forwarded.message_id, user.id)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 بث للجميع", callback_data=f"broadcast:{user.id}")],
            [InlineKeyboardButton("🚫 حظر هذا المستخدم", callback_data=f"ban:{user.id}")]
        ])

        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text="⬆️ *ردّ مباشرة* على الرسالة المُحالة أعلاه للرد على المستخدم.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        logger.info("✅ تم إرسال الرسالة للمجموعة بنجاح")
        await message.reply_text("✅ تم إرسال رسالتك للإدارة، سنرد عليك قريباً!")

    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال للمجموعة: {e}", exc_info=True)
        await message.reply_text(f"❌ خطأ: {e}")


# ==================== ردود المشرفين ====================

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.reply_to_message:
        return

    target_user_id = get_user_from_message(message.reply_to_message.message_id)
    if not target_user_id:
        return

    try:
        await context.bot.send_message(chat_id=int(target_user_id), text="💬 *رد من الإدارة:*", parse_mode="Markdown")
        await message.forward(chat_id=int(target_user_id))
        await message.reply_text("✅ تم إرسال ردك للمستخدم!")
    except Exception as e:
        await message.reply_text(f"❌ فشل الإرسال: {e}")


# ==================== الأزرار ====================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_chat.id != ADMIN_GROUP_ID:
        return

    data = query.data

    if data.startswith("ban:"):
        user_id = int(data.split(":")[1])
        ban_user(user_id)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 بث للجميع", callback_data=f"broadcast:{user_id}")],
            [InlineKeyboardButton("✅ فك الحظر", callback_data=f"unban:{user_id}")]
        ]))
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🚫 تم حظر المستخدم `{user_id}`.", parse_mode="Markdown")
        try: await context.bot.send_message(chat_id=user_id, text="⛔ تم حظرك من التواصل مع الإدارة.")
        except: pass

    elif data.startswith("unban:"):
        user_id = int(data.split(":")[1])
        unban_user(user_id)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 بث للجميع", callback_data=f"broadcast:{user_id}")],
            [InlineKeyboardButton("🚫 حظر هذا المستخدم", callback_data=f"ban:{user_id}")]
        ]))
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"✅ تم فك حظر المستخدم `{user_id}`.", parse_mode="Markdown")
        try: await context.bot.send_message(chat_id=user_id, text="✅ تم فك حظرك، يمكنك التواصل مجدداً.")
        except: pass

    elif data.startswith("broadcast:"):
        set_broadcast_mode(query.from_user.id, True)
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text="📢 *وضع البث*\n\nأرسل الرسالة التي تريد بثها.\nأرسل /cancel للإلغاء.",
            parse_mode="Markdown"
        )


# ==================== البث ====================

async def do_broadcast(context, message, text=None):
    users = get_all_users()
    success, failed = 0, 0
    await message.reply_text(f"⏳ جاري البث لـ {len(users)} مستخدم...")

    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text="📢 *إعلان من الإدارة:*", parse_mode="Markdown")
            if text:
                await context.bot.send_message(chat_id=int(uid), text=text)
            else:
                await message.forward(chat_id=int(uid))
            success += 1
        except:
            failed += 1

    await message.reply_text(f"✅ *اكتمل البث!*\n\n• نجح: {success}\n• فشل: {failed}", parse_mode="Markdown")


# ==================== رسائل الأدمن ====================

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return

    admin_id = update.effective_user.id

    if is_broadcast_mode(admin_id):
        if message.text == "/cancel":
            set_broadcast_mode(admin_id, False)
            await message.reply_text("❌ تم إلغاء البث.")
            return
        set_broadcast_mode(admin_id, False)
        await do_broadcast(context, message)
        return

    if message.reply_to_message:
        await handle_admin_reply(update, context)


# ==================== أوامر ====================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: /broadcast رسالتك هنا")
        return
    await do_broadcast(context, update.message, " ".join(context.args))

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: /ban USER_ID")
        return
    try:
        user_id = int(context.args[0])
        ban_user(user_id)
        await update.message.reply_text(f"🚫 تم حظر `{user_id}`.", parse_mode="Markdown")
        try: await context.bot.send_message(chat_id=user_id, text="⛔ تم حظرك من التواصل مع الإدارة.")
        except: pass
    except ValueError:
        await update.message.reply_text("❌ ID غير صحيح.")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    if not context.args:
        await update.message.reply_text("📌 الاستخدام: /unban USER_ID")
        return
    try:
        user_id = int(context.args[0])
        unban_user(user_id)
        await update.message.reply_text(f"✅ تم فك حظر `{user_id}`.", parse_mode="Markdown")
        try: await context.bot.send_message(chat_id=user_id, text="✅ تم فك حظرك، يمكنك التواصل مجدداً.")
        except: pass
    except ValueError:
        await update.message.reply_text("❌ ID غير صحيح.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID: return
    await update.message.reply_text(
        f"📊 *إحصائيات البوت الأول:*\n\n"
        f"👥 المستخدمين: {get_users_count()}\n"
        f"📨 الرسائل: {get_messages_count()}\n"
        f"🚫 المحظورين: {r.scard(f'{REDIS_PREFIX}:banned')}",
        parse_mode="Markdown"
    )


# ==================== التشغيل ====================

ALL_MESSAGES = (
    filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE |
    filters.AUDIO | filters.VIDEO_NOTE | filters.Sticker.ALL |
    filters.ANIMATION | filters.Document.ALL |
    filters.LOCATION | filters.CONTACT | filters.POLL
)

def main():
    try:
        r.ping()
        logger.info("✅ متصل بـ Redis Cloud!")
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بـ Redis: {e}")
        return

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info("✅ Web server شغال على port 8080")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Chat(ADMIN_GROUP_ID) & ALL_MESSAGES, handle_admin_message))
    app.add_handler(MessageHandler(~filters.Chat(ADMIN_GROUP_ID) & ALL_MESSAGES, handle_user_message))

    logger.info("✅ البوت الأول يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
