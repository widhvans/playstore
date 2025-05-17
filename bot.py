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

CHUNK_SIZE = 50 * 1024 * 1024  # 50MB

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
        # Download APK (handle large files)
        file_obj = await file.get_file()
        file_size = file.file_size
        logger.info(f"Downloading APK: {file.file_name} ({file_size} bytes)")

        if file_size <= CHUNK_SIZE:
            # Direct download for ≤50MB
            await file_obj.download_to_drive(apk_path)
        else:
            # Chunked download for >50MB
            chunks = []
            offset = 0
            while offset < file_size:
                chunk_path = os.path.join(temp_dir, f"chunk_{offset}.part")
                async with aiohttp.ClientSession() as session:
                    async with session.get(file_obj.file_path, headers={'Range': f'bytes={offset}-{offset+CHUNK_SIZE-1}'}) as resp:
                        if resp.status != 206:
                            raise Exception("Chunk download failed")
                        with open(chunk_path, 'wb') as f:
                            f.write(await resp.read())
                chunks.append(chunk_path)
                offset += CHUNK_SIZE
            # Reassemble chunks
            with open(apk_path, 'wb') as f:
                for chunk_path in chunks:
                    with open(chunk_path, 'rb') as cf:
                        f.write(cf.read())
                    os.remove(chunk_path)

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
        if file_size <= CHUNK_SIZE:
            # Direct upload for ≤50MB
            await update.message.reply_document(document=open(apk_path, "rb"),
                                             filename=file.file_name,
                                             caption=f"{app_title} APK")
            logger.info(f"Re-uploaded APK to Telegram: {file.file_name}")
        else:
            # Chunked upload for >50MB
            chunk_paths = []
            with open(apk_path, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    chunk_path = os.path.join(temp_dir, f"chunk_{len(chunk_paths)}.part")
                    with open(chunk_path, 'wb') as cf:
                        cf.write(chunk)
                    chunk_paths.append(chunk_path)
            for i, chunk_path in enumerate(chunk_paths):
                await update.message.reply_document(document=open(chunk_path, "rb"),
                                                 filename=f"{file.file_name}.part{i}",
                                                 caption=f"Chunk {i+1} of {app_title} APK")
                logger.info(f"Uploaded chunk {i+1} for {file.file_name}")
            await update.message.reply_text(
                f"APK >50MB split into {len(chunk_paths)} chunks. "
                "Download all parts and combine with: cat {file.file_name}.part* > {file.file_name}"
            )

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
