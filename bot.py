from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import google_play_scraper as gps
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io
import os
import logging
import config
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio

# Setup logging (only errors and key actions)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)  # Suppress httpx logs
logger = logging.getLogger(__name__)

INPUT_DIR = "/root/playstore/input"
OUTPUT_DIR = "/root/playstore/output"

# Ensure directories exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

class FileHandler(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.apk'):
            filename = os.path.basename(event.src_path)
            asyncio.run_coroutine_threadsafe(
                process_apk(None, filename, self.bot), asyncio.get_event_loop()
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Upload your APK (up to 500MB) to /root/playstore/input/ on the server via SCP/SFTP. "
        "Use /process <filename> to process it, or I'll auto-detect new files. "
        "I'll add the app name to the icon and save the APK and icon to /root/playstore/output/."
    )
    logger.info("Bot started")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text(f"Error: {str(context.error)}")

async def process_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a filename: /process <filename.apk>")
        return
    filename = context.args[0]
    if not filename.endswith('.apk'):
        await update.message.reply_text("Please provide an APK filename!")
        logger.warning(f"Invalid filename: {filename}")
        return
    apk_path = os.path.join(INPUT_DIR, filename)
    if not os.path.exists(apk_path):
        await update.message.reply_text(f"File not found: {apk_path}")
        logger.warning(f"File not found: {apk_path}")
        return
    await process_apk(update, filename, context.bot)

async def process_apk(update: Update, filename: str, bot):
    apk_path = os.path.join(INPUT_DIR, filename)
    app_name = os.path.splitext(filename)[0]
    output_apk_path = os.path.join(OUTPUT_DIR, filename)

    try:
        # Search for app on Google Play
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            message = f"No app found for '{app_name}'"
            logger.warning(message)
            if update:
                await update.message.reply_text(message)
            return

        # Get app details
        app_id = results[0]['appId']
        app_details = gps.app(app_id, lang='en', country='us')
        icon_url = app_details['icon']
        app_title = app_details['title']
        logger.info(f"Fetched details for {app_title}")

        # Download icon
        async with aiohttp.ClientSession() as session:
            async with session.get(icon_url) as resp:
                if resp.status != 200:
                    message = f"Could not download icon for '{app_title}'"
                    logger.error(message)
                    if update:
                        await update.message.reply_text(message)
                    return
                icon_data = await resp.read()

        # Process icon: add app name as text
        icon_img = Image.open(io.BytesIO(icon_data)).convert("RGBA")
        draw = ImageDraw.Draw(icon_img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
            logger.warning("Using default font; arial.ttf not found")
        text_bbox = draw.textbbox((0, 0), app_title, font=font)
        text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        img_width, img_height = icon_img.size
        draw.text(((img_width - text_width) // 2, img_height - text_height - 10),
                  app_title, fill="white", font=font, stroke_width=2, stroke_fill="black")

        # Save modified icon
        icon_buffer = io.BytesIO()
        icon_img.save(icon_buffer, format="PNG")
        icon_buffer.seek(0)
        icon_path = os.path.join(OUTPUT_DIR, f"{app_title}_icon.png")
        with open(icon_path, 'wb') as f:
            f.write(icon_buffer.getvalue())
        logger.info(f"Processed icon for {app_title}")

        # Copy APK to output directory (preserve original name)
        os.rename(apk_path, output_apk_path)
        logger.info(f"Moved APK to {output_apk_path}")

        # Send icon via Telegram
        if update:
            with open(icon_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"{app_title}_icon.png",
                    caption=f"{app_title} Renamed Icon"
                )
            await update.message.reply_text(
                f"APK processed! Find it at: {output_apk_path}\nIcon saved at: {icon_path}"
            )
        logger.info(f"Sent results for {app_title}")

    except Exception as e:
        logger.error(f"Error processing {app_name}: {str(e)}")
        if update:
            await update.message.reply_text(f"Error: {str(e)}")
        if os.path.exists(apk_path):
            os.remove(apk_path)

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("process", process_command))
    app.add_error_handler(error_handler)

    # Setup file watcher
    event_handler = FileHandler(app.bot)
    observer = Observer()
    observer.schedule(event_handler, INPUT_DIR, recursive=False)
    observer.start()
    logger.info("File watcher started")

    app.run_polling()

    # Stop observer when bot stops
    observer.stop()
    observer.join()

if __name__ == '__main__':
    main()
