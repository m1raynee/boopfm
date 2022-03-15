from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

import wavelink
from wavelink.ext import spotify
import discord
from discord import app_commands
from discord.ext import commands

from .utils.funcs import send

if TYPE_CHECKING:
    from ..bot import Bot

    class Track(wavelink.PartialTrack):
        requester: discord.Member

class Player(wavelink.Player):
    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        self.dj = interaction.user
        self.state_channel = interaction.channel
        self.now_playing_message: discord.Message = None


async def get_spotify_tracks(decoded: dict):
    if decoded['type'] == spotify.SpotifySearchType.track:
        return [await spotify.SpotifyTrack.search(decoded['id'], return_first=True)]
        # return [wavelink.PartialTrack(query=decoded['id'], cls=spotify.SpotifyTrack)]
    else:
        tracks = []
        async for track in spotify.SpotifyTrack.iterator(query=decoded['id'], type=decoded['type'], partial_tracks=True):
            tracks.append(track)
        return tracks



class MusicCog(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

        self.bot.loop.create_task(self.start_node())

    async def start_node(self):
        await self.bot.wait_until_ready()

        await wavelink.NodePool.create_node(
            bot=self.bot,
            host='127.0.0.1',
            port=2333,
            password='youshallnotpass',
            spotify_client=spotify.SpotifyClient(
                client_id='47f9a00b99fe4d868eb063ec9bad3054',
                client_secret='d2608f9ca5c247a38313658b9edc62fb'
            )
        )

    @app_commands.command()
    @app_commands.describe(channel='Channel for connecting')
    async def connect(
        self,
        inter: discord.Interaction,
        channel: Optional[Union[discord.VoiceChannel, discord.StageChannel]] = None
    ):
        """Connect to the voice channel"""
        channel = channel or inter.user.voice.channel
        if channel is None:
            raise Exception  # TODO

        vc = await channel.connect(cls=Player(inter))
        emb = discord.Embed(description=f'Подключён к {channel.mention}', color=0x00E09D)
        await send(inter, embed=emb)

        return vc
    
    @app_commands.command()
    @app_commands.describe(query='Search query')
    async def play(
        self,
        inter: discord.Interaction,
        query: str
    ):
        """Play tracks with given query (Spotify supported)"""
        if not (vc := inter.guild.voice_client):
            vc: wavelink.Player = await self.connect.callback(self, inter)

        if decoded := spotify.decode_url(query):
            tracks: list[Track] = await get_spotify_tracks(decoded)  # type: ignore
        else:
            tracks: list[Track] = [await wavelink.YouTubeTrack.search(query=query, return_first=True)]  # type: ignore

        if not tracks:
            raise Exception  # TODO
        
        for track in tracks:
            track.requester = inter.user
            vc.queue.put(track)
        if len(tracks) == 1:
            track = tracks[0]
            emb = discord.Embed(
                description=f'Трек {track.title} [{track.requester.mention}] добавлен в очередь',
                color=0x00E09D
            )
        else:
            emb = discord.Embed(
                description=f'{len(tracks)} треков добавлено в очередь',
                color=0x00E09D
            )
        await send(inter, embed=emb)
        
        if vc.queue.count and not vc.is_playing():
            await vc.play(await vc.queue.get_wait())
    
    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: Player, track: wavelink.YouTubeTrack):
        activity = discord.Activity(name=track.title, type=discord.ActivityType.listening)
        await self.bot.change_presence(activity=activity)
        emb = discord.Embed(
            title='\N{MUSICAL NOTE} Сейчас играет',
            description=f'[{track.title}]({track.uri})'  # [{track.requester.mention}]
        )
        player.now_playing_message = await player.state_channel.send(embed=emb)
    
    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: Player, track: wavelink.YouTubeTrack, reason):
        if player.now_playing_message:
            await player.now_playing_message.delete()
        
        if player.queue.count and not player.is_playing():
            new_track = await player.queue.get_wait()
            await player.play(new_track)
        else:
            await self.bot.change_presence(activity=None)

def setup(bot: Bot):
    bot.add_cog(MusicCog(bot), guilds=[discord.Object(824997091075555419)])