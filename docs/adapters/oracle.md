# Oracle Database

Oracle Database 19c+ (thin mode, no Oracle Client needed).

| | |
| --- | --- |
| Adapter name | `oracle` (aliases: none) |
| Runs on | on-premise, Oracle Cloud (Autonomous), AWS RDS |
| Install | `pip install odcr-oracle` |
| Python driver | `oracledb` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr-oracle
odcr init my_contracts --adapter oracle
cd my_contracts
```

The generated project is also in the repository: [`examples/oracle`](https://github.com/sulfibashy/odcr/tree/main/examples/oracle).

## Connection

```yaml
connections:
  main:
    type: oracle
    host: ${ORACLE_HOST:-localhost}
    port: ${ORACLE_PORT:-1521}
    service_name: ${ORACLE_SERVICE:-FREEPDB1}
    user: ${ORACLE_USER}
    password: ${ORACLE_PASSWORD}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- Meta tables are created in the current schema with the prefix odcr_meta_.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
