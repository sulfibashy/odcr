# Databricks

Databricks SQL warehouses and clusters; Unity Catalog and hive_metastore; Delta meta tables.

| | |
| --- | --- |
| Adapter name | `databricks` (aliases: `azure-databricks`, `aws-databricks`, `gcp-databricks`) |
| Runs on | Azure, AWS, GCP |
| Install | `pip install odcr-databricks` |
| Python driver | `databricks.sql` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_DATABRICKS`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-databricks
odcr init my_contracts --adapter databricks
cd my_contracts
```

The generated project is also in the repository: [`examples/databricks`](https://github.com/sulfibashy/odcr/tree/main/examples/databricks).

## Connection

```yaml
connections:
  main:
    type: databricks
    host: ${DATABRICKS_HOST}
    http_path: ${DATABRICKS_HTTP_PATH}
    access_token: ${DATABRICKS_TOKEN}
    catalog: ${DATABRICKS_CATALOG:-main}
    schema: ${DATABRICKS_SCHEMA:-default}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- None.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
