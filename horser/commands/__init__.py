from ..abc import CompositeMetaClass
from .database import DatabaseCommands
from .user import User


class Commands(DatabaseCommands, User, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
