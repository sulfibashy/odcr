# IBM Db2

IBM Db2 LUW, Db2 on Cloud and Db2 Warehouse.

| | |
| --- | --- |
| Adapter name | `db2` (aliases: none) |
| Runs on | on-premise, IBM Cloud |
| Install | `pip install odcr-db2` |
| Python driver | `ibm_db` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_DB2`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-db2
odcr init my_contracts --adapter db2
cd my_contracts
```

The generated project is also in the repository: [`examples/db2`](https://github.com/sulfibashy/odcr/tree/main/examples/db2).

## Connection

```yaml
connections:
  main:
    type: db2
    host: ${DB2_HOST:-localhost}
    port: ${DB2_PORT:-50000}
    database: ${DB2_DATABASE}
    user: ${DB2_USER}
    password: ${DB2_PASSWORD}
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
