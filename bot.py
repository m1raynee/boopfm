from discord.ext import commands
import jishaku

BULK = False

# 824997091075555419
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            commands.when_mentioned,
            enable_debug_events=True,
        )

    async def setup_hook(self) -> None:
        print('loading cogs')
        await self.load_extension("cogs.music")
        await self.add_cog(jishaku.Jishaku(bot=self))
        print('end')
    
    async def on_ready(self):
        print(f'ready {self.user}')
