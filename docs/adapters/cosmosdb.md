# Azure Cosmos DB (NoSQL)

Containers as objects; Cosmos SQL conditions; key or Entra ID auth.

| | |
| --- | --- |
| Adapter name | `cosmosdb` (aliases: `cosmos`) |
| Runs on | Azure |
| Install | `pip install "odcr[cosmosdb]"` |
| Python driver | `azure.cosmos` |
| Batch filter example | `c.load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_COSMOSDB`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install "odcr[cosmosdb]"
odcr init my_contracts --adapter cosmosdb
cd my_contracts
```

The generated project is also in the repository: [`examples/cosmosdb`](https://github.com/sulfibashy/odcr/tree/main/examples/cosmosdb).

## Connection

```yaml
connections:
  main:
    type: cosmosdb
    endpoint: ${COSMOS_ENDPOINT}
    key: ${COSMOS_KEY:-}
    database: ${COSMOS_DATABASE:-odcr}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- None.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "c.load_id = 'batch-001'"
```
