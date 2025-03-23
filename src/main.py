"""
The entrypoint of MediaForge, containing the majority of the discord API interactions.
"""
import asyncio
import os
import sqlite3
import sys
import traceback

sys.path.insert(0, os.getcwd())
from utils import tempfiles

try:
    import aiofiles
    import aiohttp
    from aiohttp import client_exceptions as aiohttp_client_exceptions
    import aiosqlite
    import docstring_parser
    import emojis
    import humanize
    import discord
    import psutil
    import regex as re
    import requests
    import yt_dlp as youtube_dl
    import glob
    from discord.ext import commands, tasks
    from tblib import pickling_support

    pickling_support.install()
except ModuleNotFoundError as e:
    print("".join(traceback.format_exception(type(e), e, tb=e.__traceback__)), file=sys.stderr)
    sys.exit("MediaForge was unable to import the required libraries and files. Did you follow the self-hosting guide "
             "on the GitHub? https://github.com/machineonamission/mediaforge#to-self-host")

import core.database
from core import heartbeat
from utils.common import *
from core.clogs import logger
import config

from cog.botevents import BotEventsCog
from cog.botlist import DiscordListsPost
from cog.commandchecks import CommandChecksCog
from cog.errorhandler import ErrorHandlerCog
from cog.status import StatusCog

from commands.caption import Caption
from commands.conversion import Conversion
from commands.debug import Debug
from commands.image import Image
from commands.media import Media
from commands.other import Other

docker = os.environ.get('AM_I_IN_A_DOCKER_CONTAINER', False)
if not hasattr(config, "bot_token") or config.bot_token == "EXAMPLE_TOKEN":
    sys.exit("The bot token could not be found or hasn't been properly set. Be sure to follow the self-hosting "
             "guide on GitHub. https://github.com/machineonamission/mediaforge#to-self-host")

discord.Message.orig_reply = discord.Message.reply

async def safe_reply(self: discord.Message, *args, **kwargs) -> discord.Message:
    try:
        await self.channel.fetch_message(self.id)
        return await self.orig_reply(*args, **kwargs)
    except (discord.errors.NotFound, discord.errors.HTTPException) as e:
        logger.debug(f"abandoning reply to {self.id} due to {get_full_class_name(e)}, "
                     f"sending message in {self.channel.id}.")
        author = self.author.mention
        if len(args):
            content = author + (args[0] or "")[:2000 - len(author)]
        else:
            content = author
        return await self.channel.send(content, **kwargs, allowed_mentions=discord.AllowedMentions(
            everyone=False, users=True, roles=False, replied_user=True))

discord.Message.reply = safe_reply

async def downloadttsvoices():
    if sys.platform != 'win32':
        ttspath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts")
        femalevoice = os.path.join(ttspath, "mycroft_voice_4.0.flitevox")
        malevoice = os.path.join(ttspath, "cmu_us_slt.flitevox")
        if not os.path.isfile(malevoice):
            logger.log(25, "Downloading male TTS voice...")
            await download_async("https://github.com/MycroftAI/mimic1/raw/development/voices/mycroft_voice_4.0.flitevox",
                          malevoice)
            logger.log(35, "Male TTS voice downloaded!")
        if not os.path.isfile(femalevoice):
            logger.log(25, "Downloading female TTS voice...")
            await download_async("https://github.com/MycroftAI/mimic1/raw/development/voices/cmu_us_slt.flitevox",
                          femalevoice)
            logger.log(35, "Female TTS voice downloaded!")
        mimicpath = os.path.join(ttspath, "mimic")
        os.chmod(mimicpath, os.stat(mimicpath).st_mode | 0o111)

def initdbsync():
    syncdb = sqlite3.connect(config.db_filename)
    with syncdb:
        cur = syncdb.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guild_prefixes'")
        if not cur.fetchall():
            syncdb.execute(
                "create table guild_prefixes ( guild int not null constraint table_name_pk primary key, "
                "prefix text not null ); "
            )
        cur = syncdb.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bans'")
        if not cur.fetchall():
            syncdb.execute("create table bans ( user int not null constraint bans_pk primary key, banreason text );  ")
    syncdb.close()

async def init():
    initdbsync()
    await downloadttsvoices()
    heartbeat.init()
    tempfiles.init()

class MyBot(commands.AutoShardedBot):
    async def setup_hook(self):
        logger.debug(f"initializing cogs")
        await core.database.init_database()
        if config.bot_list_data:
            logger.info("bot list data found. botblock will start when bot is ready.")
            await bot.add_cog(DiscordListsPost(bot))
        else:
            logger.debug("no bot list data found")
        await asyncio.gather(
            bot.add_cog(Caption(bot)),
            bot.add_cog(Media(bot)),
            bot.add_cog(Conversion(bot)),
            bot.add_cog(Image(bot)),
            bot.add_cog(Other(bot)),
            bot.add_cog(Debug(bot)),
            bot.add_cog(StatusCog(bot)),
            bot.add_cog(ErrorHandlerCog(bot)),
            bot.add_cog(CommandChecksCog(bot)),
            bot.add_cog(BotEventsCog(bot)),
        )

if __name__ == "__main__":
    logger.log(25, "Hello World!")
    logger.info(f"discord.py {discord.__version__}")
    asyncio.run(init())
    if hasattr(config, "shard_count") and config.shard_count is not None:
        shard_count = config.shard_count
    else:
        shard_count = None
    intents = discord.Intents.all()
    intents.presences = False
    intents.members = False
    bot = MyBot(command_prefix=prefix_function,
                help_command=None,
                case_insensitive=True,
                shard_count=shard_count,
                guild_ready_timeout=30,
                allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=True),
                intents=intents)

    logger.debug("running bot")
    bot.run(config.bot_token, log_handler=None)
    asyncio.run(core.database.close_database())
