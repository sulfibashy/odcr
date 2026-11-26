"""MySQL / MariaDB adapter (PyMySQL). Also: Amazon Aurora / RDS MySQL, Azure Database for MySQL,
Google Cloud SQL for MySQL, TiDB, SingleStore. In MySQL a schema is a database."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class MySQLAdapter(Adapter):
    dialect = "mysql"
    driver = "pymysql"
    quote_open = quote_close = "`"
    default_schema_sql = "SELECT DATABASE()"

    def _connect(self) -> Any:
        try:
            import pymysql
        except ImportError as exc:  # pragma: no cover
            raise ImportError("MySQL support needs: pip install 'odcr[mysql]'") from exc
        o = self.options
        ssl = {"ssl": {"ca": o["ssl_ca"]}} if o.get("ssl_ca") else {}
        return pymysql.connect(
            host=o.get("host", "localhost"), port=int(o.get("port", 3306)),
            database=o.get("database") or o.get("schema"), user=o.get("user") or o.get("username"),
            password=o.get("password") or "", autocommit=True, charset="utf8mb4", **ssl)

    def create_schema_sql(self, schema: str) -> str:
        return f"CREATE DATABASE IF NOT EXISTS {self.quote(schema)}"

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "ts": "DATETIME(6)", "num": "DOUBLE", "text": "TEXT"}
