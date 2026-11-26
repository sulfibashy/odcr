"""Databricks adapter (databricks-sql-connector) for SQL warehouses and clusters on Azure, AWS and GCP.
Works with Unity Catalog (catalog.schema.table) and the legacy hive_metastore. Meta tables are Delta tables.

Authentication: personal access token (`access_token`), OAuth machine-to-machine (`client_id` +
`client_secret` via auth_type), or browser OAuth (`auth_type: databricks-oauth`).
"""

from __future__ import annotations

from typing import Any

from .base import Adapter


class DatabricksAdapter(Adapter):
    dialect = "databricks"
    driver = "databricks.sql"
    paramstyle = "named"
    quote_open = quote_close = "`"
    multi_row_insert = True

    def _connect(self) -> Any:
        try:
            from databricks import sql
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Databricks support needs: pip install 'odcr[databricks]'") from exc
        o = self.options
        kwargs: dict[str, Any] = {"server_hostname": o["host"].replace("https://", "").rstrip("/"),
                                  "http_path": o["http_path"]}
        for key in ("access_token", "auth_type", "client_id", "client_secret", "catalog", "schema"):
            if o.get(key):
                kwargs[key] = o[key]
        if o.get("token") and "access_token" not in kwargs:
            kwargs["access_token"] = o["token"]
        return sql.connect(**kwargs)

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        try:
            rows = self.fetchall(f"DESCRIBE TABLE {self.qualify(name)}")
        except Exception:  # noqa: BLE001 - table does not exist
            return {}
        out: dict[str, str] = {}
        for col, dtype, *_ in rows:
            if not col or str(col).startswith("#"):
                break
            out[str(col).lower()] = str(dtype).lower()
        return out

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE TABLE IF NOT EXISTS {table} ({columns_sql}) USING DELTA"

    def meta_types(self) -> dict[str, str]:
        return {k: "STRING" for k in ("id", "name", "short", "text")} | {"ts": "TIMESTAMP", "int": "BIGINT",
                                                                          "num": "DOUBLE"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INT", "string": "STRING", "decimal": "DECIMAL(12,2)", "date": "DATE"}
