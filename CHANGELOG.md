# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-11-27

### Added
- `odcr destroy [folder]`: deletes a project created by `odcr init`. It shows what will be deleted (including
  files you added, such as `.env`), asks you to type the project name, never touches database tables, and refuses
  folders that are not odcr projects or that you are currently inside. `--yes` skips the question for scripts.
- `odcr doctor` shows the connection settings it uses (host, database, user; never the password).
- `odcr init` writes `.odcr/project.json`, which marks the folder as an odcr project.

### Fixed
- `odcr init --adapter <name>` no longer asks for the adapter again in interactive mode; `--name` skips the
  project-name question too.
- A mistyped adapter name (e.g. `postgress`) now suggests the right one.
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
