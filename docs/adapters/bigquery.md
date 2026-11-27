# Google BigQuery

BigQuery with Application Default Credentials or a key file.

| | |
| --- | --- |
| Adapter name | `bigquery` (aliases: none) |
| Runs on | GCP |
| Install | `pip install odcr-bigquery` |
| Python driver | `google.cloud.bigquery` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_BIGQUERY`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-bigquery
odcr init my_contracts --adapter bigquery
cd my_contracts
```

The generated project is also in the repository: [`examples/bigquery`](https://github.com/sulfibashy/odcr/tree/main/examples/bigquery).

## Connection

```yaml
connections:
  main:
    type: bigquery
    project: ${GCP_PROJECT}
    dataset: ${BIGQUERY_DATASET}
    location: ${BIGQUERY_LOCATION:-EU}
    credentials_path: ${GOOGLE_APPLICATION_CREDENTIALS:-}
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
