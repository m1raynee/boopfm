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

