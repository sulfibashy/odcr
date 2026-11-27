# ClickHouse

ClickHouse over HTTP(S); MergeTree meta tables.

| | |
| --- | --- |
| Adapter name | `clickhouse` (aliases: `clickhouse-cloud`, `chdb`) |
| Runs on | on-premise, ClickHouse Cloud, Altinity, Aiven; embedded with chDB |
| Install | `pip install odcr-clickhouse` |
| Python driver | `clickhouse_connect` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr-clickhouse
odcr init my_contracts --adapter clickhouse
cd my_contracts
```

The generated project is also in the repository: [`examples/clickhouse`](https://github.com/sulfibashy/odcr/tree/main/examples/clickhouse).

## Connection

```yaml
connections:
  main:
    type: clickhouse
    host: ${CLICKHOUSE_HOST:-localhost}
    port: ${CLICKHOUSE_PORT:-8123}
    database: ${CLICKHOUSE_DATABASE:-default}
    user: ${CLICKHOUSE_USER:-default}
    password: ${CLICKHOUSE_PASSWORD:-}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- ClickHouse Cloud: port 8443 (TLS is switched on automatically).
- No server: client: chdb and path: odcr.chdb (pip install chdb).

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
