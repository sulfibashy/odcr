# Installation

odcr is a pure-Python package (Python 3.10–3.13). It runs anywhere Python runs: Windows, macOS, Linux and
Unix servers (AIX, Solaris and others through the database drivers available there), containers, Kubernetes,
Databricks clusters, Azure Functions and AWS Lambda.

## Install the connector for your platform

Like `dbt-postgres` or `dbt-snowflake`, every platform has its own package. It installs odcr plus that
platform's driver — no brackets, no quotes:

```bash
pip install odcr-postgres                       # one platform
pip install odcr-snowflake odcr-databricks      # several
pip install odcr-all                            # every driver
odcr adapters                                   # what is supported and what is installed
```

| Package | Platforms |
| --- | --- |
| `odcr` | the core, plus SQLite (built into Python) |
| `odcr-duckdb` | DuckDB, MotherDuck |
| `odcr-files` | Parquet / CSV / JSON in local folders, network shares, ADLS Gen2, Azure Blob, S3, GCS, MinIO |
| `odcr-postgres` | PostgreSQL, Aurora / RDS, Azure Database for PostgreSQL, Cloud SQL, AlloyDB, Greenplum, CockroachDB, YugabyteDB, TimescaleDB |
| `odcr-mysql` | MySQL, MariaDB, Aurora / RDS, Azure Database for MySQL, Cloud SQL, TiDB, SingleStore |
| `odcr-sqlserver` | SQL Server, Azure SQL Database, Azure SQL Managed Instance |
| `odcr-synapse` | Azure Synapse Analytics (dedicated SQL pools) |
| `odcr-fabric` | Microsoft Fabric Warehouse |
| `odcr-oracle` | Oracle Database, Autonomous Database |
| `odcr-db2` | IBM Db2 LUW, Db2 on Cloud, Db2 Warehouse |
| `odcr-teradata` | Teradata Vantage, VantageCloud |
| `odcr-saphana` | SAP HANA Cloud, SAP HANA on-premise, SAP Datasphere |
| `odcr-vertica` | Vertica on-premise and Eon mode |
| `odcr-clickhouse` | ClickHouse, ClickHouse Cloud, Altinity, Aiven |
| `odcr-hive` | Apache Hive, Spark SQL Thrift server (Cloudera, EMR, Dataproc, HDInsight) |
| `odcr-impala` | Apache Impala (Cloudera) |
| `odcr-trino` | Trino, Starburst, Presto |
| `odcr-snowflake` | Snowflake |
| `odcr-databricks` | Databricks on Azure, AWS and GCP |
| `odcr-bigquery` | Google BigQuery |
| `odcr-redshift` | Amazon Redshift |
| `odcr-athena` | Amazon Athena |
| `odcr-mongodb` | MongoDB, Atlas, Amazon DocumentDB, Cosmos DB for MongoDB |
| `odcr-cosmosdb` | Azure Cosmos DB for NoSQL |
| `odcr-kafka` | Apache Kafka, Confluent, Amazon MSK, Aiven, Redpanda, IBM Event Streams |
| `odcr-eventhubs` | Azure Event Hubs (Kafka endpoint, Entra ID) |
| `odcr-all` | every driver above |

The equivalent "extras" form also works: `pip install "odcr[postgres]"`. In zsh (the macOS default shell) the
brackets must be quoted; the `odcr-<platform>` packages avoid that.

Optional features: `pip install "odcr[keyring]"` (OS keychain secrets), `"odcr[microsoft365]"` (email via
Microsoft Graph), `"odcr[aws-ses]"` (email via Amazon SES), `"odcr[lint]"` (Data Contract CLI linting).

## Per operating system

=== "Linux / Unix"

    ```bash
    python3 -m venv /opt/odcr/venv
    /opt/odcr/venv/bin/pip install odcr-postgres
    /opt/odcr/venv/bin/odcr --version
    ```

    SQL Server via ODBC needs the [Microsoft ODBC Driver 18](https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)
    (`client: pyodbc`), or use the pure-Python client with `client: pytds`.

=== "Windows"

    ```powershell
    py -m venv C:\odcr\venv
    C:\odcr\venv\Scripts\pip install odcr-sqlserver
    C:\odcr\venv\Scripts\odcr --version
    ```

    The ODBC Driver 18 for SQL Server is usually already installed; Entra ID (`authentication:
    ActiveDirectoryIntegrated`) works with your Windows login.

=== "macOS"

    ```bash
    brew install python@3.12
    python3 -m venv ~/.odcr && ~/.odcr/bin/pip install odcr-snowflake
    ```

=== "pipx (CLI only)"

    ```bash
    pipx install odcr-postgres
    ```

## Servers without internet access

Build a wheelhouse on a machine with access, copy it over, and install offline:

```bash
pip download odcr-postgres odcr-sqlserver -d wheelhouse --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12
pip install --no-index --find-links wheelhouse odcr-postgres odcr-sqlserver
```

## Behind a corporate proxy or with a private CA

```bash
pip install --proxy http://proxy.example.com:8080 --cert /etc/ssl/certs/corporate-ca.pem odcr-all
```

At run time, see [Security](../security.md): every connection verifies TLS certificates, and a corporate CA
bundle can be configured for notifications and cloud storage.

## Docker

```bash
docker build -t odcr --build-arg EXTRAS=postgres,sqlserver https://github.com/sulfibashy/odcr.git
docker run --rm -v "$PWD:/work" -w /work --env-file .env odcr run --contract-id orders
```

## Databricks, Azure Functions, AWS Lambda

`%pip install odcr-databricks` in a notebook or as a cluster / job library; add `odcr-<adapter>` to
`requirements.txt` for Functions and Lambda. Call the [Python API](../reference/python-api.md).
