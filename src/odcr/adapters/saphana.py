"""SAP HANA adapter (hdbcli). SAP HANA Cloud, SAP HANA on-premise and SAP Datasphere (its SQL endpoint).
TLS is on and the server certificate is verified by default. JWT and SAML single sign-on, X.509 and
Kerberos are passed to the driver."""

from __future__ import annotations

from typing import Any

from .base import Adapter

_DRIVER_OPTIONS = ("sslValidateCertificate", "sslTrustStore", "sslCryptoProvider", "sslHostNameInCertificate",
                   "authenticationMethods", "authenticationX509", "databaseName", "nodeConnectTimeout")


class SAPHanaAdapter(Adapter):
    dialect = "saphana"
    driver = "hdbcli"
    paramstyle = "qmark"
    quote_policy = "needed"
    default_schema_sql = "SELECT CURRENT_SCHEMA FROM DUMMY"
    ping_sql = "SELECT 1 FROM DUMMY"
    ignore_errors = ("duplicate table name", "duplicate schema name", "(288,", "(386,")

    def _connect(self) -> Any:
        try:
            from hdbcli import dbapi
        except ImportError as exc:  # pragma: no cover
            raise ImportError("SAP HANA support needs: pip install odcr-saphana") from exc
        o = self.options
        kwargs: dict[str, Any] = {"address": o.get("host", "localhost"), "port": int(o.get("port", 443)),
                                  "encrypt": bool(o.get("encrypt", True)), "autocommit": True}
        for key in ("user", "password"):
            if o.get(key):
                kwargs[key] = o[key]
        if o.get("schema"):
            kwargs["currentSchema"] = o["schema"]
        kwargs.update({k: o[k] for k in _DRIVER_OPTIONS if o.get(k) not in (None, "")})
        return dbapi.connect(**kwargs)

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        sql = ("SELECT COLUMN_NAME, DATA_TYPE_NAME FROM SYS.TABLE_COLUMNS WHERE LOWER(SCHEMA_NAME) = LOWER(?) "
               "AND LOWER(TABLE_NAME) = LOWER(?) UNION ALL SELECT COLUMN_NAME, DATA_TYPE_NAME FROM SYS.VIEW_COLUMNS "
               "WHERE LOWER(SCHEMA_NAME) = LOWER(?) AND LOWER(VIEW_NAME) = LOWER(?)")
        rows = self.fetchall(sql, [schema, table, schema, table])
        return {str(c).lower(): str(t).lower() for c, t in rows}

    def create_schema_sql(self, schema: str) -> str:
        return f"CREATE SCHEMA {self.quote(schema)}"

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE COLUMN TABLE {table} ({columns_sql})"

    def meta_types(self) -> dict[str, str]:
        return {"id": "NVARCHAR(64)", "name": "NVARCHAR(255)", "short": "NVARCHAR(32)", "text": "NVARCHAR(5000)",
                "ts": "TIMESTAMP", "int": "BIGINT", "num": "DOUBLE"}

    def sample_types(self) -> dict[str, str]:
        return {**super().sample_types(), "string": "NVARCHAR(50)"}
