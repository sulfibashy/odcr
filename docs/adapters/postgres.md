# PostgreSQL

PostgreSQL and PostgreSQL-compatible databases.

| | |
| --- | --- |
| Adapter name | `postgres` (aliases: `postgresql`, `aurora-postgres`, `azure-postgres`, `cloudsql-postgres`, `alloydb`, `supabase`, `neon`, `greenplum`, `cockroachdb`, `yugabytedb`, `timescaledb`, `citus`) |
| Runs on | on-premise, AWS RDS/Aurora, Azure, GCP Cloud SQL/AlloyDB |
| Install | `pip install odcr-postgres` |
| Python driver | `psycopg` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr-postgres
odcr init my_contracts --adapter postgres
cd my_contracts
```

The generated project is also in the repository: [`examples/postgres`](https://github.com/sulfibashy/odcr/tree/main/examples/postgres).

## Connection

```yaml
connections:
  main:
    type: postgres
    host: ${PGHOST:-localhost}
    port: ${PGPORT:-5432}
    database: ${PGDATABASE:-postgres}
    user: ${PGUSER:-postgres}
    password: ${PGPASSWORD:-}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- Also Greenplum, CockroachDB, YugabyteDB, TimescaleDB and Citus (PostgreSQL wire protocol).

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
