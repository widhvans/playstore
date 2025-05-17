from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google_play_scraper as gps
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io
import os
import logging
import config

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send an APK file (up to 50MB). I'll add the app name to its icon and re-upload both. For larger files, use an external file host.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text(f"Error: {str(context.error)}")

async def handle_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    if not file.file_name.endswith('.apk'):
        await update.message.reply_text("Please send an APK file!")
        return

    # Check file size (Telegram limit: 50MB)
    if file.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("File too large (>50MB). Telegram bots can't handle this. Upload to a file host (e.g., Google Drive) and share the link.")
        return

    # Extract app name from filename
    app_name = os.path.splitext(file.file_name)[0]
    apk_path = f"{app_name}.apk"

    try:
        # Download APK
        file_obj = await file.get_file()
        await file_obj.download_to_drive(apk_path)
        logger.info(f"Downloaded APK: {apk_path}")

        # Search for app on Google Play
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            await update.message.reply_text(f"No app found for '{app_name}'")
            os.remove(apk_path)
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
                    os.remove(apk_path)
                    return
                icon_data = await resp.read()

        # Process icon: add app name as text
        icon_img = Image.open(io.BytesIO(icon_data)).convert("RGBA")
        draw = ImageDraw.Draw(icon_img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
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

        # Send original APK with same name
        await update.message.reply_document(document=open(apk_path, "rb"),
                                         filename=file.file_name,
                                         caption=f"{app_title} APK")

        # Send modified icon as document
        await update.message.reply_document(document=icon_buffer,
                                         filename=f"{app_title}_icon.png",
                                         caption=f"{app_title} Renamed Icon")

        # Clean up
        os.remove(apk_path)
        logger.info(f"Cleaned up {apk_path}")

    except Exception as e:
        logger.error(f"Error processing {app_name}: {str(e)}")
        await update.message.reply_text(f"Error: {str(e)}")
        if os.path.exists(apk_path):
            os.remove(apk_path)

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_apk))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
