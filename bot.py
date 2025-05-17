from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google_play_scraper as gps
import aiohttp
import config

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send an app name to get its icon!")

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
                if resp.status == 200:
                    icon_data = await resp.read()
                    # Send icon
                    await update.message.reply_photo(photo=icon_data, caption=f"{app_title} Icon")
                else:
                    await update.message.reply_text(f"Could not download icon for '{app_title}'")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_app))
    app.run_polling()

if __name__ == '__main__':
    main()
