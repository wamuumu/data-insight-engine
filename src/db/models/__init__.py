"""
Database models for the application.
"""
from db.models.history import HistoryLog
from db.models.raw_data import RawData

__all__ = ["HistoryLog", "RawData"]
