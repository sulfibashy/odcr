# Apache Hive / Spark SQL

HiveServer2 and the Spark Thrift server; LDAP or Kerberos.

| | |
| --- | --- |
| Adapter name | `hive` (aliases: `spark`, `spark-thrift`, `hiveserver2`, `emr`, `dataproc`, `hdinsight`, `cloudera`) |
| Runs on | on-premise Hadoop, Cloudera CDP, Amazon EMR, Google Dataproc, Azure HDInsight |
| Install | `pip install odcr-hive` |
| Python driver | `pyhive` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_HIVE`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-hive
odcr init my_contracts --adapter hive
cd my_contracts
```

The generated project is also in the repository: [`examples/hive`](https://github.com/sulfibashy/odcr/tree/main/examples/hive).

## Connection

```yaml
connections:
  main:
    type: hive
    host: ${HIVE_HOST:-localhost}
    port: ${HIVE_PORT:-10000}
    database: ${HIVE_DATABASE:-default}
    user: ${HIVE_USER:-}
    auth: ${HIVE_AUTH:-NONE}
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
