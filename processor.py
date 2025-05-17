from telethon import TelegramClient, events
import google_play_scraper as gps
from PIL import Image, ImageDraw, ImageFont
import io
import os
import logging
import config
import asyncio

# Setup logging (only errors and key actions)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

client = TelegramClient('processor', config.API_ID, config.API_HASH)

async def process_apk(message):
    if not message.document or not message.document.file_name.endswith('.apk'):
        return

    app_name = os.path.splitext(message.document.file_name)[0]
    apk_path = f"/tmp/{message.document.file_name}"

    try:
        # Download APK
        await message.download_media(file=apk_path)
        logger.info(f"Downloaded APK: {apk_path} ({message.document.size} bytes)")

        # Search for app on Google Play
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            await message.reply(f"No app found for '{app_name}'")
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
                    await message.reply(f"Could not download icon for '{app_title}'")
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

        # Upload APK and icon
        await client.send_file(
            config.PROCESSING_CHANNEL_ID,
            file=apk_path,
            caption=f"{app_title} APK",
            attributes=[DocumentAttributeFilename(message.document.file_name)]
        )
        await client.send_file(
            config.PROCESSING_CHANNEL_ID,
            file=icon_buffer,
            caption=f"{app_title} Renamed Icon",
            attributes=[DocumentAttributeFilename(f"{app_title}_icon.png")]
        )
        logger.info(f"Uploaded APK and icon for {app_title}")

        # Clean up
        os.remove(apk_path)
        logger.info(f"Cleaned up {apk_path}")

    except Exception as e:
        logger.error(f"Error processing {app_name}: {str(e)}")
        await message.reply(f"Error: {str(e)}")
        if os.path.exists(apk_path):
            os.remove(apk_path)

@client.on(events.NewMessage(chats=config.PROCESSING_CHANNEL_ID))
async def handler(event):
    await process_apk(event.message)

async def main():
    await client.start(phone=config.PHONE_NUMBER)
    logger.info("Processor started")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
