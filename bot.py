from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import config

# Setup logging (only errors and key actions)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)  # Suppress httpx logs
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send an APK file (up to 500MB). I'll process it and send back the APK and icon with the app name added."
    )
    logger.info("Bot started")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text(f"Error: {str(context.error)}")

async def handle_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    if not file or not file.file_name.endswith('.apk'):
        await update.message.reply_text("Please send an APK file!")
        logger.warning("Non-APK file received")
        return

    try:
        # Forward message to processing channel
        await update.message.forward(chat_id=config.PROCESSING_CHANNEL_ID)
        logger.info(f"Forwarded APK: {file.file_name} ({file.file_size} bytes)")
        await update.message.reply_text("APK forwarded for processing. Please wait for results.")
    except Exception as e:
        logger.error(f"Error forwarding {file.file_name}: {str(e)}")
        await update.message.reply_text(f"Error: {str(e)}")

async def handle_channel_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post and update.channel_post.chat_id == config.PROCESSING_CHANNEL_ID:
        if update.channel_post.document and update.channel_post.document.file_name.endswith(('.apk', '.png')):
            # Forward results to the original user
            if update.channel_post.reply_to_message:
                original_user_id = update.channel_post.reply_to_message.forward_from.id if update.channel_post.reply_to_message.forward_from else None
                if original_user_id:
                    await update.channel_post.forward(chat_id=original_user_id)
                    logger.info(f"Forwarded result: {update.channel_post.document.file_name} to user {original_user_id}")

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_apk))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_update))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
