# Vertica

OpenText Vertica; TLS, OAuth and Kerberos.

| | |
| --- | --- |
| Adapter name | `vertica` (aliases: none) |
| Runs on | on-premise, AWS, Azure, GCP (Eon mode) |
| Install | `pip install odcr-vertica` |
| Python driver | `vertica_python` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_VERTICA`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-vertica
odcr init my_contracts --adapter vertica
cd my_contracts
```

The generated project is also in the repository: [`examples/vertica`](https://github.com/sulfibashy/odcr/tree/main/examples/vertica).

## Connection

```yaml
connections:
  main:
    type: vertica
    host: ${VERTICA_HOST:-localhost}
    port: ${VERTICA_PORT:-5433}
    database: ${VERTICA_DATABASE}
    user: ${VERTICA_USER}
    password: ${VERTICA_PASSWORD:-}
    tlsmode: ${VERTICA_TLSMODE:-prefer}
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
