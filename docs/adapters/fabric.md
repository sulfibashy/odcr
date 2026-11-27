# Microsoft Fabric Warehouse

Fabric Warehouse and SQL analytics endpoints.

| | |
| --- | --- |
| Adapter name | `fabric` (aliases: none) |
| Runs on | Azure |
| Install | `pip install odcr-fabric` |
| Python driver | `pyodbc` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_FABRIC`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-fabric
odcr init my_contracts --adapter fabric
cd my_contracts
```

The generated project is also in the repository: [`examples/fabric`](https://github.com/sulfibashy/odcr/tree/main/examples/fabric).

## Connection

```yaml
connections:
  main:
    type: fabric
    host: ${FABRIC_SQL_ENDPOINT}
    port: 1433
    database: ${FABRIC_WAREHOUSE}
    authentication: ActiveDirectoryInteractive
    user: ${FABRIC_USER:-}
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
