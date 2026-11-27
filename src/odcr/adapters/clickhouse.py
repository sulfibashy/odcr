"""ClickHouse adapter. Self-managed ClickHouse, ClickHouse Cloud, Altinity and Aiven, over HTTP(S) with
clickhouse-connect; or embedded in the process with chDB (`client: chdb`, no server at all).

In ClickHouse a schema is a database. Meta tables are MergeTree tables with Nullable columns.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .base import Adapter


class ClickHouseAdapter(Adapter):
    dialect = "clickhouse"
    driver = "clickhouse_connect"
    paramstyle = "inline"  # values are rendered as ClickHouse literals by odcr
    default_schema_sql = "SELECT currentDatabase()"
    multi_row_insert = True  # every INSERT creates a data part: send rows together

    def _connect(self) -> Any:
        o = self.options
        if str(o.get("client", "http")).lower() == "chdb":
            try:
                from chdb import dbapi
            except ImportError as exc:  # pragma: no cover
                raise ImportError("Embedded ClickHouse needs: pip install chdb") from exc
            self.driver = "chdb"
            return dbapi.connect(str(o.get("path") or ":memory:"))
        try:
            from clickhouse_connect import dbapi
        except ImportError as exc:  # pragma: no cover
            raise ImportError("ClickHouse support needs: pip install odcr-clickhouse") from exc
        secure = bool(o.get("secure", str(o.get("port", "")) in ("8443", "443")))
        kwargs: dict[str, Any] = {
            "host": o.get("host", "localhost"), "port": int(o.get("port", 8443 if secure else 8123)),
            "username": o.get("user") or o.get("username") or "default", "password": o.get("password") or "",
            "database": o.get("database") or "default", "secure": secure}
        for key in ("access_token", "verify", "ca_cert", "client_cert", "client_cert_key"):
            if o.get(key) not in (None, ""):
                kwargs[key] = o[key]
        return dbapi.connect(**kwargs)

    def _run(self, cur: Any, sql: str, params: Any) -> None:
        q, _ = self._bind(sql, params)  # inline: no driver parameters
        if self.driver == "clickhouse_connect":
            cur.execute(q, pyformat_encoded=False)  # keep '%' in values and patterns as written
        else:
            cur.execute(q)

    def literal(self, value: Any) -> str:
        if isinstance(value, str):
            return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        if isinstance(value, dt.datetime):
            return f"toDateTime64('{value.strftime('%Y-%m-%d %H:%M:%S.%f')}', 6)"
        if isinstance(value, dt.date):
            return f"toDate('{value.isoformat()}')"
        return super().literal(value)

    def executemany(self, sql: str, rows: Any) -> None:
        rows = [list(r) for r in rows]
        if not rows:
            return
        head, sep, group = sql.rpartition(" VALUES ")
        if not sep:
            super().executemany(sql, rows)
            return
        self.execute(f"{head} VALUES " + ", ".join([group] * len(rows)), [v for r in rows for v in r])

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        rows = self.fetchall(f"SELECT name, type FROM system.columns WHERE database = {self.placeholder} "
                             f"AND table = {self.placeholder}", [schema, table])
        return {str(c).lower(): str(t).lower() for c, t in rows}

    def raw_columns(self, expr: str) -> dict[str, str]:
        try:
            rows = self.fetchall(f"DESCRIBE TABLE (SELECT * FROM {expr})")
        except Exception:  # noqa: BLE001
            return {}
        return {str(r[0]).lower(): str(r[1]).lower() for r in rows}

    def create_schema_sql(self, schema: str) -> str:
        return f"CREATE DATABASE IF NOT EXISTS {self.quote(schema)}"

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE TABLE IF NOT EXISTS {table} ({columns_sql}) ENGINE = MergeTree ORDER BY tuple()"

    def sample_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE TABLE {table} ({columns_sql}) ENGINE = MergeTree ORDER BY tuple()"

    def meta_types(self) -> dict[str, str]:
        return {k: "Nullable(String)" for k in ("id", "name", "short", "text")} | {
            "ts": "Nullable(DateTime64(6))", "int": "Nullable(Int64)", "num": "Nullable(Float64)"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "Nullable(Int32)", "string": "Nullable(String)", "decimal": "Nullable(Decimal(12, 2))",
                "date": "Nullable(Date)"}
