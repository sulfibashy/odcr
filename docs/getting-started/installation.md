# Installation

odcr is a pure-Python package (Python 3.10–3.13). It runs anywhere Python runs: Windows, macOS, Linux and
Unix servers (AIX, Solaris and others through the database drivers available there), containers, Kubernetes,
Databricks clusters, Azure Functions and AWS Lambda. The core depends only on PyYAML; each platform adds
its own driver through an *extra*.

## Choose your adapters

```bash
pip install "odcr[postgres]"                  # one platform
pip install "odcr[snowflake,databricks]"      # several
pip install "odcr[all]"                       # every driver
odcr adapters                                 # what is supported and what is installed
```

| Extra | Platforms |
| --- | --- |
| `duckdb`, `files` | DuckDB; Parquet / CSV / JSON in local folders, ADLS Gen2, Blob, S3, GCS |
| *(none)* | SQLite |
| `postgres` | PostgreSQL, Aurora / RDS, Azure Database for PostgreSQL, Cloud SQL, AlloyDB |
| `mysql` | MySQL, MariaDB, Aurora / RDS, Azure Database for MySQL, Cloud SQL |
| `sqlserver` | SQL Server, Azure SQL Database / Managed Instance, Synapse, Fabric Warehouse |
| `oracle` | Oracle Database, Autonomous Database |
| `db2` | IBM Db2 LUW, Db2 on Cloud, Db2 Warehouse |
| `trino` | Trino, Starburst, Presto |
| `snowflake` | Snowflake |
| `databricks` | Databricks on Azure, AWS and GCP |
| `bigquery` | Google BigQuery |
| `redshift` | Amazon Redshift |
| `athena` | Amazon Athena |
| `mongodb` | MongoDB, Atlas, Amazon DocumentDB, Cosmos DB for MongoDB |
| `cosmosdb` | Azure Cosmos DB for NoSQL |
| `lint` | the official Data Contract CLI, for extra contract linting |

## Per operating system

=== "Linux / Unix"

    ```bash
    python3 -m venv /opt/odcr/venv
    /opt/odcr/venv/bin/pip install "odcr[postgres]"
    /opt/odcr/venv/bin/odcr --version
    ```

    SQL Server via ODBC needs the [Microsoft ODBC Driver 18](https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)
    (`client: pyodbc`), or use the pure-Python client with `client: pytds`.

=== "Windows"

    ```powershell
    py -m venv C:\odcr\venv
    C:\odcr\venv\Scripts\pip install "odcr[sqlserver]"
    C:\odcr\venv\Scripts\odcr --version
    ```

    The ODBC Driver 18 for SQL Server is usually already installed; Entra ID (`authentication:
    ActiveDirectoryIntegrated`) works with your Windows login.

=== "macOS"

    ```bash
    brew install python@3.12
    python3 -m venv ~/.odcr && ~/.odcr/bin/pip install "odcr[snowflake]"
    ```

=== "pipx (CLI only)"

    ```bash
    pipx install "odcr[postgres]"
    ```

## Servers without internet access

Build a wheelhouse on a machine with access, copy it over, and install offline:

```bash
pip download "odcr[postgres,sqlserver]" -d wheelhouse --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12
pip install --no-index --find-links wheelhouse "odcr[postgres,sqlserver]"
```

## Behind a corporate proxy or with a private CA

```bash
pip install --proxy http://proxy.example.com:8080 --cert /etc/ssl/certs/corporate-ca.pem "odcr[all]"
```

At run time, see [Security](../security.md): every connection verifies TLS certificates, and a corporate CA
bundle can be configured for notifications and cloud storage.

## Docker

```bash
docker build -t odcr --build-arg EXTRAS=postgres,sqlserver https://github.com/sulfibashy/odcr.git
docker run --rm -v "$PWD:/work" -w /work --env-file .env odcr run --contract-id orders
```

## Databricks, Azure Functions, AWS Lambda

`%pip install "odcr[databricks]"` in a notebook or as a cluster / job library; add `odcr[...]` to
`requirements.txt` for Functions and Lambda. Call the [Python API](../reference/python-api.md).
