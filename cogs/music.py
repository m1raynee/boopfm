from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional, Union

import wavelink
from wavelink.ext import spotify
import discord
from discord import app_commands
from discord.ext import commands

from .utils.funcs import send
from .utils.paginator import PaginatorView, BaseListSource

if TYPE_CHECKING:
    from ..bot import Bot

    class Track(wavelink.PartialTrack):
        requester: discord.Member

def humanize_seconds(s: int):
    hours, minutes = divmod(abs(s), 3600)
    minutes, seconds = divmod(minutes, 60)
    times = []
    for i, time in enumerate((hours, minutes, seconds)):
        if i == hours == 0:
            continue
        str_time = f'{time:02}'
        times.append(str_time)
    return f'{":".join(times)} {"left" if s <= 0 else ""}'


class QueueListSource(BaseListSource):
    def __init__(self, player: Player, *, per_page):
        super().__init__(player.queue._queue, per_page=per_page)

    async def format_page(self, view: PaginatorView, page: list[Track]):
        offset = self.per_page*view.current_page+1

        emb = self.base_embed(view, page)
        emb.title = '\N{MUSICAL NOTE} Текущая очередь'

        emb.add_field(
            name='Трек',
            value='\n'.join([f'{i}. {track}' for i, track in enumerate(page, offset)])
        )
        emb.add_field(name='Length', value='\n'.join([
            humanize_seconds(
                int((discord.utils.utcnow() - self.player.start).total_seconds()) - track.length//1000
            )
            if self.player.queue.next == offset+i else humanize_seconds(track.length//1000)
            for i, track in enumerate(page)
        ]))

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

    async def cog_load(self):
        await self.bot.wait_until_ready()

        await wavelink.NodePool.create_node(
            bot=self.bot,
            host='127.0.0.1',
            port=2333,
            password='youshallnotpass',
            spotify_client=spotify.SpotifyClient(
                client_id=os.environ.get('SPOTIFY_CLIENT_ID'),
                client_secret=os.environ.get('SPOTIFY_CLIENT_SECRET')
            )
        )

    @app_commands.command()
    @app_commands.describe(channel='Channel for connecting')
    async def connect(
        self,
        inter: discord.Interaction,
        channel: Optional[Union[discord.VoiceChannel, discord.StageChannel]] = None
    ) -> Player:
        """Connect to the voice channel"""
        channel = channel or inter.user.voice.channel
        if channel is None:
            raise Exception  # TODO

        vc = await channel.connect(cls=Player(inter))
        emb = discord.Embed(description=f'Подключён к {channel.mention}', color=BaseListSource.BASE_COLOR)
        await send(inter, embed=emb)

        return vc
    
    @app_commands.command()
    @app_commands.describe(query='Search query')
    async def play(
        self,
        inter: discord.Interaction,
        query: str
    ) -> None:
        """Play tracks with given query (Spotify supported)"""
        if not (vc := inter.guild.voice_client):
            vc: wavelink.Player = await self.connect.callback(self, inter)
        else:
            await inter.response.defer()

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
                description=f'Трек {track.title} [{inter.user.mention}] добавлен в очередь',
                color=BaseListSource.BASE_COLOR
            )
        else:
            emb = discord.Embed(
                description=f'{len(tracks)} треков [{inter.user.mention}] добавлено в очередь',
                color=BaseListSource.BASE_COLOR
            )
        await send(inter, embed=emb)
        
        if vc.queue.count and not vc.is_playing():
            await vc.play(await vc.queue.get_wait())
    
    @app_commands.command()
    async def queue(self, inter: discord.Interaction) -> None:
        ...
    
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

async def setup(bot: Bot):
    await bot.add_cog(MusicCog(bot), guilds=[discord.Object(824997091075555419)])