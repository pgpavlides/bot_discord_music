import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import logging
from async_timeout import timeout
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# FFMPEG options for high quality audio
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5" -acodec libopus -b:a 192k -ar 48000 -bufsize 3M -maxrate 3M'
}

# YouTube DL options for better quality
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'extractaudio': True,
    'audioformat': 'opus',
    'audioquality': 0,  # Best quality
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'cachedir': False,
    'extract_flat': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '192'
    }],
    'prefer_ffmpeg': True,
    'compat_opts': {'no-youtube-unavailable-videos': True}
}

# Initialize clients
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
            description='A music bot that plays songs from YouTube and Spotify'
        )
        self.queue = {}
        self.now_playing = {}
        
    async def setup_hook(self):
        await self.load_extension("music_cog")
        logger.info("Music cog has been added.")
        
    async def on_ready(self):
        logger.info(f'Bot is ready! Logged in as {self.user}')
        print(f'Bot ID: {self.user.id}')
        print('Connected to servers:')
        for guild in self.guilds:
            print(f'- {guild.name} (ID: {guild.id})')

async def main():
    bot = MusicBot()
    
    try:
        await bot.start(TOKEN)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())