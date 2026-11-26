# Changelog

## 0.1.0 (unreleased)

First public version.

- Load and validate ODCS v3 contracts (ODCS 3.0 rule names supported as aliases)
- Schema checks (table and columns exist, logicalType, extra columns) and quality checks (rowCount, nullValues, missingValues, duplicateValues, invalidValues, custom SQL)
- Batch / micro-batch filtering with `--where`; pass, warn, fail and quarantine
- Notifications to source and platform teams via Slack, Teams, webhook and email
- Meta tables created inside each platform; run history with `odcr history`
- Reconciliation between source and target, including across platforms
- End-to-end stage checkpoints and `odcr trace`
- Adapters: PostgreSQL, MySQL/MariaDB (tested), SQL Server (implemented)
