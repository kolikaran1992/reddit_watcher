import json
from pathlib import Path

from reddit_watcher.omniconf import config
from reddit_watcher.database.models import *
from reddit_watcher.database.config import Base

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column
from typing import Dict, List


def extract_model_column_map(Base):
    model_map = {}

    for mapper in Base.registry.mappers:
        cls = mapper.class_

        if not hasattr(cls, "__table__"):
            continue

        table = cls.__table__
        cols = []

        for col in table.columns:
            # Safe unique detection
            unique = col.unique or any(
                getattr(c, "unique", False)
                for c in table.constraints
                if hasattr(c, "columns") and col.name in c.columns.keys()  # <-- FIXED
            )

            cols.append(
                {
                    "name": col.name,
                    "type": col.type.__class__.__name__,
                    "primary_key": col.primary_key,
                    "nullable": col.nullable,
                    "unique": unique,
                    "default": (
                        str(col.default.arg) if col.default is not None else None
                    ),
                    "foreign_keys": [
                        str(fk.target_fullname) for fk in col.foreign_keys
                    ],
                }
            )

        model_map[cls.__name__] = cols

    return model_map
