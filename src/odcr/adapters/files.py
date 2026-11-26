"""Files adapter: check files the moment they land, in local folders, ADLS Gen2 / Azure Blob, Amazon S3,
Google Cloud Storage, SFTP-mounted or network shares. Uses DuckDB as the engine, so files are read in
place without loading them anywhere.

A contract's physicalName is a path or glob; the format comes from the extension (or `format:`):

    physicalName: abfss://landing@mylake.dfs.core.windows.net/orders/2026/11/26/*.parquet
    physicalName: s3://landing/orders/*.csv
    physicalName: landing/orders/*.json            # local or network path
    physicalName: "read_csv('landing/orders/*.txt', delim='|')"   # any DuckDB table function

Connection options:
    storage: local | azure | s3 | gcs
    azure:  account_name + (connection_string | tenant_id/client_id/client_secret | credential_chain)
    s3:     region + (key_id/secret | credential_chain)  [+ endpoint for MinIO / S3-compatible]
    gcs:    key_id/secret (HMAC) | credential_chain
    meta_path: odcr_meta.duckdb    # where meta tables are stored (or use meta: {connection: ...})
"""

from __future__ import annotations

from typing import Any

from .duckdb import DuckDBAdapter

READERS = {
    ".parquet": "read_parquet", ".pq": "read_parquet",
    ".csv": "read_csv_auto", ".tsv": "read_csv_auto", ".txt": "read_csv_auto", ".gz": "read_csv_auto",
    ".json": "read_json_auto", ".jsonl": "read_json_auto", ".ndjson": "read_json_auto",
}
REMOTE = ("abfss://", "az://", "azure://", "s3://", "s3a://", "gs://", "gcs://", "http://", "https://", "r2://")


class FilesAdapter(DuckDBAdapter):
    dialect = "files"

    def _connect(self) -> Any:
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise ImportError("File support needs: pip install 'odcr[files]'") from exc
        conn = duckdb.connect(str(self.options.get("meta_path") or ":memory:"))
        self._configure_storage(conn)
        return conn

    # -- storage credentials (stored only in DuckDB's in-memory secret manager for this process)
    def _configure_storage(self, conn: Any) -> None:
        o = self.options
        storage = str(o.get("storage", "local")).lower()
        if storage in ("azure", "adls", "blob"):
            conn.execute("INSTALL azure; LOAD azure;")
            if o.get("connection_string"):
                conn.execute("CREATE OR REPLACE SECRET odcr_azure (TYPE azure, "
                             f"CONNECTION_STRING {self.literal(o['connection_string'])})")
            elif o.get("client_id"):
                conn.execute(
                    "CREATE OR REPLACE SECRET odcr_azure (TYPE azure, PROVIDER service_principal, "
                    f"TENANT_ID {self.literal(o['tenant_id'])}, CLIENT_ID {self.literal(o['client_id'])}, "
                    f"CLIENT_SECRET {self.literal(o['client_secret'])}, ACCOUNT_NAME {self.literal(o['account_name'])})")
            else:
                conn.execute("CREATE OR REPLACE SECRET odcr_azure (TYPE azure, PROVIDER credential_chain, "
                             f"ACCOUNT_NAME {self.literal(o['account_name'])})")
            if o.get("transport") == "curl":  # behind corporate proxies / custom CA bundles
                conn.execute("SET azure_transport_option_type = 'curl'")
        elif storage in ("s3", "minio", "r2"):
            conn.execute("INSTALL httpfs; LOAD httpfs;")
            parts = ["TYPE s3"]
            if o.get("key_id"):
                parts += [f"KEY_ID {self.literal(o['key_id'])}", f"SECRET {self.literal(o['secret'])}"]
            else:
                parts.append("PROVIDER credential_chain")
            if o.get("region"):
                parts.append(f"REGION {self.literal(o['region'])}")
            if o.get("endpoint"):
                parts.append(f"ENDPOINT {self.literal(o['endpoint'])}")
                parts.append(f"USE_SSL {'true' if o.get('use_ssl', True) else 'false'}")
                parts.append("URL_STYLE 'path'")
            conn.execute(f"CREATE OR REPLACE SECRET odcr_s3 ({', '.join(parts)})")
        elif storage in ("gcs", "gs"):
            conn.execute("INSTALL httpfs; LOAD httpfs;")
            if o.get("key_id"):
                conn.execute(f"CREATE OR REPLACE SECRET odcr_gcs (TYPE gcs, KEY_ID {self.literal(o['key_id'])}, "
                             f"SECRET {self.literal(o['secret'])})")
            else:
                conn.execute("CREATE OR REPLACE SECRET odcr_gcs (TYPE gcs, PROVIDER credential_chain)")
        if o.get("ca_bundle"):
            conn.execute(f"SET ca_cert_file = {self.literal(o['ca_bundle'])}")

    # -- paths become table functions
    def reader(self, path: str) -> str:
        fmt = self.options.get("format")
        if fmt:
            return {"parquet": "read_parquet", "csv": "read_csv_auto", "json": "read_json_auto"}[str(fmt)]
        lower = path.lower().rstrip("*/")
        for ext, fn in READERS.items():
            if lower.endswith(ext) or f"{ext}." in lower:
                return fn
        return "read_parquet"

    def to_relation(self, name: str) -> str:
        if "(" in name:
            return name  # already a table function
        if name.startswith(REMOTE) or "/" in name or "\\" in name or "*" in name or "." in name.split("/")[-1]:
            options = ", union_by_name = true" if self.reader(name) == "read_parquet" else ""
            return f"{self.reader(name)}({self.literal(name)}{options})"
        return self.quote(name)  # a table inside the meta database

    def qualify(self, name: str) -> str:
        return self.to_relation(name)

    def columns(self, name: str) -> dict[str, str]:
        rel = self.to_relation(name)
        if rel == self.quote(name):
            return super().columns(name)
        return self.raw_columns(rel)

    def list_files(self, pattern: str) -> list[str]:
        """Files matching a glob, local or remote (used by `odcr watch`)."""
        return sorted(str(r[0]) for r in self.fetchall(f"SELECT file FROM glob({self.literal(pattern)})"))

    def create_sample(self, name: str, columns: list[tuple[str, str]], rows: list) -> None:  # type: ignore[override]
        """Write the rows as a Parquet / CSV / JSON file at `name` (a local path)."""
        from pathlib import Path

        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = "odcr_sample_tmp"
        super().create_sample(tmp, columns, rows)
        fmt = {"read_csv_auto": "CSV, HEADER", "read_json_auto": "JSON"}.get(self.reader(name), "PARQUET")
        self.execute(f"COPY {self.quote(tmp)} TO {self.literal(str(path))} (FORMAT {fmt})")
        self.execute(f"DROP TABLE {self.quote(tmp)}")

    def drop_table(self, name: str) -> None:
        if "/" in name or "\\" in name or "." in name.split("/")[-1]:
            from pathlib import Path

            Path(name).unlink(missing_ok=True)
        else:
            super().drop_table(name)
