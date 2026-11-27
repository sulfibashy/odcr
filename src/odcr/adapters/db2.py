"""IBM Db2 adapter (ibm_db) for Db2 LUW, Db2 on Cloud and Db2 Warehouse. Db2 for z/OS and IBM i work
for checks; their catalog differs, so schema checks may need the `catalog: sysibm` option."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class Db2Adapter(Adapter):
    dialect = "db2"
    driver = "ibm_db"
    paramstyle = "qmark"
    quote_policy = "needed"
    default_schema_sql = "VALUES CURRENT SCHEMA"
    ping_sql = "SELECT 1 FROM SYSIBM.SYSDUMMY1"
    ignore_errors = ("SQL0601N", "SQLSTATE=42710")

    def _connect(self) -> Any:
        try:
            import ibm_db_dbi
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Db2 support needs: pip install odcr-db2") from exc
        o = self.options
        dsn = o.get("dsn") or (
            f"DATABASE={o.get('database')};HOSTNAME={o.get('host', 'localhost')};PORT={int(o.get('port', 50000))};"
            f"PROTOCOL=TCPIP;UID={o.get('user') or o.get('username')};PWD={o.get('password', '')};"
            + ("SECURITY=SSL;" if o.get("ssl") else ""))
        conn = ibm_db_dbi.connect(dsn, "", "")
        setter = getattr(conn, "set_autocommit", None)
        if setter:
            setter(True)
        return conn

    def current_schema(self) -> str | None:
        return str(super().current_schema()).strip()

    def limit(self, select_sql: str, n: int) -> str:
        return f"{select_sql} FETCH FIRST {int(n)} ROWS ONLY"

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        rows = self.fetchall(
            "SELECT colname, typename FROM syscat.columns "
            f"WHERE LOWER(TRIM(tabschema)) = LOWER({self.placeholder}) AND LOWER(tabname) = LOWER({self.placeholder})",
            [schema, table])
        return {str(c).lower(): str(t).lower().strip() for c, t in rows}

    def create_schema_sql(self, schema: str) -> str:
        return f"CREATE SCHEMA {self.qualify(schema)}"

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE TABLE {table} ({columns_sql})"

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "num": "DOUBLE"}

    def _commit(self) -> None:
        commit = getattr(self.conn, "commit", None)
        if commit:
            commit()
