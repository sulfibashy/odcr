"""Amazon Redshift adapter (redshift_connector). Works for provisioned clusters and Redshift Serverless,
with password or IAM authentication."""

from __future__ import annotations

from typing import Any

from .postgres import PostgresAdapter


class RedshiftAdapter(PostgresAdapter):
    dialect = "redshift"
    driver = "redshift_connector"

    def _connect(self) -> Any:
        try:
            import redshift_connector
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Redshift support needs: pip install odcr-redshift") from exc
        o = {k: v for k, v in self.options.items() if k not in ("schema",)}
        o["port"] = int(o.get("port", 5439))
        if "username" in o:
            o["user"] = o.pop("username")
        conn = redshift_connector.connect(**o)
        conn.autocommit = True
        if self.options.get("schema"):
            cur = conn.cursor()
            cur.execute(f"SET search_path TO {self.quote(self.options['schema'])}, public")
            cur.close()
        return conn

    def meta_types(self) -> dict[str, str]:
        return {**super().meta_types(), "text": "VARCHAR(65535)"}
