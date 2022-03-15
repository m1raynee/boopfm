import os
from bot import Bot

Bot().run(token=os.environ.get('TOKEN'))
