# Amazon Redshift

Redshift provisioned and Serverless (password or IAM).

| | |
| --- | --- |
| Adapter name | `redshift` (aliases: none) |
| Runs on | AWS |
| Install | `pip install "odcr[redshift]"` |
| Python driver | `redshift_connector` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_REDSHIFT`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install "odcr[redshift]"
odcr init my_contracts --adapter redshift
cd my_contracts
```

The generated project is also in the repository: [`examples/redshift`](https://github.com/sulfibashy/odcr/tree/main/examples/redshift).

## Connection

```yaml
connections:
  main:
    type: redshift
    host: ${REDSHIFT_HOST}
    port: 5439
    database: ${REDSHIFT_DATABASE:-dev}
    user: ${REDSHIFT_USER}
    password: ${REDSHIFT_PASSWORD}
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
