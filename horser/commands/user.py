import math
import typing as t

import discord
from redbot.core import bank, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import GuildSettings, Player, Horse, Race, ensure_db_connection

import textwrap


class User(MixinMeta):
    @commands.group(name="horser", invoke_without_command=True)
    async def horser_group(self, ctx: commands.Context):
        """User commands"""
        await ctx.send_help()

    @horser_group.command(name="menu", description="Horser main menu.")
    @ensure_db_connection()
    async def horser_menu(self, ctx: commands.Context):
        """Horser main menu."""
        user = ctx.author

        player = await self.db_utils.get_create_player(user)
        horse_count = await Horse.count().where(
            (Horse.guild == ctx.guild.id) & (Horse.player == player.id) 
        )

        embed = discord.Embed(
            title="Horser",
            color=discord.Color.dark_magenta(),
            description=(textwrap.dedent(f"""
                    Welcome to **Horser**! The horse racing simulation game.
                    {user.mention}, you have {horse_count} horses in your stable.
                """)
            )
        )
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        # add buttons
        return await ctx.send(embed=embed)

    @horser_group.command(name="stable", aliases=["s"], description="View your Horser stable.")
    @ensure_db_connection()
    async def horser_stable(self, ctx: commands.Context, user = t.Optional[discord.User | discord.Member]):
        """View your or another player's Horser stable."""
        if not user:
            user = ctx.author
        user = ctx.author

        player = await self.db_utils.get_create_player(user)

        horse_count = await (
            Horse
            .count()
            .where((Horse.guild == ctx.guild.id) & (Horse.player == player.id))
        )

        embed = discord.Embed(
            title="Stable",
            color=discord.Color.dark_gold(),
            description=(textwrap.dedent(f"""
                    You currently have {horse_count} horses in your stable.

                    To manage and improve your horse, type {ctx.clean_prefix}horser horse [horse name] or use the select menu below.*
                """)
            )
        )

        player_horses = await (
            Horse
            .select(Horse.name, Horse.color, Horse.energy, Horse.max_energy)
            .where((Horse.guild == ctx.guild.id) & (Horse.player == player.id))
        )

        for idx, horse in enumerate(player_horses, start=1):
            # emoji = await self.config.__getattr__(f'emoji_horse_{horse[1]}')()
            emoji = "temp"
            embed.add_field(name=f'{idx}. {horse["name"]}', value=emoji, inline=False)
            embed.add_field(name="", value=f'Energy: {horse["energy"]}/{horse["max_energy"]}\n', inline=False)

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        # add buttons and select menu
        return await ctx.send(embed=embed)

    @horser_group.command(name="horse", aliases=["h"], description="Manage your horser.")
    @ensure_db_connection()
    async def horser_horse(self, ctx: commands.Context, horse_name: str):
        """View your or another player's horse. Manage your horse using this menu."""
        user = ctx.author

        player = await self.db_utils.get_create_player(user)

        horse = await (
            Horse
            .objects()
            .where((Horse.name == horse_name) & (Horse.player == player.id) & (Horse.guild == ctx.guild.id)).first()
        )

        if horse is None:
            return await ctx.send(f"You do not have a horse named '{horse_name}' in your stable.", ephemeral=True)

        currency_name = await bank.get_currency_name(ctx.guild)
        # emoji = await self.config.__getattr__(f'emoji_horse_{horse[1]}')()
        emoji = "temp"

        embed = discord.Embed(
            title=f'{user.display_name}\'s {horse["name"]}',
            color=discord.color.dark_gold()
        )

        embed.add_field(name=
                        f"{emoji}",
                        value=
                        f'Color: **{horse["color"].capitalize()}**\n'
                        f'Energy: **{horse["energy"]}/{horse["max_energy"]}**\n',
                        inline=False)
        
        embed.add_field(name="", value=
                        f'Speed: **{horse["speed"]}**‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ \n'
                        f'Power: **{horse["power"]}**\n'
                        f'Stamina: **{horse["stamina"]}**\n'
                        f'Guts: **{horse["guts"]}**\n'
                        f'Wit: **{horse["wit"]}**\n',
                        inline=True)
        
        embed.add_field(name="", value=
                        f'Races run: **{horse["races_run"]}**‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ \n'
                        f'Races won: **{horse["races_won"]}**\n'
                        f'Win rate: **{(horse["races_won"] / horse["races_run"] * 100) if horse["races_run"] > 0 else 0:.2f}%**\n'
                        f"\n"
                        f'Total cash earned: **{horse["cash_earned"]}** {currency_name}\n',
                        inline=True)

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        return await ctx.send(embed=embed)

    @horser_group.command(name="buyHorse", aliases=["buyhorse", "bh"], description="Buy a horser.")
    @ensure_db_connection
    async def horser_buy_horse(self, ctx: commands.Context, color: str, *name):
        """Buy a horser."""
        
        if len(color) == 0 or len(name) == 0:
            return await ctx.send("Usage: !horser buy_horse [color] [name]")
            
        name = " ".join(arg.capitalize() for arg in name)

        # Check if color is valid
        valid_colors = [
            "aqua", "ash", "black", "blue", "brown", "chocolate", "cream",
            "diamond", "green", "grey", "lime", "orange", "pink", "purple",
            "red", "sky", "soot", "white", "yellow", "zombie"
        ]

        if color not in valid_colors:
            return await ctx.send(f"Invalid color. Valid colors are: {', '.join(valid_colors)}")
            
        # Check if user has enough balance
        currency_name = await bank.get_currency_name(ctx.guild)
        horse_cost = 25000  # add to constants
        user_balance = await bank.get_balance(ctx.author)
        if user_balance < horse_cost:
            return await ctx.send(f"You do not have enough {currency_name} to buy a horse. You need {humanize_number(horse_cost)} {currency_name}.")
        
        await Horse.insert(
            Horse(guild=ctx.guild.id, player=ctx.author.id, color=color, name=name)
        )
            
        await bank.withdraw_credits(ctx.author, horse_cost)

        return await ctx.send(
            f"You have successfully bought a {color} horse named '{name}' for {humanize_number(horse_cost)} {currency_name}!\n"
            f"Your updated balance is {humanize_number(await bank.get_balance(ctx.author))} {currency_name}."
        )

    @horser_group.command(name="race", aliases=["r"], description="Race your horsers.")
    @ensure_db_connection()
    async def horser_race(self, ctx: commands.Context):
        """Race your horsers."""
        user = ctx.author
        
        embed = discord.Embed(
            title="Race",
            color=discord.Color.green(),
            description=(textwrap.dedent(f"""
                    Race under construction.
                """)
            )
        )

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        # add buttons and select menu
        return await ctx.send(embed=embed)

    @horser_group.command(name="leaderboard", aliases=["l"], description="Horser leaderboard.")
    @ensure_db_connection()
    async def horser_leaderboard(self, ctx: commands.Context):
        """Horser leaderboard."""

        top_horses = await (
            Horse
            .select(
                Horse.player,
                Horse.name,
                Horse.color,
                Horse.speed,
                Horse.power,
                Horse.stamina,
                Horse.guts,
                Horse.wit,
                Horse.cash_earned,
            )
            .order_by(Horse.cash_earned, ascending=False)
            .limit(10)  # add to constant?
        )

        currency_name = await bank.get_currency_name(ctx.guild)
        leaderboard = ""
        # emoji = await self.config.__getattr__(f'emoji_horse_{horse_color}')()
        emoji = "temp"
        for rank, horse in enumerate(top_horses, start=1):
            leaderboard += f'**{rank}.** {emoji} **{horse["name"]}** . . . **{horse["speed"]}** | **{horse["power"]}** | **{horse["stamina"]}** | **{horse["guts"]}** | **{horse["wit"]}** . . . {currency_name}**{humanize_number(horse["cash_earned"])}** won by ⮞<@{horse["player"].id}>⮜\n'

        if len(leaderboard) == 0:
            leaderboard = "No horses found."

        embed = discord.Embed(
            title="Leaderboard",
            color=discord.Color.blue(),
            description=leaderboard
        )

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        return await ctx.send(embed=embed)
