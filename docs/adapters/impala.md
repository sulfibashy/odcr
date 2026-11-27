# Apache Impala

Impala daemons; LDAP, Kerberos or JWT.

| | |
| --- | --- |
| Adapter name | `impala` (aliases: none) |
| Runs on | Cloudera CDP / CDH, on-premise |
| Install | `pip install odcr-impala` |
| Python driver | `impala` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_IMPALA`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-impala
odcr init my_contracts --adapter impala
cd my_contracts
```

The generated project is also in the repository: [`examples/impala`](https://github.com/sulfibashy/odcr/tree/main/examples/impala).

## Connection

```yaml
connections:
  main:
    type: impala
    host: ${IMPALA_HOST:-localhost}
    port: ${IMPALA_PORT:-21050}
    database: ${IMPALA_DATABASE:-default}
    auth: ${IMPALA_AUTH:-NOSASL}
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
