"""Teradata adapter (teradatasql). Teradata Vantage on-premise, VantageCloud Lake and Enterprise on AWS,
Azure and GCP. Logon mechanisms (`logmech`: TD2, LDAP, KRB5, JWT, BROWSER for Entra ID / Okta single sign-on)
and TLS (`sslmode`) are passed to the driver.

Meta tables are created in the default database with the prefix odcr_meta_, as MULTISET tables.
"""

from __future__ import annotations

from typing import Any

from .base import Adapter

# DBC.ColumnsV.ColumnType codes -> type names
_TYPES = {"I": "integer", "I1": "byteint", "I2": "smallint", "I8": "bigint", "D": "decimal", "N": "number",
          "F": "float", "CV": "varchar", "CF": "char", "CO": "clob", "DA": "date", "TS": "timestamp",
          "SZ": "timestamp with time zone", "AT": "time", "TZ": "time with time zone", "BF": "byte",
          "BV": "varbyte", "BO": "blob", "JN": "json", "XM": "xml", "PD": "period"}
_DRIVER_OPTIONS = ("logmech", "logdata", "sslmode", "sslca", "sslcapath", "encryptdata", "tmode", "dbs_port",
                   "browser", "oidc_clientid", "oidc_scope", "connect_timeout", "cop")


class TeradataAdapter(Adapter):
    dialect = "teradata"
    driver = "teradatasql"
    paramstyle = "qmark"
    quote_policy = "needed"
    meta_in_current_schema = True
    default_schema_sql = "SELECT DATABASE"
    ignore_errors = ("[Error 3803]", "[Error 5612]")  # table already exists

    def _connect(self) -> Any:
        try:
            import teradatasql
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Teradata support needs: pip install odcr-teradata") from exc
        o = self.options
        params: dict[str, Any] = {"host": o.get("host", "localhost")}
        for key in ("user", "password", "database"):
            if o.get(key):
                params[key] = str(o[key])
        if o.get("username") and "user" not in params:
            params["user"] = str(o["username"])
        if o.get("port"):
            params["dbs_port"] = str(o["port"])
        params.update({k: str(o[k]) for k in _DRIVER_OPTIONS if o.get(k) not in (None, "")})
        return teradatasql.connect(None, **params)

    def current_schema(self) -> str | None:
        return str(super().current_schema()).strip()

    def limit(self, select_sql: str, n: int) -> str:
        if select_sql.upper().startswith("SELECT DISTINCT "):
            return f"SELECT DISTINCT TOP {int(n)} " + select_sql[16:]
        return f"SELECT TOP {int(n)} " + select_sql[7:]

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        rows = self.fetchall("SELECT TRIM(ColumnName), TRIM(ColumnType) FROM DBC.ColumnsV "
                             "WHERE TRIM(DatabaseName) = ? AND TRIM(TableName) = ?", [schema, table])
        return {str(c).lower(): _TYPES.get(str(t).upper(), str(t).lower()) for c, t in rows}

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE MULTISET TABLE {table} ({columns_sql}) NO PRIMARY INDEX"

    def sample_table_sql(self, table: str, columns_sql: str) -> str:
        return self.create_table_sql(table, columns_sql)  # MULTISET: keep duplicate rows

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "text": "VARCHAR(4000) CHARACTER SET UNICODE", "ts": "TIMESTAMP(6)",
                "num": "FLOAT"}
