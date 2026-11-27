# MySQL / MariaDB

MySQL, MariaDB and MySQL-compatible databases.

| | |
| --- | --- |
| Adapter name | `mysql` (aliases: `mariadb`, `aurora-mysql`, `azure-mysql`, `cloudsql-mysql`, `tidb`) |
| Runs on | on-premise, AWS RDS/Aurora, Azure, GCP Cloud SQL |
| Install | `pip install odcr-mysql` |
| Python driver | `pymysql` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr-mysql
odcr init my_contracts --adapter mysql
cd my_contracts
```

The generated project is also in the repository: [`examples/mysql`](https://github.com/sulfibashy/odcr/tree/main/examples/mysql).

## Connection

```yaml
connections:
  main:
    type: mysql
    host: ${MYSQL_HOST:-localhost}
    port: ${MYSQL_PORT:-3306}
    database: ${MYSQL_DATABASE:-odcr}
    user: ${MYSQL_USER:-root}
    password: ${MYSQL_PASSWORD:-}
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
