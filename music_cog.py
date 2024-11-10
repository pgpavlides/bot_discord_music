import discord
from discord.ext import commands
import logging
import asyncio
from async_timeout import timeout
import yt_dlp as youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

logger = logging.getLogger('discord')

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')


# FFMPEG options - simplified and more stable
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# YouTube DL options - optimized for stability
ytdl_format_options = {
    'format': 'bestaudio',
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'force-ipv4': True
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_volume = 0.5

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Music cog is ready!")

    async def get_yt_info(self, url, search=False):
        """Get YouTube video info"""
        try:
            if search:
                url = f"ytsearch:{url}"
            
            info = await self.bot.loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(url, download=False)
            )
            
            if 'entries' in info:
                info = info['entries'][0]
                
            return {
                'url': info['url'],
                'title': info['title'],
                'duration': info.get('duration', 0)
            }
        except Exception as e:
            logger.error(f"Error getting YT info: {e}")
            return None

    async def play_next(self, ctx):
        if not ctx.guild.id in self.bot.queue or not self.bot.queue[ctx.guild.id]:
            return
            
        try:
            voice_client = ctx.voice_client
            if voice_client and voice_client.is_connected():
                current_song = self.bot.queue[ctx.guild.id][0]
                
                # Always get fresh stream URL
                fresh_info = await self.get_yt_info(current_song['source_url'])
                if not fresh_info:
                    await ctx.send("❌ Error getting stream URL, skipping song...")
                    self.bot.queue[ctx.guild.id].pop(0)
                    return await self.play_next(ctx)
                
                source = await discord.FFmpegOpusAudio.from_probe(
                    fresh_info['url'],
                    **FFMPEG_OPTIONS
                )
                
                def after_playing(error):
                    if error:
                        logger.error(f"Error in playback: {error}")
                    self.bot.loop.create_task(self.handle_playback_end(ctx))
                
                voice_client.play(source, after=after_playing)
                self.bot.now_playing[ctx.guild.id] = current_song['title']
                
                duration = current_song.get('duration', 0)
                duration_str = f" ({int(duration//60)}:{int(duration%60):02d})" if duration else ""
                await ctx.send(f'🎵 Now playing: {current_song["title"]}{duration_str}')
                
        except Exception as e:
            logger.error(f"Error in play_next: {e}")
            await ctx.send(f"❌ Error playing song: {str(e)}")
            if ctx.guild.id in self.bot.queue and self.bot.queue[ctx.guild.id]:
                self.bot.queue[ctx.guild.id].pop(0)
            await self.play_next(ctx)

    async def handle_playback_end(self, ctx):
        """Handle song end and play next"""
        if ctx.guild.id in self.bot.queue and self.bot.queue[ctx.guild.id]:
            self.bot.queue[ctx.guild.id].pop(0)
            await self.play_next(ctx)

    @commands.command(name='play', help='Plays a song from YouTube or Spotify')
    async def play(self, ctx, *, query):
        if not ctx.author.voice:
            return await ctx.send('❌ You need to be in a voice channel!')

        try:
            if not ctx.voice_client:
                await self.join(ctx)

            if ctx.guild.id not in self.bot.queue:
                self.bot.queue[ctx.guild.id] = []

            if 'spotify.com' in query:
                await self.handle_spotify(ctx, query)
            else:
                await self.add_to_queue(ctx, query)
        except Exception as e:
            logger.error(f"Error in play command: {e}")
            await ctx.send(f"❌ Error: {str(e)}")

    async def add_to_queue(self, ctx, query):
        try:
            await ctx.send(f'🔍 Searching for: {query}')
            
            # Handle direct YouTube URLs
            if 'youtube.com' in query or 'youtu.be' in query:
                video_info = await self.get_yt_info(query)
            else:
                video_info = await self.get_yt_info(query, search=True)
            
            if not video_info:
                return await ctx.send("❌ Could not find song.")
            
            song_info = {
                'source_url': query,
                'title': video_info['title'],
                'duration': video_info['duration']
            }

            self.bot.queue[ctx.guild.id].append(song_info)
            
            if not ctx.voice_client.is_playing():
                await self.play_next(ctx)
            else:
                duration = song_info.get('duration', 0)
                duration_str = f" ({int(duration//60)}:{int(duration%60):02d})" if duration else ""
                await ctx.send(f'➕ Added to queue: {song_info["title"]}{duration_str}')

        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            await ctx.send(f"❌ Error adding to queue: {str(e)}")

    async def handle_spotify(self, ctx, url):
        try:
            if 'track' in url:
                track_id = url.split('/')[-1].split('?')[0]
                track = spotify.track(track_id)
                search_query = f"{track['name']} {track['artists'][0]['name']} official audio"
                await self.add_to_queue(ctx, search_query)
            elif 'playlist' in url:
                await ctx.send('📝 Adding playlist tracks to queue...')
                playlist_id = url.split('/')[-1].split('?')[0]
                results = spotify.playlist_tracks(playlist_id)
                added_tracks = 0
                
                for item in results['items']:
                    if item['track']:
                        track = item['track']
                        search_query = f"{track['name']} {track['artists'][0]['name']} official audio"
                        await self.add_to_queue(ctx, search_query)
                        added_tracks += 1
                        if added_tracks % 5 == 0:
                            await ctx.send(f'✅ Added {added_tracks} tracks so far...')
                            
                await ctx.send(f'✅ Added {added_tracks} tracks from playlist to queue!')
        except Exception as e:
            logger.error(f"Error handling Spotify URL: {e}")
            await ctx.send(f"❌ Error processing Spotify URL: {str(e)}")

    @commands.command(name='join', help='Joins your voice channel')
    async def join(self, ctx):
        if not ctx.author.voice:
            return await ctx.send('❌ You need to be in a voice channel!')
        
        channel = ctx.author.voice.channel
        try:
            if ctx.voice_client is not None:
                await ctx.voice_client.move_to(channel)
            else:
                await channel.connect()
            
            self.bot.queue[ctx.guild.id] = []
            await ctx.send(f'✅ Joined {channel.name}')
        except Exception as e:
            logger.error(f"Error joining channel: {e}")
            await ctx.send(f"❌ Error joining channel: {str(e)}")

    @commands.command(name='leave', help='Leaves the voice channel')
    async def leave(self, ctx):
        if not ctx.voice_client:
            return await ctx.send('❌ I am not in a voice channel!')
            
        try:
            await ctx.voice_client.disconnect()
            if ctx.guild.id in self.bot.queue:
                del self.bot.queue[ctx.guild.id]
            if ctx.guild.id in self.bot.now_playing:
                del self.bot.now_playing[ctx.guild.id]
            await ctx.send('👋 Disconnected from voice channel')
        except Exception as e:
            logger.error(f"Error leaving channel: {e}")
            await ctx.send(f"❌ Error leaving channel: {str(e)}")

    @commands.command(name='skip', help='Skips the current song')
    async def skip(self, ctx):
        if not ctx.voice_client:
            return await ctx.send('❌ Not playing anything!')
            
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send('⏭️ Skipped current song')
        else:
            await ctx.send('❌ Nothing is playing!')

    @commands.command(name='queue', help='Shows the current queue')
    async def queue(self, ctx):
        if not ctx.guild.id in self.bot.queue or not self.bot.queue[ctx.guild.id]:
            return await ctx.send('📝 Queue is empty!')

        try:
            queue_list = ['**Current Queue:**']
            if ctx.guild.id in self.bot.now_playing:
                queue_list.append(f'▶️ Now Playing: {self.bot.now_playing[ctx.guild.id]}')
            
            for i, song in enumerate(self.bot.queue[ctx.guild.id], 1):
                duration = song.get('duration', 0)
                duration_str = f" ({int(duration//60)}:{int(duration%60):02d})" if duration else ""
                queue_list.append(f'{i}. {song["title"]}{duration_str}')

            await ctx.send('\n'.join(queue_list))
        except Exception as e:
            logger.error(f"Error displaying queue: {e}")
            await ctx.send(f"❌ Error displaying queue: {str(e)}")

    @commands.command(name='pause', help='Pauses the current song')
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send('⏸️ Paused')
        else:
            await ctx.send('❌ Nothing is playing!')

    @commands.command(name='resume', help='Resumes the current song')
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send('▶️ Resumed')
        else:
            await ctx.send('❌ Nothing is paused!')

    @commands.command(name='stop', help='Stops playing and clears the queue')
    async def stop(self, ctx):
        if ctx.voice_client:
            self.bot.queue[ctx.guild.id] = []
            ctx.voice_client.stop()
            await ctx.send('⏹️ Stopped playing and cleared queue')
        else:
            await ctx.send('❌ Not playing anything!')

    @commands.command(name='clear', help='Clears the queue')
    async def clear(self, ctx):
        if ctx.guild.id in self.bot.queue:
            self.bot.queue[ctx.guild.id] = []
            await ctx.send('🧹 Queue cleared!')
        else:
            await ctx.send('📝 Queue is already empty!')

async def setup(bot):
    await bot.add_cog(Music(bot))