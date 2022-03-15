from __future__ import annotations
import datetime
import re
import asyncio

from disnake.ext import commands, menus
import disnake
from typing import TYPE_CHECKING
import wavelink

from .utils.paginator import PaginatorView

if TYPE_CHECKING:
    from main import Bot

URL_REGEX = re.compile('https?:\/\/(?:www\.)?.+')

class TrackQueue(asyncio.Queue):
    def _init(self, *_) -> None:
        self._queue: list[Track] = []
        self.next = 0
    
    def _put(self, item: Track) -> None:
        self._queue.append(item)
    
    def _get(self) -> Track:
        value = self._queue[self.next]
        self.next += 1
        return value

    def empty(self) -> bool:
        return self.next >= len(self._queue)

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

class TrackSource(menus.ListPageSource):
    def __init__(self, controller: PlayerController):
        super().__init__(controller.queue._queue, per_page=10)
        self.controller = controller

    async def format_page(self, menu: PaginatorView, page: list[Track]):
        offset = self.per_page*menu.current_page+1
        embed = disnake.Embed(title='\N{MUSICAL NOTE} Current queue', color=0x0084c7)
        embed.add_field(name='Tracks', value='\n'.join([
            f"{i}. {track}" for i, track in enumerate(page, start=offset)
        ]))
        embed.add_field(name='Length', value='\n'.join([
            humanize_seconds(int((disnake.utils.utcnow() - self.controller.start).total_seconds()) - track.length//1000)
            if self.controller.queue.next == offset+i else humanize_seconds(track.length//1000)
            for i, track in enumerate(page)
        ]))
        return embed

class Track(wavelink.Track):
    requester: disnake.Member

class PlayerController:
    def __init__(self, bot: Bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.channel: disnake.abc.Messageable = None
        self.start: datetime.datetime = None

        self.next = asyncio.Event()
        self.queue = TrackQueue()

        self.volume = 40
        self.now_playing = None

        bot.loop.create_task(self.controle_loop())
    
    async def controle_loop(self):
        await self.bot.wait_until_ready()

        player = self.bot.wavelink.get_player(self.guild_id)
        await player.set_volume(self.volume)

        while True:
            if self.now_playing:
                await self.now_playing.delete()
            
            self.next.clear()

            track: Track = await self.queue.get()
            await player.play(track)
            self.start = disnake.utils.utcnow()
            self.now_playing = await self.channel.send(
                embed=disnake.Embed(title='\N{MUSICAL NOTE} Now Playing', description=f'{track} [{track.requester.mention}]')
            )

            await self.next.wait()

class Music(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.controllers: dict[int, PlayerController] = {}

    async def cog_load(self):
        await self.bot.wait_until_ready()

        # Initiate our nodes. For this example we will use one server.
        # Region should be a disnake guild.region e.g sydney or us_central (Though this is not technically required)
        self.node = await self.bot.wavelink.initiate_node(
            host='127.0.0.1',
            port=2333,
            rest_uri='http://127.0.0.1:2333',
            password='youshallnotpass',
            identifier='TEST',
            region='us_central'
        )
        self.node.set_hook(self.on_hook)
    
    async def on_hook(self, event):
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            controller = self.get_controller(event.player)
            controller.next.set()
    
    def get_controller(self, object: disnake.ApplicationCommandInteraction | wavelink.Player):
        if isinstance(object, disnake.ApplicationCommandInteraction):
            guild_id = object.guild.id
        else:
            guild_id = object.guild_id

        try:
            controller = self.controllers[guild_id]
        except KeyError:
            controller = PlayerController(self.bot, guild_id)
            self.controllers[guild_id] = controller

        return controller

    @commands.slash_command()
    async def connect(
        self,
        inter: disnake.ApplicationCommandInteraction,
        channel: disnake.VoiceChannel = commands.Param(lambda i: i.author.voice.channel if i.author.voice is not None else None)
    ):
        """
        Сonnects the bot to the channel

        Parameters
        ----------
        channel: Channel to connect the bot to
        """
        if channel is None:
            return await inter.send('connect to channel pls or pass any')
        
        player = self.bot.wavelink.get_player(inter.guild.id)
        await inter.send(f'Connecting to **`{channel.name}`**')
        await player.connect(channel.id)

        controller = self.get_controller(inter)
        controller.channel = inter.channel

    @commands.slash_command()
    async def play(
        self,
        inter: disnake.ApplicationCommandInteraction,
        query: str
    ):
        if not URL_REGEX.match(query):
            query = f'ytsearch:{query}'
        tracks = await self.bot.wavelink.get_tracks(query)

        if not tracks:
            return await inter.response.send_message('Could not find any songs with that query.', ephemeral=True)

        player = self.bot.wavelink.get_player(inter.guild.id)
        if not player.is_connected:
            await self.connect(inter, inter.author.voice.channel if inter.author.voice is not None else None)

        controller = self.get_controller(inter)
        if isinstance(tracks, wavelink.TrackPlaylist):
            for track in tracks.tracks:
                track.requester = inter.author
                controller.queue.put_nowait(track)
            return await inter.send(f'Added {len(tracks.tracks)} tracks to the queue.')
        track = tracks[0]
        controller.queue.put_nowait(track)
        await inter.send(f'Added {str(track)} to the queue.')
    
    @commands.slash_command()
    async def disconnect(self, inter):
        player = self.bot.wavelink.get_player(inter.guild.id)
        if player.is_connected:
            await player.destroy()
            await inter.send('Player was destroyed')
        else:
            await inter.send('there is nothing to destroy', ephemeral=True)
    
    @commands.slash_command()
    async def pause(self, inter):
        player = self.bot.wavelink.get_player(inter.guild.id)
        if not player.is_connected:
            return await inter.send('there is nothing to pause', ephemeral=True)
        await player.set_pause(not player.is_paused)
        if player.is_paused:
            await inter.send('The player is paused')
        else:
            await inter.send('The player is resumed')
    
    @commands.slash_command()
    async def skip(self, inter):
        player = self.bot.wavelink.get_player(inter.guild.id)
        if not player.is_connected:
            return await inter.send('there is nothing to skip', ephemeral=True)
        
        await inter.send('Skipped')
        await player.stop()

    def cog_unload(self) -> None:
        self.bot.loop.create_task(self.node.destroy(force=True))

    @commands.slash_command()
    async def queue(self, inter):
        player = self.bot.wavelink.get_player(inter.guild.id)
        if not player.is_connected:
            return await inter.send('there is nothing to show', ephemeral=True)

        controller = self.get_controller(inter)
        view = PaginatorView(TrackSource(controller), interaction=inter)
        view.current_page = controller.queue.next // 10
        await view.start()

def setup(bot):
    bot.add_cog(Music(bot))
