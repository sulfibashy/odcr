"""Platform adapters. Register new platforms in ADAPTERS."""

from __future__ import annotations

from typing import Any

from .base import Adapter, type_matches
from .mysql import MySQLAdapter
from .postgres import PostgresAdapter
from .sqlserver import SQLServerAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    "postgres": PostgresAdapter,
    "postgresql": PostgresAdapter,
    "mysql": MySQLAdapter,
    "mariadb": MySQLAdapter,
    "sqlserver": SQLServerAdapter,
    "mssql": SQLServerAdapter,
    "azuresql": SQLServerAdapter,
}


def get_adapter(options: dict[str, Any]) -> Adapter:
    opts = dict(options)
    kind = str(opts.pop("type", "")).lower()
    if kind not in ADAPTERS:
        raise ValueError(f"Unsupported connection type '{kind}'. Supported: {', '.join(sorted(set(ADAPTERS)))}")
    return ADAPTERS[kind](**opts)


__all__ = ["Adapter", "ADAPTERS", "get_adapter", "type_matches",
           "PostgresAdapter", "MySQLAdapter", "SQLServerAdapter"]
