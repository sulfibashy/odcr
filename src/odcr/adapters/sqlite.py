"""SQLite adapter (Python standard library). SQLite has no schemas, so meta tables are prefixed:
odcr_meta_validation_runs, odcr_meta_check_results, ..."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from .base import Adapter


class SQLiteAdapter(Adapter):
    dialect = "sqlite"
    driver = "sqlite3"
    paramstyle = "qmark"
    meta_in_current_schema = True

    def _connect(self) -> Any:
        import sqlite3

        return sqlite3.connect(str(self.options.get("path") or self.options.get("database") or ":memory:"),
                               isolation_level=None)

    def to_db(self, value: Any) -> Any:
        if isinstance(value, (dt.datetime, dt.date)):
            return value.isoformat(sep=" ") if isinstance(value, dt.datetime) else value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    def current_schema(self) -> str | None:
        return "main"

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        table = name.split(".")[-1]
        return {str(r[1]).lower(): str(r[2]).lower() for r in self.fetchall(f"PRAGMA table_info({self.quote(table)})")}

    def meta_types(self) -> dict[str, str]:
        return {"id": "TEXT", "name": "TEXT", "short": "TEXT", "text": "TEXT", "ts": "TIMESTAMP",
                "int": "INTEGER", "num": "REAL"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INTEGER", "string": "TEXT", "decimal": "NUMERIC(12,2)", "date": "DATE"}
