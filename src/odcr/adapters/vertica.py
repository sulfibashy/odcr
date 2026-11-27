"""Vertica adapter (vertica-python). OpenText Vertica on-premise, Vertica Accelerator and Eon mode on
AWS, Azure or GCP. TLS (`tlsmode`), OAuth (`oauth_access_token`) and Kerberos are passed to the driver."""

from __future__ import annotations

from typing import Any

from .base import Adapter

_DRIVER_OPTIONS = ("tlsmode", "tls_verify", "tls_cafile", "tls_certfile", "tls_keyfile", "oauth_access_token",
                   "kerberos_service_name", "kerberos_host_name", "session_label", "connection_load_balance",
                   "backup_server_node", "workload", "connection_timeout")


class VerticaAdapter(Adapter):
    dialect = "vertica"
    driver = "vertica_python"
    default_schema_sql = "SELECT CURRENT_SCHEMA()"

    def _connect(self) -> Any:
        try:
            import vertica_python
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Vertica support needs: pip install odcr-vertica") from exc
        o = self.options
        info: dict[str, Any] = {"host": o.get("host", "localhost"), "port": int(o.get("port", 5433)),
                                "user": o.get("user") or o.get("username"), "database": o.get("database", ""),
                                "autocommit": True}
        if o.get("password"):
            info["password"] = o["password"]
        info.update({k: o[k] for k in _DRIVER_OPTIONS if o.get(k) not in (None, "")})
        conn = vertica_python.connect(**info)
        if o.get("schema"):
            cur = conn.cursor()
            cur.execute(f"SET SEARCH_PATH TO {self.quote(o['schema'])}, public")
            cur.close()
        return conn

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        p = self.placeholder
        rows = self.fetchall(
            "SELECT column_name, data_type FROM v_catalog.columns WHERE LOWER(table_schema) = LOWER(%s) "
            "AND LOWER(table_name) = LOWER(%s) UNION ALL SELECT column_name, data_type FROM v_catalog.view_columns "
            "WHERE LOWER(table_schema) = LOWER(%s) AND LOWER(table_name) = LOWER(%s)".replace("%s", p),
            [schema, table, schema, table])
        return {str(c).lower(): str(t).lower() for c, t in rows}

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "num": "FLOAT"}
