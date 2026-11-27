# MongoDB

Collections as objects; JSON batch filters; custom rules with engine: mongodb.

| | |
| --- | --- |
| Adapter name | `mongodb` (aliases: `documentdb`, `cosmos-mongo`, `atlas`) |
| Runs on | on-premise, MongoDB Atlas, Amazon DocumentDB, Azure Cosmos DB for MongoDB |
| Install | `pip install odcr-mongodb` |
| Python driver | `pymongo` |
| Batch filter example | `{"load_id": "{batch_id}"}` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr-mongodb
odcr init my_contracts --adapter mongodb
cd my_contracts
```

The generated project is also in the repository: [`examples/mongodb`](https://github.com/sulfibashy/odcr/tree/main/examples/mongodb).

## Connection

```yaml
connections:
  main:
    type: mongodb
    uri: ${MONGODB_URI:-mongodb://localhost:27017}
    database: ${MONGODB_DATABASE:-odcr}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- None.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where '{"load_id": "batch-001"}'
```
