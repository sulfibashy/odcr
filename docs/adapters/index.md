# Adapters

One adapter per platform. Install only the extras you need: `pip install "odcr[snowflake,databricks]"`,
or everything with `pip install "odcr[all]"`. `odcr adapters` shows which drivers are installed.

| Platform | Adapter | Where | Install | End-to-end tests |
| --- | --- | --- | --- | --- |
| [DuckDB](duckdb.md) | `duckdb` | local, MotherDuck | `odcr[duckdb]` | CI |
| [Files: ADLS, S3, GCS, local](files.md) | `files` | local, network shares, Azure ADLS Gen2/Blob, AWS S3, GCP GCS, MinIO | `odcr[files]` | CI |
| [SQLite](sqlite.md) | `sqlite` | local | `odcr` | CI |
| [PostgreSQL](postgres.md) | `postgres` | on-premise, AWS RDS/Aurora, Azure, GCP Cloud SQL/AlloyDB | `odcr[postgres]` | CI |
| [MySQL / MariaDB](mysql.md) | `mysql` | on-premise, AWS RDS/Aurora, Azure, GCP Cloud SQL | `odcr[mysql]` | CI |
| [SQL Server / Azure SQL](sqlserver.md) | `sqlserver` | on-premise, Azure SQL Database, Azure SQL Managed Instance, AWS RDS | `odcr[sqlserver]` | CI |
| [Azure Synapse Analytics](synapse.md) | `synapse` | Azure | `odcr[sqlserver]` | with credentials |
| [Microsoft Fabric Warehouse](fabric.md) | `fabric` | Azure | `odcr[sqlserver]` | with credentials |
| [Oracle Database](oracle.md) | `oracle` | on-premise, Oracle Cloud (Autonomous), AWS RDS | `odcr[oracle]` | CI |
| [IBM Db2](db2.md) | `db2` | on-premise, IBM Cloud | `odcr[db2]` | with credentials |
| [Trino / Starburst / Presto](trino.md) | `trino` | on-premise, Starburst Galaxy, AWS EMR | `odcr[trino]` | CI |
| [Snowflake](snowflake.md) | `snowflake` | AWS, Azure, GCP | `odcr[snowflake]` | with credentials |
| [Databricks](databricks.md) | `databricks` | Azure, AWS, GCP | `odcr[databricks]` | with credentials |
| [Google BigQuery](bigquery.md) | `bigquery` | GCP | `odcr[bigquery]` | with credentials |
| [Amazon Redshift](redshift.md) | `redshift` | AWS | `odcr[redshift]` | with credentials |
| [Amazon Athena](athena.md) | `athena` | AWS | `odcr[athena]` | with credentials |
| [MongoDB](mongodb.md) | `mongodb` | on-premise, MongoDB Atlas, Amazon DocumentDB, Azure Cosmos DB for MongoDB | `odcr[mongodb]` | CI |
| [Azure Cosmos DB (NoSQL)](cosmosdb.md) | `cosmosdb` | Azure | `odcr[cosmosdb]` | with credentials |

**ETL and orchestration tools** (Informatica, Ab Initio, Azure Data Factory, SSIS, Airflow, Databricks Workflows)
are not adapters: they call odcr when data lands. See [Integrations](../integrations/index.md).

Missing a platform? [Adding an adapter](../contributing/adding-an-adapter.md) takes about 50 lines.
