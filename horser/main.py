import asyncio
import json
import logging
import textwrap
import typing as t
from collections import defaultdict
from io import BytesIO

from piccolo.engine.postgres import PostgresEngine
from redbot.core import commands
from redbot.core.bot import Red

from .commands import Commands
from .db.tables import TABLES, Player
from .db.utils import DBUtils
from .engine import engine
from .tasks import TaskLoops

log = logging.getLogger("veto.cog.horser")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Horser(Commands, TaskLoops, commands.Cog):
    """A horse-racing simulation game."""

    __author__ = "ak4.7"
    __version__ = "0.0.1"

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot: Red = bot
        self.db: PostgresEngine | None = None
        self.db_utils = DBUtils()

        self.active_guild_races: dict[int, int] = defaultdict(int)
        self.active_channel_races: set[int] = set()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, user_id: int) -> t.MutableMapping[str, BytesIO]:
        users = await Player.select(Player.all_columns()).where(Player.id == user_id)
        return {"data.json": BytesIO(json.dumps(users).encode())}

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        if not self.db:
            return "Data not deleted, database connection is not active"
        await Player.delete().where(Player.id == user_id)
        return f"Data for user ID {user_id} has been deleted"

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        if self.db:
            self.db.pool.terminate()
            log.info("Database connection terminated (Cog unloaded)")

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            log.warning("Postgres credentials not set!")
            return
        if self.db_active():
            log.info("Closing existing database connection")
            await self.db.close_connection_pool()
        log.info("Registering database connection")
        try:
            self.db = await engine.register_cog(self, TABLES, config, trace=True)
        except Exception as e:
            log.error("Failed to connect to database", exc_info=e)
            self.db = None
            return
        log.info("Cog initialized")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: dict):
        if service_name != "postgres":
            return
        await self.initialize()

    # ---------------------------- GLOBAL METHODS ----------------------------
    def db_active(self) -> bool:
        if not self.db:
            return False
        if hasattr(self.db.pool, "is_closing"):
            return not self.db.pool.is_closing()  # 1.27.1
        if self.db.pool._closed:
            return False
        return self.db is not None
