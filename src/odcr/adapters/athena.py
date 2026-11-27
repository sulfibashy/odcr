"""Amazon Athena adapter (PyAthena). Checks run on any Athena table (Glue Data Catalog).

Meta tables are Apache Iceberg tables and need an S3 location: set `meta_location: s3://bucket/odcr_meta/`
on the connection, or store meta tables elsewhere with `meta: {connection: <other connection>}`.
"""

from __future__ import annotations

from typing import Any

from .base import Adapter


class AthenaAdapter(Adapter):
    dialect = "athena"
    driver = "pyathena"
    paramstyle = "inline"
    multi_row_insert = True

    def _connect(self) -> Any:
        try:
            from pyathena import connect
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Athena support needs: pip install odcr-athena") from exc
        o = self.options
        kwargs = {k: o[k] for k in ("s3_staging_dir", "region_name", "work_group", "catalog_name", "profile_name")
                  if o.get(k)}
        kwargs["schema_name"] = o.get("schema", "default")
        return connect(**kwargs)

    def current_schema(self) -> str | None:
        return self.options.get("schema", "default")

    def meta_ensure(self, schema: str) -> None:
        if schema in self._meta_ready:
            return
        from ..meta import TABLES

        location = str(self.options.get("meta_location", "")).rstrip("/")
        if not location:
            raise ValueError("Athena meta tables need 'meta_location: s3://bucket/prefix' on the connection, "
                             "or set meta.connection to store results on another platform")
        types = {"id": "string", "name": "string", "short": "string", "text": "string", "ts": "timestamp",
                 "int": "bigint", "num": "double"}
        self.execute(f"CREATE DATABASE IF NOT EXISTS `{schema}`")
        for table, cols in TABLES.items():
            cols_sql = ", ".join(f"`{c}` {types[t]}" for c, t in cols)
            self.execute(f"CREATE TABLE IF NOT EXISTS `{schema}`.`{table}` ({cols_sql}) "
                         f"LOCATION '{location}/{table}/' TBLPROPERTIES ('table_type'='ICEBERG')")
        self._meta_ready.add(schema)

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INT", "string": "STRING", "decimal": "DECIMAL(12,2)", "date": "DATE"}
