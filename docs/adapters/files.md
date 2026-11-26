# Files: ADLS, S3, GCS, local

Checks Parquet, CSV and JSON files where they land, before loading (DuckDB engine).

| | |
| --- | --- |
| Adapter name | `files` (aliases: `adls`, `azure-storage`, `s3`, `gcs`, `landing`, `parquet`, `csv`) |
| Runs on | local, network shares, Azure ADLS Gen2/Blob, AWS S3, GCP GCS, MinIO |
| Install | `pip install "odcr[files]"` |
| Python driver | `duckdb` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install "odcr[files]"
odcr init my_contracts --adapter files
cd my_contracts
```

The generated project is also in the repository: [`examples/files`](https://github.com/sulfibashy/odcr/tree/main/examples/files).

## Connection

```yaml
connections:
  main:
    type: files
    storage: ${ODCR_STORAGE:-local}
    account_name: ${AZURE_STORAGE_ACCOUNT:-}
    meta_path: ${ODCR_META_PATH:-odcr_meta.duckdb}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- physicalName is a path or glob: abfss://container@account.dfs.core.windows.net/orders/*.parquet
- Authentication: credential chain (Managed Identity, az login, AWS profile) by default; service principal or keys via environment variables.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
