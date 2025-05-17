from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google_play_scraper as gps
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io
import os
import logging
import config

# Setup logging (only errors and key actions)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)  # Suppress httpx logs
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Upload your APK (up to 500MB) to https://transfer.sh and send the download URL. "
        "I'll add the app name to its icon and provide a new URL for the APK."
    )
    logger.info("Bot started")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text(f"Error: {str(context.error)}")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith('http') or not url.lower().endswith('.apk'):
        await update.message.reply_text("Please send a valid APK URL from https://transfer.sh!")
        logger.warning(f"Invalid URL received: {url}")
        return

    # Extract app name from URL
    app_name = os.path.splitext(os.path.basename(url))[0]
    apk_path = f"{app_name}.apk"

    try:
        # Download APK from URL
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await update.message.reply_text("Could not download APK from URL")
                    logger.error(f"Failed to download APK: {url}, status: {resp.status}")
                    return
                with open(apk_path, 'wb') as f:
                    f.write(await resp.read())
        logger.info(f"Downloaded APK: {apk_path}")

        # Search for app on Google Play
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            await update.message.reply_text(f"No app found for '{app_name}'")
            logger.warning(f"No app found for: {app_name}")
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
                    logger.error(f"Failed to download icon: {icon_url}")
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

        # Re-upload APK to Transfer.sh
        async with aiohttp.ClientSession() as session:
            with open(apk_path, 'rb') as f:
                async with session.put(f"https://transfer.sh/{os.path.basename(apk_path)}", data=f) as resp:
                    if resp.status != 200:
                        await update.message.reply_text("Could not upload APK to Transfer.sh")
                        logger.error(f"Failed to upload APK to Transfer.sh: {resp.status}")
                        os.remove(apk_path)
                        return
                    download_url = await resp.text()
        logger.info(f"Uploaded APK to Transfer.sh: {download_url}")

        # Send modified icon as document
        await update.message.reply_document(document=icon_buffer,
                                         filename=f"{app_title}_icon.png",
                                         caption=f"{app_title} Renamed Icon")

        # Send APK download URL
        await update.message.reply_text(f"APK re-uploaded with original name: {download_url}")
        logger.info(f"Sent APK URL for {app_title}: {download_url}")

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
