import discord
from discord.ext import commands

BULK = False

# 824997091075555419
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            commands.when_mentioned,
            enable_debug_events=True,
        )
        self.load_extension("cogs.music")
        self.load_extension("jishaku")

    async def on_ready(self):
        print(f"logged as {self.user}, syncing... ")

        guild = discord.Object(824997091075555419)
        coded = self.tree.get_commands(guild=guild)
        fetched = await self.tree.fetch_commands(guild=guild)

        print(coded, fetched, sep='\n')

        if BULK or (len(coded) != len(fetched)):
            a = await self.tree.sync(guild=guild)
            print(f'synced {a}')
