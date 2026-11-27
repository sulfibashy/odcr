# Snowflake

Snowflake data cloud (password, key-pair, OAuth, SSO).

| | |
| --- | --- |
| Adapter name | `snowflake` (aliases: none) |
| Runs on | AWS, Azure, GCP |
| Install | `pip install odcr-snowflake` |
| Python driver | `snowflake.connector` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_SNOWFLAKE`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-snowflake
odcr init my_contracts --adapter snowflake
cd my_contracts
```

The generated project is also in the repository: [`examples/snowflake`](https://github.com/sulfibashy/odcr/tree/main/examples/snowflake).

## Connection

```yaml
connections:
  main:
    type: snowflake
    account: ${SNOWFLAKE_ACCOUNT}
    user: ${SNOWFLAKE_USER}
    password: ${SNOWFLAKE_PASSWORD:-}
    private_key_file: ${SNOWFLAKE_PRIVATE_KEY_FILE:-}
    warehouse: ${SNOWFLAKE_WAREHOUSE}
    database: ${SNOWFLAKE_DATABASE}
    schema: ${SNOWFLAKE_SCHEMA:-PUBLIC}
    role: ${SNOWFLAKE_ROLE:-}
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
