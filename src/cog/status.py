import datetime

import discord
from discord.ext import commands, tasks

import config


class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.changestatus.start()

    def cog_unload(self):
        self.changestatus.cancel()

    @tasks.loop(seconds=60)
    async def changestatus(self):
        if datetime.datetime.now().month == 6:  # june (pride month)
            status_text = f"LGBTQ+ pride in {len(self.bot.guilds)} server{'' if len(self.bot.guilds) == 1 else 's'}! | {config.default_command_prefix}help"
            game = discord.Activity(
                name=status_text,
                type=discord.ActivityType.watching)
        else:
            status_text = f"with your media in {len(self.bot.guilds)} server{'' if len(self.bot.guilds) == 1 else 's'} | {config.default_command_prefix}help"
            game = discord.Activity(
                name=status_text,
                type=discord.ActivityType.playing)
        await self.bot.change_presence(activity=game)

    @changestatus.before_loop
    async def before_printer(self):
        await self.bot.wait_until_ready()
