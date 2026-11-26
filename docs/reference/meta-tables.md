# Meta tables

Created by `odcr meta-init` (or on first run) in the `meta.schema` schema of each platform (default `odcr_meta`).
SQLite and Oracle use a prefix in the current schema instead (`odcr_meta_validation_runs`). MongoDB and Cosmos DB
use a database with one collection / container per table. All tables are append-only.

| Table | One row per | Key columns |
| --- | --- | --- |
| `contracts` | contract version seen | contract_id, contract_version, yaml_hash, owner, loaded_at |
| `validation_runs` | contract check of a table / batch / file | run_id, contract_id, object_name, batch_id, status, rows_checked, checks_failed |
| `check_results` | rule evaluated in a run | run_id, check_id, check_type, column_name, severity, expected, actual, status, query_text |
| `quarantine_log` | failed batch | run_id, contract_id, object_name, batch_id, reason, released_at |
| `notifications` | alert attempt | run_id, channel, recipient (masked), audience, status |
| `reconciliation_runs` | source-vs-target comparison | run_id, recon_id, batch_id, status |
| `reconciliation_results` | reconciliation check | run_id, check_id, source_value, target_value, difference, status |
| `pipeline_events` | stage checkpoint | pipeline, stage, batch_id, mode, row_count, status, event_time |

Useful queries:

```sql
-- failure rate per contract, last 30 days
SELECT contract_id, COUNT(*) AS runs, SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS failed
FROM odcr_meta.validation_runs GROUP BY contract_id;

-- which rules break most often
SELECT check_id, COUNT(*) FROM odcr_meta.check_results WHERE status = 'failed' GROUP BY check_id ORDER BY 2 DESC;
```
