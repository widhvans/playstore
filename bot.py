from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google_play_scraper as gps
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io
import os
import config

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send an app name to download its APK and renamed icon!")

async def get_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app_name = update.message.text
    try:
        # Search for the app
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            await update.message.reply_text(f"No app found for '{app_name}'")
            return

        # Get app details
        app_id = results[0]['appId']
        app_details = gps.app(app_id, lang='en', country='us')
        icon_url = app_details['icon']
        app_title = app_details['title']

        # Download icon
        async with aiohttp.ClientSession() as session:
            async with session.get(icon_url) as resp:
                if resp.status != 200:
                    await update.message.reply_text(f"Could not download icon for '{app_title}'")
                    return
                icon_data = await resp.read()

            # Simulate APK download (replace with real APK source)
            apk_url = f"https://apkpure.com/{app_id}/download"  # Placeholder
            async with session.get(apk_url) as apk_resp:
                if apk_resp.status != 200:
                    await update.message.reply_text(f"Could not download APK for '{app_title}'")
                    return
                apk_data = await apk_resp.read()

        # Process icon: add app name as text
        icon_img = Image.open(io.BytesIO(icon_data)).convert("RGBA")
        draw = ImageDraw.Draw(icon_img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)  # Ensure font is available
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

        # Save APK temporarily
        apk_filename = f"{app_title}.apk"
        with open(apk_filename, "wb") as f:
            f.write(apk_data)

        # Send APK
        await update.message.reply_document(document=open(apk_filename, "rb"),
                                         filename=f"{app_title}.apk",
                                         caption=f"{app_title} APK")

        # Send modified icon as document
        await update.message.reply_document(document=icon_buffer,
                                         filename=f"{app_title}_icon.png",
                                         caption=f"{app_title} Renamed Icon")

        # Clean up
        os.remove(apk_filename)
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_app))
    app.run_polling()

if __name__ == '__main__':
    main()
