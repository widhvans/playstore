from telethon import TelegramClient, events
import config
import os

client = TelegramClient('bot', config.API_ID, config.API_HASH).start(bot_token=config.BOT_TOKEN)

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply('Send me a file to download and re-upload as a document!')
    raise events.StopPropagation

@client.on(events.NewMessage(incoming=True))
async def handle_file(event):
    if event.message.file:
        try:
            # Download the file
            file_path = await event.message.download_media()
            file_name = event.message.file.name or 'downloaded_file'
            
            # Re-upload as document
            await client.send_file(
                event.chat_id,
                file_path,
                caption='Re-uploaded as document',
                force_document=True
            )
            
            # Clean up
            os.remove(file_path)
            await event.reply('File re-uploaded successfully!')
        except Exception as e:
            await event.reply(f'Error: {str(e)}')
    else:
        await event.reply('Please send a file!')

client.run_until_disconnected()
