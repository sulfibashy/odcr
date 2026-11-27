# Amazon Athena

Athena over the Glue Data Catalog; Iceberg meta tables in S3.

| | |
| --- | --- |
| Adapter name | `athena` (aliases: none) |
| Runs on | AWS |
| Install | `pip install odcr-athena` |
| Python driver | `pyathena` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_ATHENA`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-athena
odcr init my_contracts --adapter athena
cd my_contracts
```

The generated project is also in the repository: [`examples/athena`](https://github.com/sulfibashy/odcr/tree/main/examples/athena).

## Connection

```yaml
connections:
  main:
    type: athena
    region_name: ${AWS_REGION:-eu-north-1}
    s3_staging_dir: ${ATHENA_S3_STAGING_DIR}
    schema: ${ATHENA_DATABASE:-default}
    work_group: ${ATHENA_WORKGROUP:-primary}
    meta_location: ${ATHENA_META_LOCATION}
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
