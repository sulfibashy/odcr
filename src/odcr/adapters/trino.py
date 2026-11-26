"""Trino / Starburst / Presto adapter (trino client). One adapter reaches every catalog Trino can query:
Hive, Iceberg, Delta Lake, PostgreSQL, Kafka and more."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class TrinoAdapter(Adapter):
    dialect = "trino"
    driver = "trino"
    paramstyle = "qmark"
    default_schema_sql = "SELECT current_schema"
    multi_row_insert = True

    def _connect(self) -> Any:
        try:
            import trino
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Trino support needs: pip install 'odcr[trino]'") from exc
        o = self.options
        auth = None
        if o.get("password"):
            auth = trino.auth.BasicAuthentication(o.get("user", "odcr"), o["password"])
        elif o.get("jwt"):
            auth = trino.auth.JWTAuthentication(o["jwt"])
        return trino.dbapi.connect(host=o.get("host", "localhost"), port=int(o.get("port", 8080)),
                                   user=o.get("user", "odcr"), catalog=o.get("catalog"), schema=o.get("schema"),
                                   http_scheme=o.get("http_scheme", "https" if auth else "http"), auth=auth)

    def meta_types(self) -> dict[str, str]:
        return {"id": "VARCHAR", "name": "VARCHAR", "short": "VARCHAR", "text": "VARCHAR", "ts": "TIMESTAMP(6)",
                "int": "BIGINT", "num": "DOUBLE"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INTEGER", "string": "VARCHAR", "decimal": "DECIMAL(12,2)", "date": "DATE"}
