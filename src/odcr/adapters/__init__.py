"""Adapter registry: every supported platform, its install extra, connection template and test status.

`odcr adapters` prints this table; `odcr init --adapter <name>` uses the connection templates.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from .base import Adapter, UnsupportedCheck, type_matches


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    title: str
    cls: str  # "module:Class" inside odcr.adapters
    category: str  # embedded | on-premise | cloud | document | streaming
    clouds: str
    extra: str | None  # pip extra: pip install "odcr[<extra>]"; None = no extra needed
    driver: str  # import name of the driver
    tested: str  # "ci" = end-to-end in CI on every push; "credentials" = end-to-end when credentials are set
    description: str
    connection: dict[str, Any]
    aliases: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)
    where_example: str = "load_id = '{batch_id}'"

    @property
    def package(self) -> str:
        """The PyPI package to install: odcr-<extra> (same as odcr[<extra>]), or odcr itself."""
        return f"odcr-{self.extra}" if self.extra else "odcr"

    @property
    def install(self) -> str:
        return f"pip install {self.package}"


ADAPTERS: dict[str, AdapterInfo] = {a.name: a for a in [
    AdapterInfo("duckdb", "DuckDB", "duckdb:DuckDBAdapter", "embedded", "local, MotherDuck", "duckdb", "duckdb",
                "ci", "Embedded analytics database; also checks Parquet/CSV/JSON files directly.",
                {"type": "duckdb", "path": "${DUCKDB_PATH:-odcr.duckdb}"},
                notes=["Check files before loading: physicalName: \"read_parquet('landing/orders/*.parquet')\""]),
    AdapterInfo("files", "Files: ADLS, S3, GCS, local", "files:FilesAdapter", "embedded",
                "local, network shares, Azure ADLS Gen2/Blob, AWS S3, GCP GCS, MinIO", "files", "duckdb", "ci",
                "Checks Parquet, CSV and JSON files where they land, before loading (DuckDB engine).",
                {"type": "files", "storage": "${ODCR_STORAGE:-local}", "account_name": "${AZURE_STORAGE_ACCOUNT:-}",
                 "meta_path": "${ODCR_META_PATH:-odcr_meta.duckdb}"},
                aliases=("adls", "azure-storage", "s3", "gcs", "landing", "parquet", "csv", "delta", "iceberg",
                         "onelake"),
                notes=["physicalName is a path or glob: abfss://container@account.dfs.core.windows.net/orders/*.parquet",
                       "Delta Lake and Iceberg tables in storage: physicalName: \"delta_scan('abfss://...')\" or "
                       "\"iceberg_scan('s3://...')\".",
                       "Authentication: credential chain (Managed Identity, az login, AWS profile) by default; "
                       "service principal or keys via environment variables."],
                where_example="load_id = '{batch_id}'"),
    AdapterInfo("sqlite", "SQLite", "sqlite:SQLiteAdapter", "embedded", "local", None, "sqlite3", "ci",
                "Built into Python; ideal for trying odcr and for unit tests.",
                {"type": "sqlite", "path": "${SQLITE_PATH:-odcr.sqlite}"},
                notes=["No schemas: meta tables are prefixed (odcr_meta_validation_runs, ...)."]),
    AdapterInfo("postgres", "PostgreSQL", "postgres:PostgresAdapter", "on-premise",
                "on-premise, AWS RDS/Aurora, Azure, GCP Cloud SQL/AlloyDB", "postgres", "psycopg", "ci",
                "PostgreSQL and PostgreSQL-compatible databases.",
                {"type": "postgres", "host": "${PGHOST:-localhost}", "port": "${PGPORT:-5432}",
                 "database": "${PGDATABASE:-postgres}", "user": "${PGUSER:-postgres}", "password": "${PGPASSWORD:-}"},
                aliases=("postgresql", "aurora-postgres", "azure-postgres", "cloudsql-postgres", "alloydb",
                         "supabase", "neon", "greenplum", "cockroachdb", "yugabytedb", "timescaledb", "citus"),
                notes=["Also Greenplum, CockroachDB, YugabyteDB, TimescaleDB and Citus (PostgreSQL wire protocol)."]),
    AdapterInfo("mysql", "MySQL / MariaDB", "mysql:MySQLAdapter", "on-premise",
                "on-premise, AWS RDS/Aurora, Azure, GCP Cloud SQL", "mysql", "pymysql", "ci",
                "MySQL, MariaDB and MySQL-compatible databases.",
                {"type": "mysql", "host": "${MYSQL_HOST:-localhost}", "port": "${MYSQL_PORT:-3306}",
                 "database": "${MYSQL_DATABASE:-odcr}", "user": "${MYSQL_USER:-root}",
                 "password": "${MYSQL_PASSWORD:-}"},
                aliases=("mariadb", "aurora-mysql", "azure-mysql", "cloudsql-mysql", "tidb", "singlestore",
                         "planetscale"),
                notes=["Also TiDB, SingleStore and PlanetScale (MySQL wire protocol)."]),
    AdapterInfo("sqlserver", "SQL Server / Azure SQL", "sqlserver:SQLServerAdapter", "on-premise",
                "on-premise, Azure SQL Database, Azure SQL Managed Instance, AWS RDS", "sqlserver", "pyodbc", "ci",
                "Microsoft SQL Server and Azure SQL. Clients: pyodbc (ODBC Driver 18, Entra ID) or pytds.",
                {"type": "sqlserver", "host": "${MSSQL_HOST:-localhost}", "port": "${MSSQL_PORT:-1433}",
                 "database": "${MSSQL_DATABASE:-master}", "user": "${MSSQL_USER:-sa}",
                 "password": "${MSSQL_PASSWORD:-}", "client": "pyodbc", "encrypt": "yes"},
                aliases=("mssql", "azuresql", "azure-sql", "sql-managed-instance"),
                notes=["Entra ID: set authentication: ActiveDirectoryMsi (or ActiveDirectoryInteractive) and "
                       "leave user/password empty.", "No ODBC driver available? Set client: pytds.",
                       "TLS is on and the server certificate is verified (encrypt: yes). For a private CA, install "
                       "it in the OS trust store; trust_server_certificate: true is for local development only."]),
    AdapterInfo("synapse", "Azure Synapse Analytics", "sqlserver:SynapseAdapter", "cloud", "Azure", "synapse",
                "pyodbc", "credentials", "Dedicated SQL pools; meta tables are created as HEAP tables.",
                {"type": "synapse", "host": "${SYNAPSE_HOST}", "port": 1433, "database": "${SYNAPSE_DATABASE}",
                 "authentication": "ActiveDirectoryInteractive", "user": "${SYNAPSE_USER:-}"}),
    AdapterInfo("fabric", "Microsoft Fabric Warehouse", "sqlserver:FabricWarehouseAdapter", "cloud", "Azure",
                "fabric", "pyodbc", "credentials", "Fabric Warehouse and SQL analytics endpoints.",
                {"type": "fabric", "host": "${FABRIC_SQL_ENDPOINT}", "port": 1433, "database": "${FABRIC_WAREHOUSE}",
                 "authentication": "ActiveDirectoryInteractive", "user": "${FABRIC_USER:-}"}),
    AdapterInfo("oracle", "Oracle Database", "oracle:OracleAdapter", "on-premise",
                "on-premise, Oracle Cloud (Autonomous), AWS RDS", "oracle", "oracledb", "ci",
                "Oracle Database 19c+ (thin mode, no Oracle Client needed).",
                {"type": "oracle", "host": "${ORACLE_HOST:-localhost}", "port": "${ORACLE_PORT:-1521}",
                 "service_name": "${ORACLE_SERVICE:-FREEPDB1}", "user": "${ORACLE_USER}",
                 "password": "${ORACLE_PASSWORD}"},
                notes=["Meta tables are created in the current schema with the prefix odcr_meta_."]),
    AdapterInfo("db2", "IBM Db2", "db2:Db2Adapter", "on-premise", "on-premise, IBM Cloud", "db2", "ibm_db",
                "credentials", "IBM Db2 LUW, Db2 on Cloud and Db2 Warehouse.",
                {"type": "db2", "host": "${DB2_HOST:-localhost}", "port": "${DB2_PORT:-50000}",
                 "database": "${DB2_DATABASE}", "user": "${DB2_USER}", "password": "${DB2_PASSWORD}"}),
    AdapterInfo("trino", "Trino / Starburst / Presto", "trino:TrinoAdapter", "on-premise",
                "on-premise, Starburst Galaxy, AWS EMR", "trino", "trino", "ci",
                "Query engine over Hive, Iceberg, Delta Lake, Kafka and more.",
                {"type": "trino", "host": "${TRINO_HOST:-localhost}", "port": "${TRINO_PORT:-8080}",
                 "user": "${TRINO_USER:-odcr}", "catalog": "${TRINO_CATALOG:-hive}", "schema": "${TRINO_SCHEMA:-default}"},
                aliases=("starburst", "presto")),
    AdapterInfo("clickhouse", "ClickHouse", "clickhouse:ClickHouseAdapter", "on-premise",
                "on-premise, ClickHouse Cloud, Altinity, Aiven; embedded with chDB", "clickhouse",
                "clickhouse_connect", "ci", "ClickHouse over HTTP(S); MergeTree meta tables.",
                {"type": "clickhouse", "host": "${CLICKHOUSE_HOST:-localhost}", "port": "${CLICKHOUSE_PORT:-8123}",
                 "database": "${CLICKHOUSE_DATABASE:-default}", "user": "${CLICKHOUSE_USER:-default}",
                 "password": "${CLICKHOUSE_PASSWORD:-}"},
                aliases=("clickhouse-cloud", "chdb"),
                notes=["ClickHouse Cloud: port 8443 (TLS is switched on automatically).",
                       "No server: client: chdb and path: odcr.chdb (pip install chdb)."]),
    AdapterInfo("vertica", "Vertica", "vertica:VerticaAdapter", "on-premise", "on-premise, AWS, Azure, GCP (Eon mode)",
                "vertica", "vertica_python", "credentials", "OpenText Vertica; TLS, OAuth and Kerberos.",
                {"type": "vertica", "host": "${VERTICA_HOST:-localhost}", "port": "${VERTICA_PORT:-5433}",
                 "database": "${VERTICA_DATABASE}", "user": "${VERTICA_USER}", "password": "${VERTICA_PASSWORD:-}",
                 "tlsmode": "${VERTICA_TLSMODE:-prefer}"}),
    AdapterInfo("teradata", "Teradata Vantage", "teradata:TeradataAdapter", "on-premise",
                "on-premise, VantageCloud on AWS, Azure, GCP", "teradata", "teradatasql", "credentials",
                "Teradata Vantage; LDAP, Kerberos, JWT and browser single sign-on.",
                {"type": "teradata", "host": "${TERADATA_HOST}", "user": "${TERADATA_USER}",
                 "password": "${TERADATA_PASSWORD:-}", "database": "${TERADATA_DATABASE:-}",
                 "logmech": "${TERADATA_LOGMECH:-TD2}"},
                aliases=("vantage",),
                notes=["Meta tables are created in the default database with the prefix odcr_meta_.",
                       "Single sign-on without a password: logmech: BROWSER (Entra ID, Okta) or KRB5."]),
    AdapterInfo("saphana", "SAP HANA", "saphana:SAPHanaAdapter", "on-premise",
                "SAP HANA Cloud, on-premise, SAP Datasphere", "saphana", "hdbcli", "credentials",
                "SAP HANA Cloud and on-premise; TLS by default.",
                {"type": "saphana", "host": "${HANA_HOST}", "port": "${HANA_PORT:-443}", "user": "${HANA_USER}",
                 "password": "${HANA_PASSWORD:-}", "schema": "${HANA_SCHEMA:-}"},
                aliases=("hana", "sap-hana", "datasphere")),
    AdapterInfo("hive", "Apache Hive / Spark SQL", "hive:HiveAdapter", "on-premise",
                "on-premise Hadoop, Cloudera CDP, Amazon EMR, Google Dataproc, Azure HDInsight", "hive", "pyhive",
                "credentials", "HiveServer2 and the Spark Thrift server; LDAP or Kerberos.",
                {"type": "hive", "host": "${HIVE_HOST:-localhost}", "port": "${HIVE_PORT:-10000}",
                 "database": "${HIVE_DATABASE:-default}", "user": "${HIVE_USER:-}", "auth": "${HIVE_AUTH:-NONE}"},
                aliases=("spark", "spark-thrift", "hiveserver2", "emr", "dataproc", "hdinsight", "cloudera")),
    AdapterInfo("impala", "Apache Impala", "hive:ImpalaAdapter", "on-premise", "Cloudera CDP / CDH, on-premise",
                "impala", "impala", "credentials", "Impala daemons; LDAP, Kerberos or JWT.",
                {"type": "impala", "host": "${IMPALA_HOST:-localhost}", "port": "${IMPALA_PORT:-21050}",
                 "database": "${IMPALA_DATABASE:-default}", "auth": "${IMPALA_AUTH:-NOSASL}"}),
    AdapterInfo("snowflake", "Snowflake", "snowflake:SnowflakeAdapter", "cloud", "AWS, Azure, GCP", "snowflake",
                "snowflake.connector", "credentials", "Snowflake data cloud (password, key-pair, OAuth, SSO).",
                {"type": "snowflake", "account": "${SNOWFLAKE_ACCOUNT}", "user": "${SNOWFLAKE_USER}",
                 "password": "${SNOWFLAKE_PASSWORD:-}", "private_key_file": "${SNOWFLAKE_PRIVATE_KEY_FILE:-}",
                 "warehouse": "${SNOWFLAKE_WAREHOUSE}", "database": "${SNOWFLAKE_DATABASE}",
                 "schema": "${SNOWFLAKE_SCHEMA:-PUBLIC}", "role": "${SNOWFLAKE_ROLE:-}"}),
    AdapterInfo("databricks", "Databricks", "databricks:DatabricksAdapter", "cloud", "Azure, AWS, GCP",
                "databricks", "databricks.sql", "credentials",
                "Databricks SQL warehouses and clusters; Unity Catalog and hive_metastore; Delta meta tables.",
                {"type": "databricks", "host": "${DATABRICKS_HOST}", "http_path": "${DATABRICKS_HTTP_PATH}",
                 "access_token": "${DATABRICKS_TOKEN}", "catalog": "${DATABRICKS_CATALOG:-main}",
                 "schema": "${DATABRICKS_SCHEMA:-default}"},
                aliases=("azure-databricks", "aws-databricks", "gcp-databricks")),
    AdapterInfo("bigquery", "Google BigQuery", "bigquery:BigQueryAdapter", "cloud", "GCP", "bigquery",
                "google.cloud.bigquery", "credentials", "BigQuery with Application Default Credentials or a key file.",
                {"type": "bigquery", "project": "${GCP_PROJECT}", "dataset": "${BIGQUERY_DATASET}",
                 "location": "${BIGQUERY_LOCATION:-EU}", "credentials_path": "${GOOGLE_APPLICATION_CREDENTIALS:-}"}),
    AdapterInfo("redshift", "Amazon Redshift", "redshift:RedshiftAdapter", "cloud", "AWS", "redshift",
                "redshift_connector", "credentials", "Redshift provisioned and Serverless (password or IAM).",
                {"type": "redshift", "host": "${REDSHIFT_HOST}", "port": 5439, "database": "${REDSHIFT_DATABASE:-dev}",
                 "user": "${REDSHIFT_USER}", "password": "${REDSHIFT_PASSWORD}"}),
    AdapterInfo("athena", "Amazon Athena", "athena:AthenaAdapter", "cloud", "AWS", "athena", "pyathena",
                "credentials", "Athena over the Glue Data Catalog; Iceberg meta tables in S3.",
                {"type": "athena", "region_name": "${AWS_REGION:-eu-north-1}",
                 "s3_staging_dir": "${ATHENA_S3_STAGING_DIR}", "schema": "${ATHENA_DATABASE:-default}",
                 "work_group": "${ATHENA_WORKGROUP:-primary}", "meta_location": "${ATHENA_META_LOCATION}"}),
    AdapterInfo("kafka", "Apache Kafka", "kafka:KafkaAdapter", "streaming",
                "on-premise, Confluent Cloud, Amazon MSK, Aiven, Redpanda, IBM Event Streams", "kafka",
                "confluent_kafka", "ci", "Topics as objects: each run checks the messages since the last run.",
                {"type": "kafka", "bootstrap_servers": "${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}",
                 "group_id": "${KAFKA_GROUP_ID:-odcr}", "start": "earliest",
                 "meta_path": "${ODCR_META_PATH:-odcr_meta.duckdb}"},
                aliases=("confluent", "msk", "redpanda", "aiven-kafka", "event-streams"),
                notes=["physicalName is the topic; message values are JSON objects.",
                       "TLS / SASL: security_protocol, sasl_mechanism, ssl_ca_location, or any librdkafka "
                       "setting under config:.",
                       "mock: true uses an in-process broker (for tests: messages are not kept between commands)."]),
    AdapterInfo("eventhubs", "Azure Event Hubs", "kafka:EventHubsAdapter", "streaming", "Azure", "eventhubs",
                "confluent_kafka", "credentials", "Event hubs as objects, over the Kafka endpoint; Entra ID auth.",
                {"type": "eventhubs", "namespace": "${EVENTHUBS_NAMESPACE}",
                 "consumer_group": "${EVENTHUBS_CONSUMER_GROUP:-odcr}", "start": "earliest",
                 "meta_path": "${ODCR_META_PATH:-odcr_meta.duckdb}"},
                aliases=("event-hubs", "azure-event-hubs", "eventhub"),
                notes=["physicalName is the event hub. Create a consumer group for odcr (e.g. odcr) so it does "
                       "not share offsets with your consumers.",
                       "Authentication: Entra ID (managed identity, workload identity, az login) by default; "
                       "the identity needs the Azure Event Hubs Data Receiver role. Or connection_string."]),
    AdapterInfo("mongodb", "MongoDB", "mongodb:MongoDBAdapter", "document",
                "on-premise, MongoDB Atlas, Amazon DocumentDB, Azure Cosmos DB for MongoDB", "mongodb", "pymongo", "ci",
                "Collections as objects; JSON batch filters; custom rules with engine: mongodb.",
                {"type": "mongodb", "uri": "${MONGODB_URI:-mongodb://localhost:27017}",
                 "database": "${MONGODB_DATABASE:-odcr}"},
                aliases=("documentdb", "cosmos-mongo", "atlas"), where_example='{"load_id": "{batch_id}"}'),
    AdapterInfo("cosmosdb", "Azure Cosmos DB (NoSQL)", "cosmosdb:CosmosDBAdapter", "document", "Azure", "cosmosdb",
                "azure.cosmos", "credentials", "Containers as objects; Cosmos SQL conditions; key or Entra ID auth.",
                {"type": "cosmosdb", "endpoint": "${COSMOS_ENDPOINT}", "key": "${COSMOS_KEY:-}",
                 "database": "${COSMOS_DATABASE:-odcr}"},
                aliases=("cosmos",), where_example="c.load_id = '{batch_id}'"),
]}

_ALIASES = {alias: info.name for info in ADAPTERS.values() for alias in info.aliases}


def resolve(name: str) -> AdapterInfo:
    key = str(name).lower()
    key = _ALIASES.get(key, key)
    if key not in ADAPTERS:
        import difflib

        close = difflib.get_close_matches(key, list(ADAPTERS) + list(_ALIASES), n=1)
        hint = f" Did you mean '{_ALIASES.get(close[0], close[0])}'?" if close else ""
        raise ValueError(f"Unsupported adapter '{name}'.{hint} Run `odcr adapters` to list them "
                         f"({', '.join(sorted(ADAPTERS))}).")
    return ADAPTERS[key]


def adapter_class(name: str) -> type[Adapter]:
    info = resolve(name)
    module, cls = info.cls.split(":")
    return getattr(importlib.import_module(f"odcr.adapters.{module}"), cls)


def driver_installed(info: AdapterInfo) -> bool:
    try:
        importlib.import_module(info.driver)
        return True
    except Exception:  # noqa: BLE001
        return False


def get_adapter(options: dict[str, Any]) -> Adapter:
    opts = dict(options)
    kind = str(opts.pop("type", ""))
    return adapter_class(kind)(**opts)


__all__ = ["Adapter", "AdapterInfo", "ADAPTERS", "UnsupportedCheck", "adapter_class", "driver_installed",
           "get_adapter", "resolve", "type_matches"]
