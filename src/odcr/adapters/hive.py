"""Apache Hive and Spark SQL (Thrift server) adapter (PyHive), and Apache Impala (impyla).

Covers Cloudera CDP / CDH, Amazon EMR, Google Dataproc, Azure HDInsight and on-premise Hadoop clusters.
Authentication: NONE, LDAP, KERBEROS or CUSTOM (`auth`), with TLS where the cluster offers it.
For Databricks use the databricks adapter.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .base import Adapter


class HiveAdapter(Adapter):
    dialect = "hive"
    driver = "pyhive"
    quote_open = quote_close = "`"
    default_schema_sql = "SELECT current_database()"
    multi_row_insert = True  # every INSERT is a job: send rows together

    def _connect(self) -> Any:
        try:
            from pyhive import hive
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Hive / Spark support needs: pip install odcr-hive") from exc
        o = self.options
        kwargs: dict[str, Any] = {"host": o.get("host", "localhost"), "port": int(o.get("port", 10000)),
                                  "database": o.get("database") or o.get("schema") or "default"}
        user = o.get("user") or o.get("username")
        if user:
            kwargs["username"] = user
        auth = str(o.get("auth") or ("LDAP" if o.get("password") else "NONE")).upper()
        if auth != "NONE":
            kwargs["auth"] = auth
        if auth in ("LDAP", "CUSTOM"):
            kwargs["password"] = o.get("password")
        if auth == "KERBEROS":
            kwargs["kerberos_service_name"] = o.get("kerberos_service_name", "hive")
        if o.get("configuration"):
            kwargs["configuration"] = dict(o["configuration"])
        return hive.connect(**kwargs)

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        try:
            rows = self.fetchall(f"DESCRIBE {self.qualify(name)}")
        except Exception:  # noqa: BLE001 - table does not exist
            self._rollback()
            return {}
        out: dict[str, str] = {}
        for col, dtype, *_ in rows:
            col = str(col or "").strip()
            if not col or col.startswith("#"):
                break
            out[col.lower()] = str(dtype).strip().lower()
        return out

    def create_schema_sql(self, schema: str) -> str:
        return f"CREATE DATABASE IF NOT EXISTS {self.quote(schema)}"

    def meta_types(self) -> dict[str, str]:
        return {k: "STRING" for k in ("id", "name", "short", "text")} | {"ts": "TIMESTAMP", "int": "BIGINT",
                                                                          "num": "DOUBLE"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INT", "string": "STRING", "decimal": "DECIMAL(12,2)", "date": "DATE"}


class ImpalaAdapter(HiveAdapter):
    dialect = "impala"
    driver = "impala"
    paramstyle = "inline"

    def _connect(self) -> Any:
        try:
            from impala.dbapi import connect
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Impala support needs: pip install odcr-impala") from exc
        o = self.options
        kwargs: dict[str, Any] = {"host": o.get("host", "localhost"), "port": int(o.get("port", 21050)),
                                  "database": o.get("database") or o.get("schema") or "default",
                                  "auth_mechanism": str(o.get("auth") or ("LDAP" if o.get("password") else "NOSASL"))
                                  .upper()}
        for key in ("user", "password", "use_ssl", "ca_cert", "kerberos_service_name", "use_http_transport",
                    "http_path", "jwt"):
            if o.get(key) not in (None, ""):
                kwargs[key] = o[key]
        return connect(**kwargs)

    def literal(self, value: Any) -> str:
        if isinstance(value, str):
            return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        if isinstance(value, dt.datetime):
            return f"CAST('{value.strftime('%Y-%m-%d %H:%M:%S.%f')}' AS TIMESTAMP)"
        if isinstance(value, dt.date):
            return f"CAST('{value.isoformat()}' AS DATE)"
        return super().literal(value)
