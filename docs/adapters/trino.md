# Trino / Starburst / Presto

Query engine over Hive, Iceberg, Delta Lake, Kafka and more.

| | |
| --- | --- |
| Adapter name | `trino` (aliases: `starburst`, `presto`) |
| Runs on | on-premise, Starburst Galaxy, AWS EMR |
| Install | `pip install "odcr[trino]"` |
| Python driver | `trino` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install "odcr[trino]"
odcr init my_contracts --adapter trino
cd my_contracts
```

The generated project is also in the repository: [`examples/trino`](https://github.com/sulfibashy/odcr/tree/main/examples/trino).

## Connection

```yaml
connections:
  main:
    type: trino
    host: ${TRINO_HOST:-localhost}
    port: ${TRINO_PORT:-8080}
    user: ${TRINO_USER:-odcr}
    catalog: ${TRINO_CATALOG:-hive}
    schema: ${TRINO_SCHEMA:-default}
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
