from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google_play_scraper as gps
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io
import os
import logging
import config
import tempfile
import shutil

# Setup logging (only errors and key actions)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)  # Suppress httpx logs
logger = logging.getLogger(__name__)

WEB_SERVER_URL = "http://localhost:8000"  # Local FastAPI server

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send an APK file (up to 500MB). I'll add the app name to its icon and re-upload both."
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

    # Extract app name from filename
    app_name = os.path.splitext(file.file_name)[0]
    temp_dir = tempfile.mkdtemp()
    apk_path = os.path.join(temp_dir, file.file_name)

    try:
        file_size = file.file_size
        logger.info(f"Processing APK: {file.file_name} ({file_size} bytes)")

        # Download APK
        file_obj = await file.get_file()
        if file_size <= 50 * 1024 * 1024:
            # Direct download for ≤50MB
            await file_obj.download_to_drive(apk_path)
            logger.info(f"Downloaded APK directly: {apk_path}")
        else:
            # Download and upload to web server for >50MB
            async with aiohttp.ClientSession() as session:
                async with session.get(file_obj.file_path) as resp:
                    if resp.status != 200:
                        raise Exception("Failed to download APK from Telegram")
                    # Stream file to web server
                    async with session.post(f"{WEB_SERVER_URL}/upload/{file.file_name}", data=resp.content) as upload_resp:
                        if upload_resp.status != 200:
                            raise Exception(f"Failed to upload to web server: {await upload_resp.text()}")
                        apk_url = (await upload_resp.json())["url"]
                async with session.get(apk_url) as download_resp:
                    if download_resp.status != 200:
                        raise Exception("Failed to download from web server")
                    with open(apk_path, 'wb') as f:
                        f.write(await download_resp.read())
            logger.info(f"Downloaded APK via web server: {apk_path}")

        # Search for app on Google Play
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            await update.message.reply_text(f"No app found for '{app_name}'")
            logger.warning(f"No app found for: {app_name}")
            os.remove(apk_path)
            shutil.rmtree(temp_dir)
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
                    await update.message.reply_text(f"Could not download icon for '{app_title}'")
                    logger.error(f"Failed to download icon: {icon_url}")
                    os.remove(apk_path)
                    shutil.rmtree(temp_dir)
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
        logger.info(f"Processed icon for {app_title}")

        # Re-upload files
        if file_size <= 50 * 1024 * 1024:
            # Direct upload to Telegram for ≤50MB
            await update.message.reply_document(document=open(apk_path, "rb"),
                                             filename=file.file_name,
                                             caption=f"{app_title} APK")
            logger.info(f"Re-uploaded APK to Telegram: {file.file_name}")
        else:
            # Upload to web server for >50MB
            async with aiohttp.ClientSession() as session:
                with open(apk_path, 'rb') as f:
                    async with session.post(f"{WEB_SERVER_URL}/upload/{file.file_name}", data=f) as resp:
                        if resp.status != 200:
                            raise Exception(f"Failed to upload APK to web server: {await resp.text()}")
                        apk_url = (await resp.json())["url"]
            await update.message.reply_text(f"APK re-uploaded: {apk_url}")
            logger.info(f"Re-uploaded APK to web server: {apk_url}")

        # Send modified icon
        await update.message.reply_document(document=icon_buffer,
                                         filename=f"{app_title}_icon.png",
                                         caption=f"{app_title} Renamed Icon")
        logger.info(f"Sent icon for {app_title}")

        # Clean up
        os.remove(apk_path)
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up {apk_path}")

    except Exception as e:
        logger.error(f"Error processing {app_name}: {str(e)}")
        await update.message.reply_text(f"Error: {str(e)}")
        if os.path.exists(apk_path):
            os.remove(apk_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_apk))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
