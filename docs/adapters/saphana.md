# SAP HANA

SAP HANA Cloud and on-premise; TLS by default.

| | |
| --- | --- |
| Adapter name | `saphana` (aliases: `hana`, `sap-hana`, `datasphere`) |
| Runs on | SAP HANA Cloud, on-premise, SAP Datasphere |
| Install | `pip install odcr-saphana` |
| Python driver | `hdbcli` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_SAPHANA`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-saphana
odcr init my_contracts --adapter saphana
cd my_contracts
```

The generated project is also in the repository: [`examples/saphana`](https://github.com/sulfibashy/odcr/tree/main/examples/saphana).

## Connection

```yaml
connections:
  main:
    type: saphana
    host: ${HANA_HOST}
    port: ${HANA_PORT:-443}
    user: ${HANA_USER}
    password: ${HANA_PASSWORD:-}
    schema: ${HANA_SCHEMA:-}
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
