from abc import ABC, ABCMeta, abstractmethod

from discord.ext.commands.cog import CogMeta
from piccolo.engine.postgres import PostgresEngine
from redbot.core.bot import Red

from .db.utils import DBUtils


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""
    

class MixinMeta(ABC):
    def __init__(self, *_args):
        self.bot: Red
        self.db: PostgresEngine | None
        self.db_utils = DBUtils

    @abstractmethod
    async def initialize(self) -> None:
        raise NotImplementedError
    
    @abstractmethod
    def db_active(self) -> bool:
        raise NotImplementedError