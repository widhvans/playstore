import os
import time
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TOKEN

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send any file to download and upload as a document.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file() if update.message.document else await update.message.photo[-1].get_file()
    file_name = update.message.document.file_name if update.message.document else f"photo_{int(time.time())}.jpg"
    
    status_message = await update.message.reply_text("Downloading: 0%")
    
    # Download file
    file_path = f"downloads/{file_name}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await file.download_to_drive(file_path)
    
    await status_message.edit_text("Downloading: 100%\nUploading: 0%")
    
    # Upload as document
    with open(file_path, 'rb') as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=f,
            caption="Uploaded document",
            disable_notification=True
        )
    
    await status_message.edit_text("Uploading: 100%\nCompleted!")
    
    # Clean up
    os.remove(file_path)
    
    # Flood control
    time.sleep(5)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update:
        await update.message.reply_text("An error occurred. Please try again.")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_error_handler(error_handler)
    
    app.run_polling()

if __name__ == "__main__":
    main()
