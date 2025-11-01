import typing as t

import discord

from .tables import GlobalSettings, GuildSettings, Player, Horse, Race


class DBUtils:
    @staticmethod
    async def get_create_global_settings() -> GlobalSettings:
        """Get or create GlobalSettings row."""
        settings: GlobalSettings = await GlobalSettings.objects().get_or_create(
            (GlobalSettings.key == 1), defaults={GlobalSettings.key: 1}
        )
        return settings

    @staticmethod
    async def get_create_guild_settings(guild: discord.Guild | int) -> GuildSettings:
        """Get or create guild settings row."""
        gid = guild if isinstance(guild, int) else guild.id
        settings = await GuildSettings.objects().get_or_create(
            (GuildSettings.id == gid), defaults={GuildSettings.id: gid}
        )
        return settings

    @staticmethod
    async def get_create_player(user: discord.User | discord.Member | int) -> Player:
        """Get or create Player row."""
        uid = user if isinstance(user, int) else user.id
        player = await Player.objects().get_or_create((Player.id == uid), defaults={Player.id: uid})
        return player
    
    @staticmethod
    async def get_create_horse(id: int, player: Player, guild: discord.Guild | int) -> Horse:
        """Get or create Horse row."""
        gid = guild if isinstance(guild, int) else guild.id
        horse = await Horse.objects().get_or_create((Horse.id == id), (Horse.player == Player), (Horse.guild == gid),
                                                    defaults={Horse.player: player, Horse.guild: gid})
        return horse
    
    @staticmethod
    async def get_create_race(id: int) -> Race:
        """Get or create Race row."""
        race = await Race.objects().get_or_create((Race.id == id))
        return race
    