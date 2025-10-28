from typing import Literal

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.menus import menu

import aiofiles

async def main_menu(s, ctx: commands.Context) -> discord.Embed:
    return discord.Embed(description=
f"""Welcome to Horser! The horse racing simulation game.
{ctx.author.mention}, you have 0 horses in your [Basic] stable.
{await s.config.emoji_horse_aqua()} represents the aqua horse!"""
    )