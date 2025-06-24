import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, CommandHandler, ContextTypes
from sqlalchemy import create_engine, text
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask, request
import asyncio
import threading
from pytz import timezone

# Replace these with your actual credentials
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_URL = os.environ.get("DB_URL")
WEBHOOK_DOMAIN = os.environ.get("WEBHOOK_DOMAIN")
DISCUSSION_GROUP_NAME = "Cheeky Softwear Club Chat"
TIME_TO_CLEAR_DB = 4 # Time to clear the database (4 AM)

engine = create_engine(DB_URL)

# Initialize Scheduler
scheduler = AsyncIOScheduler(timezone=timezone('Asia/Singapore'))

# Store message
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(update)
    if update.message and update.message.chat.title == DISCUSSION_GROUP_NAME and update.message.reply_to_message:
        print("Storing message in database...")
        message_id = update.message.message_id
        username = update.message.from_user.username or update.message.from_user.full_name
        text_msg = update.message.text or ""
        now = datetime.now()
        message_thread_id = update.message.message_thread_id

        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO messages (id, message_id, username, text, timestamp, message_thread_id)
                VALUES (gen_random_uuid(), :msg_id, :username, :text, :ts, :message_thread_id)
            """), {
                "msg_id": message_id,
                "username": username,
                "text": text_msg,
                "ts": now,
                "message_thread_id": message_thread_id
            })

            if result.rowcount == 1:
                print("✅ Insert into messages successful.")
            else:
                print("⚠️ Insert may have failed.")

async def handle_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Handling item...")
    if update.message and update.message.chat.title == DISCUSSION_GROUP_NAME:
        print("Storing item in database...")
        message_id = update.message.message_id
        caption = update.message.caption
        if caption:
            with engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO items (message_id, caption)
                    VALUES (:msg_id, :caption)
                """), {
                    "msg_id": message_id,
                    "caption": caption,
                })

                if result.rowcount == 1:
                    print("✅ Insert into items successful.")
                else:
                    print("⚠️ Insert may have failed.")

# Manual command to query deleted comments
async def show_deleted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.from_user:
        username = update.message.from_user.username
        deleted = []
        chat_id = update.effective_chat.id

        # Get all messages and check which no longer exist
        with engine.connect() as conn:
            messages = conn.execute(text("SELECT message_id, username, text, message_thread_id FROM messages")).fetchall()

            for msg in messages:
                try:
                    forwarded_msg = await context.bot.forward_message(chat_id=chat_id, from_chat_id=chat_id, message_id=msg.message_id)
                    # If forwarding succeeds, delete the forwarded message
                    await context.bot.delete_message(chat_id=chat_id,message_id=forwarded_msg.message_id)
                except:
                    with engine.connect() as conn:
                        item_row = conn.execute(text(
                            "SELECT caption FROM items WHERE message_id = :message_thread_id"
                        ), {"message_thread_id": msg.message_thread_id}).fetchone()

                    item_caption = item_row.caption if item_row else "(unknown item)"

                    deleted.append(f"@{msg.username}: {msg.text}\nItem: {item_caption}\n\n")

        with engine.connect() as conn:
            result = conn.execute(text("SELECT chat_id FROM usernames WHERE username = :uname"), {"uname": username})
            row = result.fetchone()
        if not row:
            print("❌ chat_id not found in database.")
            return
        target_chat_id = int(row.chat_id)
        if not deleted:
            message = "No deleted messages detected."
        else:
            message = "Deleted messages:\n\n" + "\n".join(deleted)

        await context.bot.send_message(chat_id=target_chat_id, text=message)

# Clear messages every day at 4am
async def clear_db():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM messages"))
        conn.execute(text("DELETE FROM items"))
    now = datetime.now().strftime("%Y-%m-%d")
    print(f"✅ Database cleared successfully at {TIME_TO_CLEAR_DB}AM on {now}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO usernames (username, chat_id)
                VALUES (:username, :chat_id)
                ON CONFLICT (username) DO NOTHING
            """), {
                "username": update.effective_chat.username,
                "chat_id": update.effective_chat.id,
            })

            if result.rowcount == 1:
                print("✅ Insert into usernames successful.")

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Hi {update.effective_chat.username}, I will now store your messages in the database. Use /deleted in the discussion group to see deleted comments.")

# -- Telegram Application --
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(MessageHandler((filters.TEXT & (~filters.COMMAND)), handle_message))
telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_item))
telegram_app.add_handler(CommandHandler("deleted", show_deleted))
telegram_app.add_handler(CommandHandler("start", start))

# --- Flask Server ---
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is live."

@flask_app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    # Safely schedule the update on the running loop
    asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), loop)
    return 'OK'

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

async def start_bot():
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_DOMAIN}/webhook/{BOT_TOKEN}")
    scheduler.start()
    scheduler.add_job(clear_db, trigger='cron', hour=TIME_TO_CLEAR_DB, minute=0)
    print("✅ Bot initialized and webhook set.")

# --- Main ---
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Run bot in main thread’s loop and keep it alive
    loop.create_task(start_bot())
    loop.run_forever()