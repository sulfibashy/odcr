"""Google BigQuery adapter (google-cloud-bigquery DB-API). Authentication uses Application Default
Credentials or a service-account key file (`credentials_path`). Meta tables live in a dataset."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class BigQueryAdapter(Adapter):
    dialect = "bigquery"
    driver = "google.cloud.bigquery"
    quote_open = quote_close = "`"
    multi_row_insert = True

    def _connect(self) -> Any:
        try:
            from google.cloud import bigquery
            from google.cloud.bigquery import dbapi
        except ImportError as exc:  # pragma: no cover
            raise ImportError("BigQuery support needs: pip install odcr-bigquery") from exc
        o = self.options
        if o.get("credentials_path"):
            client = bigquery.Client.from_service_account_json(o["credentials_path"], project=o.get("project"),
                                                               location=o.get("location"))
        else:
            client = bigquery.Client(project=o.get("project"), location=o.get("location"))
        if o.get("dataset"):
            client.default_query_job_config = bigquery.QueryJobConfig(
                default_dataset=f"{client.project}.{o['dataset']}")
        self._project = client.project
        return dbapi.connect(client)

    def current_schema(self) -> str | None:
        return self.options.get("dataset")

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        parts = name.split(".")
        table = parts[-1]
        dataset = ".".join(parts[:-1]) or str(self.current_schema())
        try:
            rows = self.fetchall(f"SELECT column_name, data_type FROM {self.qualify(dataset)}.INFORMATION_SCHEMA.COLUMNS "
                                 f"WHERE LOWER(table_name) = LOWER({self.placeholder})", [table])
        except Exception:  # noqa: BLE001 - dataset does not exist
            return {}
        return {str(c).lower(): str(t).lower() for c, t in rows}

    def meta_types(self) -> dict[str, str]:
        return {k: "STRING" for k in ("id", "name", "short", "text")} | {"ts": "DATETIME", "int": "INT64",
                                                                          "num": "FLOAT64"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INT64", "string": "STRING", "decimal": "NUMERIC", "date": "DATE"}
