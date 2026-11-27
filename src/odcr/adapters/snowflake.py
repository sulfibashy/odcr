"""Snowflake adapter (snowflake-connector-python). Supports password, key-pair, OAuth and SSO
(`authenticator: externalbrowser`). Unquoted names follow Snowflake's upper-case rules."""

from __future__ import annotations

from typing import Any

from .base import Adapter

_CONNECT_KEYS = ("account", "user", "password", "authenticator", "token", "private_key_file",
                 "private_key_file_pwd", "warehouse", "database", "schema", "role", "host", "region", "login_timeout")


class SnowflakeAdapter(Adapter):
    dialect = "snowflake"
    driver = "snowflake.connector"
    quote_policy = "needed"
    default_schema_sql = "SELECT CURRENT_SCHEMA()"

    def _connect(self) -> Any:
        try:
            import snowflake.connector
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Snowflake support needs: pip install odcr-snowflake") from exc
        o = {k: v for k, v in self.options.items() if k in _CONNECT_KEYS and v not in (None, "")}
        if "username" in self.options and "user" not in o:
            o["user"] = self.options["username"]
        return snowflake.connector.connect(autocommit=True, **o)

    def meta_types(self) -> dict[str, str]:
        return {"id": "VARCHAR(64)", "name": "VARCHAR(255)", "short": "VARCHAR(32)", "text": "VARCHAR",
                "ts": "TIMESTAMP_NTZ", "int": "NUMBER(38,0)", "num": "FLOAT"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INTEGER", "string": "VARCHAR(50)", "decimal": "NUMBER(12,2)", "date": "DATE"}
