import discord
from discord.ext import commands
import google_play_scraper as gps
import aiohttp
import config

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready as {bot.user}')

@bot.command()
async def app(ctx, *, app_name):
    try:
        # Search for the app on Google Play Store
        results = gps.search(app_name, lang='en', country='us')
        if not results:
            await ctx.send(f"No app found for '{app_name}'")
            return

        # Get the first result's app ID
        app_id = results[0]['appId']
        # Fetch app details
        app_details = gps.app(app_id, lang='en', country='us')
        
        # Get app icon URL
        icon_url = app_details['icon']
        app_title = app_details['title']

        # Download the icon
        async with aiohttp.ClientSession() as session:
            async with session.get(icon_url) as resp:
                if resp.status == 200:
                    icon_data = await resp.read()
                    # Save icon temporarily
                    with open('temp_icon.png', 'wb') as f:
                        f.write(icon_data)
                    
                    # Send the icon to Discord
                    file = discord.File('temp_icon.png', filename=f"{app_title}_icon.png")
                    await ctx.send(f"**{app_title}** Icon:", file=file)
                else:
                    await ctx.send(f"Could not download icon for '{app_title}'")
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

bot.run(config.BOT_TOKEN)
