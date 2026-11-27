"""PostgreSQL adapter (psycopg 3). Also: Amazon Aurora / RDS PostgreSQL, Azure Database for PostgreSQL,
Google Cloud SQL / AlloyDB, Supabase, Neon, CockroachDB (PostgreSQL wire protocol)."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class PostgresAdapter(Adapter):
    dialect = "postgres"
    driver = "psycopg"

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise ImportError("PostgreSQL support needs: pip install odcr-postgres") from exc
        o = self.options
        if o.get("dsn"):
            conn = psycopg.connect(o["dsn"], autocommit=True)
        else:
            conn = psycopg.connect(
                host=o.get("host", "localhost"), port=int(o.get("port", 5432)),
                dbname=o.get("database") or o.get("dbname"), user=o.get("user") or o.get("username"),
                password=o.get("password") or None, sslmode=o.get("sslmode", "prefer"), autocommit=True)
        if o.get("schema"):
            conn.execute(f"SET search_path TO {self.quote(o['schema'])}, public")
        return conn

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "text": "TEXT"}
