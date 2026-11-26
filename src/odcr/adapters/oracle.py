"""Oracle Database adapter (python-oracledb, thin mode: no Oracle Client needed). Also Oracle Autonomous
Database. Meta tables are created in the current schema with the prefix odcr_meta_."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class OracleAdapter(Adapter):
    dialect = "oracle"
    driver = "oracledb"
    paramstyle = "named"
    quote_policy = "needed"
    meta_in_current_schema = True
    default_schema_sql = "SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM dual"
    ping_sql = "SELECT 1 FROM dual"
    ignore_errors = ("ORA-00955", "ORA-01920")

    def _connect(self) -> Any:
        try:
            import oracledb
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Oracle support needs: pip install 'odcr[oracle]'") from exc
        o = self.options
        dsn = o.get("dsn") or f"{o.get('host', 'localhost')}:{int(o.get('port', 1521))}/{o.get('service_name', 'FREEPDB1')}"
        conn = oracledb.connect(user=o.get("user") or o.get("username"), password=o.get("password"), dsn=dsn,
                                config_dir=o.get("config_dir"), wallet_location=o.get("wallet_location"),
                                wallet_password=o.get("wallet_password"))
        conn.autocommit = True
        return conn

    def limit(self, select_sql: str, n: int) -> str:
        return f"{select_sql} FETCH FIRST {int(n)} ROWS ONLY"

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        rows = self.fetchall(
            "SELECT column_name, data_type FROM all_tab_columns "
            f"WHERE LOWER(owner) = LOWER({self.placeholder}) AND LOWER(table_name) = LOWER({self.placeholder})",
            [schema, table])
        return {str(c).lower(): str(t).lower() for c, t in rows}

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE TABLE {table} ({columns_sql})"

    def meta_types(self) -> dict[str, str]:
        return {"id": "VARCHAR2(64)", "name": "VARCHAR2(255)", "short": "VARCHAR2(32)", "text": "VARCHAR2(4000)",
                "ts": "TIMESTAMP", "int": "NUMBER(19)", "num": "BINARY_DOUBLE"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "NUMBER(10)", "string": "VARCHAR2(50)", "decimal": "NUMBER(12,2)", "date": "DATE"}
