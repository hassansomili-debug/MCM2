"""Core package for the Nudj MCM platform."""

from .api import API
from .database import init_db

__all__ = ["API", "init_db"]
