# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.2] - 2026-11-27

### Added
- One package per connector, like dbt adapters: `pip install odcr-postgres`, `odcr-snowflake`, `odcr-databricks`,
  `odcr-sqlserver`, `odcr-synapse`, `odcr-fabric`, `odcr-files`, `odcr-mongodb`, ... and `odcr-all`. No brackets or
  quotes needed (zsh on macOS treats `odcr[postgres]` as a pattern). `pip install "odcr[postgres]"` still works.
- `odcr adapters`, `odcr init` and every error message now show the `odcr-<platform>` package to install.

- 8 new adapters (26 in total), each with its own package and reference project:
  - **Streaming:** `odcr-kafka` (Apache Kafka, Confluent, MSK, Redpanda, Aiven) and `odcr-eventhubs` (Azure Event
    Hubs over its Kafka endpoint, with Entra ID — no stored secret). The topic is the object; each run checks the
    messages that arrived since the last run, then commits the offsets. `mock: true` runs an in-memory broker.
  - **Warehouses and on-premise:** `odcr-teradata`, `odcr-saphana`, `odcr-vertica`, `odcr-clickhouse`
    (also embedded through chDB).
  - **Hadoop:** `odcr-hive` (Hive and Spark SQL Thrift server) and `odcr-impala`.
- New aliases: Greenplum, CockroachDB, YugabyteDB, TimescaleDB, Citus (PostgreSQL); SingleStore, PlanetScale (MySQL);
  Delta Lake and Iceberg tables in storage through the files adapter (`delta_scan`, `iceberg_scan`).
- ClickHouse and Kafka run end-to-end in CI; Kafka also runs against the in-memory broker on every OS.

### Changed
- Synapse and Fabric have their own `synapse` and `fabric` extras.

## [0.2.1] - 2026-11-27

### Added
- `odcr destroy [folder]`: deletes a project created by `odcr init`. It shows what will be deleted (including
  files you added, such as `.env`), asks you to type the project name, never touches database tables, and refuses
  folders that are not odcr projects or that you are currently inside. `--yes` skips the question for scripts.
- Email without stored passwords: `mail.provider` = `smtp-relay`, `microsoft365` (Microsoft Graph with Entra ID
  managed identity / workload identity / `az login`), `aws-ses` (IAM role), or `smtp` / `gmail` with the password
  in the OS keychain. `odcr init` asks how email is sent (`--mail`, `--mail-from`, `--alerts-email`).
- `odcr secret set|check|delete NAME` and `${keyring:NAME}` in configs: secrets in the macOS Keychain, Windows
  Credential Manager or Linux Secret Service.
- Contracts from any Git repository per command: `--contracts <folder or Git URL>`, `--contracts-ref`, or
  `ODCR_CONTRACTS` / `ODCR_CONTRACTS_REF`; `odcr lint <git url>` works without a project; `token_user` for GitLab.
- `odcr init` adds pipeline templates (ingestion → contract gate → transformation) for Azure DevOps and GitHub
  Actions in `pipelines/`.
- Documentation: architecture and flow diagrams, running in pipelines, command overview.
- `odcr doctor` shows the connection settings it uses (host, database, user; never the password).
- `odcr init` writes `.odcr/project.json`, which marks the folder as an odcr project.

### Fixed
- `odcr init --adapter <name>` no longer asks for the adapter again in interactive mode; `--name` skips the
  project-name question too.
- A mistyped adapter name (e.g. `postgress`) now suggests the right one.
- `${VAR:-default}` now uses the default when the variable is set but empty (as in the shell), so an empty
  `SMTP_HOST=` in `.env` no longer breaks email.
- Email alerts without a mail server now say so clearly (set `SMTP_HOST`) instead of "please run connect() first".
- New projects no longer print the summary twice (the console alert is left out of the generated config).
- `odcr init` without a folder creates a new folder named after the project (like `dbt init`), instead of
  `odcr_project`; nothing is ever written into the current folder itself.

## [0.2.0] - 2026-11-27

### Added
- 18 adapters: DuckDB, SQLite, files (local, ADLS Gen2, Blob, S3, GCS, MinIO), PostgreSQL, MySQL/MariaDB,
  SQL Server/Azure SQL, Azure Synapse, Fabric Warehouse, Oracle, IBM Db2, Trino/Starburst/Presto, Snowflake,
  Databricks (Azure, AWS, GCP), BigQuery, Redshift, Athena, MongoDB, Azure Cosmos DB.
- `odcr init`: interactive project scaffolding (like `dbt init`) with config, `.env.example`, contracts,
  reconciliations, seeds, job wrappers for Linux/macOS/Unix and Windows, tests and CI for GitHub and Azure DevOps.
- Central contract repository: `contracts.path` or `contracts.git` (cloned and refreshed); `--contract-id` and
  `--for-object` lookup; `odcr contracts`; `odcr lint` on folders.
- `odcr watch`: check every new file or batch the moment it lands; processed batches are remembered.
- `odcr adapters`, `odcr doctor`, `odcr seed`.
- Notifications: Microsoft Teams (Adaptive Cards), Google Chat, Discord, PagerDuty, Opsgenie; SMTP with STARTTLS
  or implicit TLS; custom CA bundles and proxies.
- `meta.connection`: store results on another platform (for read-only sources).
- Custom quality rules per engine (`engine: mongodb`, `engine: cosmosdb`); rules for other engines are skipped.
- `${file:/path}` secrets and automatic `.env` loading.
- Airflow operators: `OdcrContractOperator`, `OdcrReconcileOperator`, `OdcrCheckpointOperator`.
- Reference project per adapter in `examples/`; documentation site; Dockerfile; release workflow with PyPI
  trusted publishing.
- CI on Windows, macOS and Linux; end-to-end tests against PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, Trino
  and MongoDB; cloud end-to-end tests when credentials are configured.

### Changed
- Minimum Python version is 3.10.
- SQL Server connections encrypt and verify the server certificate by default.

## [0.1.0] - 2026-11-26

### Added
- First public version: ODCS v3 contracts, schema and quality checks, quarantine, notifications (Slack, Teams,
  email, webhook), meta tables, reconciliation, end-to-end tracing; PostgreSQL, MySQL and SQL Server adapters.
