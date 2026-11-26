# DuckDB

Embedded analytics database; also checks Parquet/CSV/JSON files directly.

| | |
| --- | --- |
| Adapter name | `duckdb` (aliases: none) |
| Runs on | local, MotherDuck |
| Install | `pip install "odcr[duckdb]"` |
| Python driver | `duckdb` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install "odcr[duckdb]"
odcr init my_contracts --adapter duckdb
cd my_contracts
```

The generated project is also in the repository: [`examples/duckdb`](https://github.com/sulfibashy/odcr/tree/main/examples/duckdb).

## Connection

```yaml
connections:
  main:
    type: duckdb
    path: ${DUCKDB_PATH:-odcr.duckdb}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- Check files before loading: physicalName: "read_parquet('landing/orders/*.parquet')"

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
