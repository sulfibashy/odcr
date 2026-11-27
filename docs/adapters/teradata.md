# Teradata Vantage

Teradata Vantage; LDAP, Kerberos, JWT and browser single sign-on.

| | |
| --- | --- |
| Adapter name | `teradata` (aliases: `vantage`) |
| Runs on | on-premise, VantageCloud on AWS, Azure, GCP |
| Install | `pip install odcr-teradata` |
| Python driver | `teradatasql` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_TERADATA`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-teradata
odcr init my_contracts --adapter teradata
cd my_contracts
```

The generated project is also in the repository: [`examples/teradata`](https://github.com/sulfibashy/odcr/tree/main/examples/teradata).

## Connection

```yaml
connections:
  main:
    type: teradata
    host: ${TERADATA_HOST}
    user: ${TERADATA_USER}
    password: ${TERADATA_PASSWORD:-}
    database: ${TERADATA_DATABASE:-}
    logmech: ${TERADATA_LOGMECH:-TD2}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- Meta tables are created in the default database with the prefix odcr_meta_.
- Single sign-on without a password: logmech: BROWSER (Entra ID, Okta) or KRB5.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
