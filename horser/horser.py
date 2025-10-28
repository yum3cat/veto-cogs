from os import name
from typing import Literal, List

import discord
from discord.ext import tasks

from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.utils.menus import menu
from redbot.core.utils.chat_formatting import humanize_number

import asyncio
import aiofiles
import apsw
from tabulate import tabulate

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]

MAX_APP_EMOJIS = 2000

# Energy regen constants
TICK_SECONDS = 300  # 5 minutes
REGEN_PER_TICK = 1  # 1 energy per tick

class Horser(commands.Cog):
    """
    A horse-racing simulation game.
    """

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=314665745441095680,
            force_registration=True,
        )

        # Emoji setup
        emojis_config = {
            "emoji_horse_aqua": "NOT_SET",
            "emoji_horse_ash": "NOT_SET",
            "emoji_horse_black": "NOT_SET",
            "emoji_horse_blue": "NOT_SET",
            "emoji_horse_brown": "NOT_SET",
            "emoji_horse_chocolate": "NOT_SET",
            "emoji_horse_cream": "NOT_SET",
            "emoji_horse_diamond": "NOT_SET",
            "emoji_horse_green": "NOT_SET",
            "emoji_horse_grey": "NOT_SET",
            "emoji_horse_lime": "NOT_SET",
            "emoji_horse_orange": "NOT_SET",
            "emoji_horse_pink": "NOT_SET",
            "emoji_horse_purple": "NOT_SET",
            "emoji_horse_red": "NOT_SET",
            "emoji_horse_sky": "NOT_SET",
            "emoji_horse_soot": "NOT_SET",
            "emoji_horse_white": "NOT_SET",
            "emoji_horse_yellow": "NOT_SET",
            "emoji_horse_zombie": "NOT_SET",
        }

        self.config.register_global(**emojis_config)

        # SQLite DB setup
        self._connection = apsw.Connection(str(cog_data_path(self) / "horser.db"))
        self.cursor = self._connection.cursor()
        self.cursor.execute(
            'CREATE TABLE IF NOT EXISTS horses ('
            'guild_id INTEGER,'
            'user_id INTEGER,'
            'horse_id INTEGER PRIMARY KEY AUTOINCREMENT,'

            'horse_name TEXT,'
            'horse_color TEXT NOT NULL,'

            'speed INTEGER NOT NULL DEFAULT 1,'
            'power INTEGER NOT NULL DEFAULT 1,'
            'stamina INTEGER NOT NULL DEFAULT 1,'
            'guts INTEGER NOT NULL DEFAULT 1,'
            'wit INTEGER NOT NULL DEFAULT 1,'

            'energy INTEGER NOT NULL DEFAULT 10,'
            'max_energy INTEGER NOT NULL DEFAULT 10,'
            "last_energy_regen_ts INTEGER NOT NULL DEFAULT (strftime('%s','now')),"

            'races_run INTEGER NOT NULL DEFAULT 0,'
            'races_won INTEGER NOT NULL DEFAULT 0,'
            'cash_earned INTEGER NOT NULL DEFAULT 0'
            ');'
        )

        # energy regeneration loop
        self.energy_catchup.start()

    def ensure_cash_earned_column(self) -> None:
        # Ensure the cash_earned column exists
        columns = [row[1] for row in self.cursor.execute("PRAGMA table_info(horses);")]
        if "cash_earned" not in columns:
            self.cursor.execute("ALTER TABLE horses ADD COLUMN cash_earned INTEGER NOT NULL DEFAULT 0;")

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int) -> None:
        # TODO: Replace this with the proper end user data removal handling.
        super().red_delete_data_for_user(requester=requester, user_id=user_id)

    async def cog_load(self) -> None:
        # This method is called when the cog is loaded.

        # Load custom emojis into config, creating them if necessary
        all_emojis = await self.bot.fetch_application_emojis()
        # Horse emojis
        for emoji_name in ("horse_aqua", "horse_ash", "horse_black", "horse_blue", "horse_brown", "horse_chocolate", "horse_cream",
                           "horse_diamond", "horse_green", "horse_grey", "horse_lime", "horse_orange", "horse_pink", "horse_purple",
                           "horse_red", "horse_sky", "horse_soot", "horse_white", "horse_yellow", "horse_zombie"):
            emoji = next((emoji for emoji in all_emojis if emoji.name == emoji_name), None)
            if not emoji and len(all_emojis) < MAX_APP_EMOJIS:
                async with aiofiles.open(bundled_data_path(self) / f"{emoji_name}.png", "rb") as fp:
                    image = await fp.read()
                emoji = await self.bot.create_application_emoji(name=emoji_name, image=image)
            if emoji:
                await self.config.__getattr__("emoji_" + emoji_name).set(str(emoji))

        # Ensure tables updated
        self.ensure_cash_earned_column()

    async def cog_unload(self) -> None:
        # This method is called when the cog is unloaded.
        self.energy_catchup.cancel()
        self._connection.close()

    @commands.group()
    async def horser(self, ctx: commands.Context) -> None:
        """Horser main command. Use !horser menu to bring up the main menu."""

        # Update energy before any command
        self.update_energy()

    @horser.command()
    async def menu(self, ctx: commands.Context) -> None:
        """Show the main menu."""
        await ctx.send(embed=await self.get_main_menu_embed(ctx), view=self.MainMenu(self, ctx))

    async def get_main_menu_embed(self, ctx: commands.Context) -> discord.Embed:
        embed = discord.Embed()
        embed.color = discord.Color.dark_magenta()
        embed.title = "Horser"

        cur = self._connection.cursor()
        horse_count = list(cur.execute(
            "SELECT COUNT(*) FROM horses WHERE guild_id = ? AND user_id = ?;",
            (ctx.guild.id, ctx.author.id),
        ))[0][0]

        embed.add_field(name="", value=
        "Welcome to Horser! The horse racing simulation game.\n"
        "\n"
        f"{ctx.author.mention}, you have {horse_count} horses in your stable.\n")

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed
    
    class MainMenu(discord.ui.View):
        def __init__(self, horser, ctx: commands.Context) -> None:
            super().__init__(timeout=30)
            self.horser = horser
            self.ctx = ctx

        @discord.ui.button(label="Stable", style=discord.ButtonStyle.secondary)
        async def stable_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            user_horses = await self.horser.fetch_user_horses_async(self.ctx)
            await interaction.response.edit_message(embed=await self.horser.get_stable_menu_embed(self.ctx), view=self.horser.StableMenu(self.horser, self.ctx, user_horses))

        @discord.ui.button(label="Race!", style=discord.ButtonStyle.primary)
        async def race_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.edit_message(embed=await self.horser.get_race_menu_embed(self.ctx), view=self.horser.RaceMenu(self.horser, self.ctx))

        # add leaderboard
    
    @horser.command()
    async def stable(self, ctx: commands.Context) -> None:
        """View your stable."""
        user_horses = await self.fetch_user_horses_async(ctx)
        await ctx.send(embed=await self.get_stable_menu_embed(ctx), view=self.StableMenu(self, ctx, user_horses))

    async def get_stable_menu_embed(self, ctx: commands.Context) -> discord.Embed:
        embed = discord.Embed()
        embed.color = discord.Color.dark_gold()
        embed.title = "Stable"

        cur1 = self._connection.cursor()
        horse_count = list(cur1.execute(
            "SELECT COUNT(*) FROM horses WHERE guild_id = ? AND user_id = ?;",
            (ctx.guild.id, ctx.author.id),
        ))[0][0]

        embed.add_field(name="", value=
        f"You currently have {horse_count} horses in your stable.\n"
        "\n"
        "*To manage and improve your horse, type !horser manage [horse name] or use the select menu below.*\n"
        )
        
        horse_idx = 1
        cur2 = self._connection.cursor()
        for horse in cur2.execute(
            "SELECT horse_name, horse_color, energy, max_energy FROM horses WHERE guild_id = ? AND user_id = ?;",
            (ctx.guild.id, ctx.author.id),
        ):
            # add embed which shows the horse emoji with the corresponding color
            emoji = await self.config.__getattr__(f'emoji_horse_{horse[1]}')()
            embed.add_field(name=f"{horse_idx}. {horse[0]}", value=emoji, inline=False)
            embed.add_field(name="", value=f"Energy: {horse[2]}/{horse[3]}\n", inline=False)
            horse_idx += 1

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed

    async def fetch_user_horses_async(self, ctx) -> List[tuple]:
        # Fetch user's horses asynchronously in order to avoid database locks
        cur = self._connection.cursor()
        result = list(cur.execute("SELECT horse_name, horse_color FROM horses WHERE guild_id = ? AND user_id = ?;", (ctx.guild.id, ctx.author.id)))
        result = [(row[0], await self.config.__getattr__(f'emoji_horse_{row[1]}')()) for row in result]
        return result

    class StableMenu(discord.ui.View):
        def __init__(self, horser, ctx: commands.Context, user_horses: List[tuple[str, str]]) -> None:
            super().__init__(timeout=30)
            self.horser = horser
            self.ctx = ctx

            options = self._generate_horse_options_from_rows(user_horses)
            self.select = discord.ui.Select(
                placeholder="Manage a horse",
                options=options[:25],  # Discord limit
                min_values=1,
                max_values=1,
                custom_id="stable_manage_select"
            )

            # Disable the select if the only option is "none"
            if len(options) == 1 and options[0].value == "none":
                self.select.disabled = True

            async def on_select(interaction: discord.Interaction):
                await self.manage_horse_select(interaction, self.select.values[0])

            self.select.callback = on_select
            self.add_item(self.select)

        def _generate_horse_options_from_rows(self, rows: List[tuple]) -> List[discord.SelectOption]:
            options: List[discord.SelectOption] = []

            for horse_name, emoji in rows:
                options.append(
                    discord.SelectOption(
                        label=str(horse_name),
                        value=str(horse_name),
                        emoji=emoji
                    )
                )

            if not options:
                # Provide a disabled single option
                options = [discord.SelectOption(label="No horses available", value="none", description="Buy a horse first.")]

            return options

        async def manage_horse_select(self, interaction: discord.Interaction, selected_value: str):
            # Prevent other users hijacking
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("⛔ This menu isn't yours.", ephemeral=True)
                return

            if selected_value == "none":
                await interaction.response.send_message("You have no horses to manage. Please buy a horse first.", ephemeral=True)
                return

            embed = await self.horser.get_manage_horse_embed(self.ctx, selected_value)
            view = self.horser.ManageHorseMenu(self.horser, self.ctx)
            await interaction.response.edit_message(embed=embed, view=view)

        @discord.ui.button(label="Buy Horse", style=discord.ButtonStyle.primary)
        async def buy_horse_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("⛔ This button isn't yours.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=await self.horser.get_buy_horse_embed(self.ctx), view=self.horser.BuyHorseMenu(self.horser, self.ctx))

        @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("⛔ This button isn't yours.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=await self.horser.get_main_menu_embed(self.ctx), view=self.horser.MainMenu(self.horser, self.ctx))

    @horser.command()
    async def manage(self, ctx: commands.Context, *name) -> None:
        """Manage a horse."""
        if len(name) < 1:
            await ctx.send("Usage: !horser manage [horse name]")
            return

        name = " ".join(n.capitalize() for n in name)

        await ctx.send(embed=await self.get_manage_horse_embed(ctx, name), view=self.ManageHorseMenu(self, ctx))

    async def get_manage_horse_embed(self, ctx: commands.Context, name: str) -> discord.Embed:
        currency_name = await bank.get_currency_name(ctx.guild)

        embed = discord.Embed()
        embed.color = discord.Color.dark_gold()
        embed.title = "Manage Horse"

        # Check if horse exists
        cur = self._connection.cursor()
        horse = list(cur.execute(
            "SELECT horse_color, energy, max_energy, speed, power, stamina, guts, wit, races_run, races_won, cash_earned FROM horses "
            "WHERE guild_id = ? AND user_id = ? AND horse_name = ?;",
            (ctx.guild.id, ctx.author.id, name)
        ))
        if not horse:
            await ctx.send(f"You do not have a horse named '{name}' in your stable.")
            return

        horse_color, energy, max_energy, speed, power, stamina, guts, wit, races_run, races_won, cash_earned = horse[0]
        emoji = await self.config.__getattr__(f'emoji_horse_{horse_color}')()

        embed.add_field(name=
                        f"{emoji} {name}"
                        , value=
                        f"Color: **{horse_color.capitalize()}**\n"
                        f"Energy: **{energy}/{max_energy}**\n"
                        , inline=False)
        
        embed.add_field(name="", value=
                        f"Speed: **{speed}**‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ \n"
                        f"Power: **{power}**\n"
                        f"Stamina: **{stamina}**\n"
                        f"Guts: **{guts}**\n"
                        f"Wit: **{wit}**\n"
                        , inline=True)
        
        embed.add_field(name="", value=
                        f"Races run: **{races_run}**‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ ‎ \n"
                        f"Races won: **{races_won}**\n"
                        f"Win rate: **{(races_won / races_run * 100) if races_run > 0 else 0:.2f}%**\n"
                        f"\n"
                        f"Total cash earned: **{cash_earned}** {currency_name}\n"
                        , inline=True)
        
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed
    
    class ManageHorseMenu(discord.ui.View):
        def __init__(self, horser, ctx: commands.Context) -> None:
            super().__init__(timeout=30)
            self.horser = horser
            self.ctx = ctx

        @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            user_horses = await self.horser.fetch_user_horses_async(self.ctx)
            await interaction.response.edit_message(embed=await self.horser.get_stable_menu_embed(self.ctx), view=self.horser.StableMenu(self.horser, self.ctx, user_horses))


    @horser.command(name="buyHorse", aliases=["buyhorse"])
    async def buyhorse(self, ctx: commands.Context, color: str, *name) -> None:
        """Buy a horse."""
       
        if len(color) == 0 or len(name) == 0:
            await ctx.send("Usage: !horser buy_horse [color] [name]")
            return

        name = " ".join(arg.capitalize() for arg in name)

        # Check if color is valid
        valid_colors = [
            "aqua", "ash", "black", "blue", "brown", "chocolate", "cream",
            "diamond", "green", "grey", "lime", "orange", "pink", "purple",
            "red", "sky", "soot", "white", "yellow", "zombie"
        ]
        if color not in valid_colors:
            await ctx.send(f"Invalid color. Valid colors are: {', '.join(valid_colors)}")
            return

        # Check if user has enough balance
        currency_name = await bank.get_currency_name(ctx.guild)
        horse_cost = 25000
        user_balance = await bank.get_balance(ctx.author)
        if user_balance < horse_cost:
            await ctx.send(f"You do not have enough {currency_name} to buy a horse. You need {humanize_number(horse_cost)} {currency_name}.")
            return

        # Deduct cost and add horse to database
        cur = self._connection.cursor()
        cur.execute(
            "INSERT INTO horses (guild_id, user_id, horse_name, horse_color) VALUES (?, ?, ?, ?);",
            (ctx.guild.id, ctx.author.id, name, color)
        )
        await bank.withdraw_credits(ctx.author, horse_cost)
        await ctx.send(
            f"You have successfully bought a {color} horse named '{name}' for {humanize_number(horse_cost)} {currency_name}!\n"
            f"Your updated balance is {humanize_number(await bank.get_balance(ctx.author))} {currency_name}."
            )

    async def get_buy_horse_embed(self, ctx: commands.Context) -> discord.Embed:
        currency_name = await bank.get_currency_name(ctx.guild)

        embed = discord.Embed()
        embed.color = discord.Color.dark_green()
        embed.title = "Buy Horse"

        embed.add_field(name="", value= 
        f" Your current balance is {humanize_number(await bank.get_balance(ctx.author))} {currency_name}.\n"
        "\n"
        f"To buy a horse, type !horser buyHorse [color] [name]. A horse costs {25000} {currency_name}."
        "\n"
        "There are currently 20 colors available. Hover over each horse emoji below to see its color name."
        "\n"
        f"{await self.config.emoji_horse_aqua()} {await self.config.emoji_horse_ash()} {await self.config.emoji_horse_black()} {await self.config.emoji_horse_blue()}\n"
        f"{await self.config.emoji_horse_brown()} {await self.config.emoji_horse_chocolate()} {await self.config.emoji_horse_cream()} {await self.config.emoji_horse_diamond()}\n" 
        f"{await self.config.emoji_horse_green()} {await self.config.emoji_horse_grey()} {await self.config.emoji_horse_lime()} {await self.config.emoji_horse_orange()}\n"
        f"{await self.config.emoji_horse_pink()} {await self.config.emoji_horse_purple()} {await self.config.emoji_horse_red()} {await self.config.emoji_horse_sky()}\n"
        f"{await self.config.emoji_horse_soot()} {await self.config.emoji_horse_white()} {await self.config.emoji_horse_yellow()} {await self.config.emoji_horse_zombie()}\n")
        
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed

    class BuyHorseMenu(discord.ui.View):
        def __init__(self, horser, ctx: commands.Context) -> None:
            super().__init__(timeout=30)
            self.horser = horser
            self.ctx = ctx

        @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            user_horses = await self.horser.fetch_user_horses_async(self.ctx)
            await interaction.response.edit_message(embed=await self.horser.get_stable_menu_embed(self.ctx), view=self.horser.StableMenu(self.horser, self.ctx, user_horses))

    @horser.command()
    async def race(self, ctx: commands.Context) -> None:
        """Race your horses for glory!"""
        await ctx.send(embed=await self.get_race_menu_embed(ctx), view=self.RaceMenu(self, ctx))

    async def get_race_menu_embed(self, ctx: commands.Context) -> discord.Embed:
        currency_name = await bank.get_currency_name(ctx.guild)

        embed = discord.Embed()
        embed.color = discord.Color.green()
        embed.title = "Race!"

        embed.add_field(name="", value=
        f" Race your horses for cash!"
        "\n"
        "Race currently under construction.")

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed
    
    class RaceMenu(discord.ui.View):
        def __init__(self, horser, ctx: commands.Context) -> None:
            super().__init__(timeout=30)
            self.horser = horser
            self.ctx = ctx

        @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.edit_message(embed=await self.horser.get_main_menu_embed(self.ctx), view=self.horser.MainMenu(self.horser, self.ctx))    

    @horser.command()
    async def leaderboard(self, ctx: commands.Context) -> None:
        """View the horser leaderboard."""
        await ctx.send(embed=await self.get_leaderboard_embed(ctx), view=self.LeaderboardMenu(self, ctx),
                       allowed_mentions=discord.AllowedMentions.none())

    async def get_leaderboard_embed(self, ctx: commands.Context) -> discord.Embed:
        embed = discord.Embed()
        embed.color = discord.Color.blue()
        embed.title = "Leaderboard"

        cur = self._connection.cursor()
        query = cur.execute(
            """
            SELECT user_id, horse_name, horse_color, speed, power, stamina, guts, wit, cash_earned
            FROM horses
            ORDER BY cash_earned DESC
            LIMIT 10;
            """
        )
        
        leaderboard = ""

        idx = 1
        for user_id, horse_name, horse_color, speed, power, stamina, guts, wit, cash_earned in query:
            currency_name = await bank.get_currency_name(ctx.guild)
            emoji = await self.config.__getattr__(f'emoji_horse_{horse_color}')()
            leaderboard += f"**{idx}.** {emoji} **{horse_name}** . . . **{speed}** | **{power}** | **{stamina}** | **{guts}** | **{wit}** . . . {currency_name}**{humanize_number(cash_earned)}** won by ⮞<@{user_id}>⮜\n"
            idx += 1

        if len(leaderboard) == 0:
            leaderboard = "No horses found."

        embed.description = leaderboard

        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed

    class LeaderboardMenu(discord.ui.View):
        def __init__(self, horser, ctx: commands.Context) -> None:
            super().__init__(timeout=30)
            self.horser = horser
            self.ctx = ctx

        @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await interaction.response.edit_message(embed=await self.horser.get_main_menu_embed(self.ctx), view=self.horser.MainMenu(self.horser, self.ctx))

    ### Energy regeneration logic ###
    async def update_energy(self) -> None:
        cur = self._connection.cursor()
        cur.execute(
            """
            UPDATE horses
            SET
                energy = MIN(
                max_energy,
                energy + CAST((strftime('%s','now') - last_energy_regen_ts) / ? AS INTEGER) * ?
                ),
                last_energy_regen_ts = last_energy_regen_ts + (
                CAST((strftime('%s','now') - last_energy_regen_ts) / ? AS INTEGER) * ?
                )
            WHERE energy < max_energy;
            """,
            (TICK_SECONDS, REGEN_PER_TICK, TICK_SECONDS, TICK_SECONDS),
        )

    @tasks.loop(seconds=60)
    async def energy_catchup(self):
        # Downtime-proof: does nothing unless a full 5-min tick elapsed
        try:
            self.update_energy()
        except Exception as e:
            print(f"[energy_catchup] DB error: {e}")

    @energy_catchup.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()
    ### End energy regeneration logic ###