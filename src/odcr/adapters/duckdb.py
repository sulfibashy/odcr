"""DuckDB adapter: local or MotherDuck databases, and files directly.

Files in a landing zone can be checked before they are loaded, by using a table function as the
contract's physicalName, e.g. physicalName: "read_parquet('landing/orders/*.parquet')" or
"read_csv('landing/orders.csv')". Column names and types are read from the files.
"""

from __future__ import annotations

from typing import Any

from .base import Adapter


class DuckDBAdapter(Adapter):
    dialect = "duckdb"
    driver = "duckdb"
    paramstyle = "qmark"

    def _connect(self) -> Any:
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise ImportError("DuckDB support needs: pip install odcr-duckdb") from exc
        return duckdb.connect(str(self.options.get("path") or self.options.get("database") or ":memory:"),
                              read_only=bool(self.options.get("read_only", False)))

    def raw_columns(self, expr: str) -> dict[str, str]:
        try:
            rows = self.fetchall(f"DESCRIBE SELECT * FROM {expr}")
        except Exception:  # noqa: BLE001
            return {}
        return {str(r[0]).lower(): str(r[1]).lower() for r in rows}

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "text": "VARCHAR", "num": "DOUBLE"}
