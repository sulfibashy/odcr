"""MySQL / MariaDB adapter (PyMySQL). In MySQL a schema is a database."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class MySQLAdapter(Adapter):
    dialect = "mysql"
    placeholder = "%s"
    default_schema_sql = "SELECT DATABASE()"

    def _connect(self) -> Any:
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover
            raise ImportError("MySQL support needs: pip install 'odcr[mysql]'") from exc
        o = self.options
        return pymysql.connect(
            host=o.get("host", "localhost"),
            port=int(o.get("port", 3306)),
            database=o.get("database") or o.get("schema"),
            user=o.get("user") or o.get("username"),
            password=o.get("password") or "",
            autocommit=True,
            charset="utf8mb4",
        )

    def quote(self, identifier: str) -> str:
        return "`" + identifier.replace("`", "``") + "`"

    def create_schema(self, schema: str) -> None:
        self.execute(f"CREATE DATABASE IF NOT EXISTS {self.quote(schema)}")

    def meta_types(self) -> dict[str, str]:
        t = super().meta_types()
        t.update({"ts": "DATETIME(6)", "num": "DOUBLE"})
        return t
