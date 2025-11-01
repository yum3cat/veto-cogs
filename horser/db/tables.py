import logging

from discord.ext.commands.core import check
from piccolo.columns import (
    Array,
    BigInt,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Serial,
    SmallInt,
    Text,
    Timestamptz,
)
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.table import Table, sort_table_classes
from redbot.core import commands

log = logging.getLogger("veto.cog.horser.db.tables")


def ensure_db_connection():
    """Check if cog.db has a value."""
    async def predicate(ctx: commands.Context) -> bool:
        if not getattr(ctx.cog, "db", None):
            raise commands.UserFeedbackCheckFailure("Database connection is not active, try again later")
        return True

    return check(predicate)


class TableMixin:
    created_on = Timestamptz()
    # updated_on = Timestamptz(auto_update=TimestamptzNow().python)


class GuildSettings(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord Guild ID


class GlobalSettings(TableMixin, Table):
    id = Serial(primary_key=True)
    key = SmallInt(unique=True, default=1)  # Always 1


class Player(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord User ID

    stable = Text(required=True, default="basic")  # Tool tier


class Horse(TableMixin, Table):
    id = Serial(primary_key=True)
    player = ForeignKey(required=True, references=Player)
    guild = BigInt()    # Discord Guild ID

    name = Text(unique=True)
    color = Text()

    speed = Integer(default=4)
    power = Integer(default=4)
    stamina = Integer(default=4)
    guts = Integer(default=4)
    wit = Integer(default=4)

    increased_speed = Integer(default=0)
    increased_power = Integer(default=0)
    increased_stamina = Integer(default=0)
    increased_guts = Integer(default=0)
    increased_wit = Integer(default=0)

    energy = Integer(default=10)
    max_energy = Integer(default=10)

    increased_max_energy = Integer(default=0)
    
    last_energy_regen = Timestamptz(null=True)

    races_run = Integer(default=0)
    races_won = Integer(default=0)
    cash_earned = BigInt(default=0)


class Race(TableMixin, Table):
    id = Serial(primary_key=True)

    name = Text()
    distance = Integer()

    difficulty = Text()
    

TABLES: list[Table] = sort_table_classes([Player, Horse, Race, GuildSettings, GlobalSettings])
