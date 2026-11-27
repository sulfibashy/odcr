# Azure Synapse Analytics

Dedicated SQL pools; meta tables are created as HEAP tables.

| | |
| --- | --- |
| Adapter name | `synapse` (aliases: none) |
| Runs on | Azure |
| Install | `pip install odcr-synapse` |
| Python driver | `pyodbc` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_SYNAPSE`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-synapse
odcr init my_contracts --adapter synapse
cd my_contracts
```

The generated project is also in the repository: [`examples/synapse`](https://github.com/sulfibashy/odcr/tree/main/examples/synapse).

## Connection

```yaml
connections:
  main:
    type: synapse
    host: ${SYNAPSE_HOST}
    port: 1433
    database: ${SYNAPSE_DATABASE}
    authentication: ActiveDirectoryInteractive
    user: ${SYNAPSE_USER:-}
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
