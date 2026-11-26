# odcr — Open Data Contract Runtime

**Enforce data contracts where data enters your platform, reconcile source and target, and trace every batch from ingestion to consumption.**

odcr reads [ODCS](https://github.com/bitol-io/open-data-contract-standard) (Open Data Contract Standard) YAML contracts from your Git repository and, at ingestion time:

1. **Checks the batch** against the contract: schema (columns, types, drift) and quality rules (nulls, duplicates, valid values, row counts, custom SQL).
2. **Decides**: pass, warn, or fail and quarantine.
3. **Notifies** the source team (from the contract) and the platform team (from config) via Slack, Teams, webhook or email.
4. **Logs everything** in meta tables created **inside the platform the data lives in**: PostgreSQL tables in PostgreSQL, MySQL tables in MySQL, SQL Server tables in SQL Server.
5. **Reconciles** source and target per batch, even across platforms (row counts, sums, distinct counts, min/max, missing keys).
6. **Traces** each batch or micro-batch through every stage (source → ingestion → bronze → silver → gold → consumption) and flags where rows were lost.

It works the same for **batch, streaming, CDC, Event Hub, Kafka and queue** loads: every load unit gets a `batch_id`.

> Status: alpha (v0.1). PostgreSQL and MySQL/MariaDB are tested end to end; SQL Server is implemented and needs community testing.

## Install

```bash
pip install "odcr[postgres]"        # or [mysql], [sqlserver], [all]
pip install "odcr[lint]"            # optional: official Data Contract CLI for linting
```

The core depends only on PyYAML. Notifications use the Python standard library.

## Quick start

```bash
odcr init                                   # creates odcr.yaml, contracts/, reconciliations/
odcr lint contracts/orders.odcs.yaml
odcr meta-init -C postgres-dev              # creates the odcr_meta schema and tables
odcr run contracts/orders.odcs.yaml -C postgres-dev --batch-id 42 --where "load_id = '42'"
```

Exit codes: `0` pass or warn, `1` fail (or warn with `--fail-on-warn`), `2` invalid contract or config. Use the exit code to stop your pipeline.

```text
Contract orders v1.0.0 batch=42: FAIL
  orders: FAIL (4 rows, 4 failed, 0 warnings)
    - [failed] orders.order_id.unique: expected = 0, got 1 (unique: no duplicate values)
    - [failed] orders.customer_id.required: expected = 0, got 1 (required: no NULL values)
    - [failed] orders.status.invalidValues: expected = 0, got 1
    - [failed] orders.no_negative_amounts: expected = 0, got 1 (Amounts must never be negative)
```

## A contract (ODCS v3)

```yaml
apiVersion: v3.0.2
kind: DataContract
id: orders
version: 1.0.0
support:                                    # the source team is notified here
  - channel: "#orders-data-alerts"
    tool: slack
    url: ${ORDERS_SLACK_WEBHOOK}
schema:
  - name: orders
    physicalName: orders
    properties:
      - name: order_id
        logicalType: integer
        primaryKey: true                    # required + unique
      - name: status
        logicalType: string
        quality:
          - type: library
            metric: invalidValues
            arguments: {validValues: [NEW, PAID, SHIPPED, CANCELLED]}
            mustBe: 0
      - name: amount
        logicalType: number
        quality:
          - type: library
            metric: nullValues
            mustBeLessOrEqualTo: 1
            unit: percent
            severity: warning               # notify, but do not stop the pipeline
    quality:
      - type: library
        metric: rowCount
        mustBeGreaterThan: 0
      - type: sql
        query: SELECT COUNT(*) FROM {object} WHERE amount < 0
        mustBe: 0
```

Supported checks: schema (table and column exist, `logicalType` matches, extra columns), `required`, `unique`, `primaryKey`, library metrics `rowCount`, `nullValues`, `missingValues`, `duplicateValues`, `invalidValues` (and the ODCS 3.0 names `nullCheck`, `duplicateCount`, `validValues`), custom `sql`, with every ODCS comparator (`mustBe`, `mustBeGreaterThan`, `mustBeBetween`, ...), `unit: rows|percent` and `severity`.

## Reconciliation

```yaml
kind: Reconciliation
id: orders-postgres-to-mysql
source: {connection: postgres-dev, object: public.orders, where: "load_id = '{batch_id}'"}
target: {connection: mysql-dev, object: orders, where: "load_id = '{batch_id}'"}
checks:
  - type: rowCount
  - type: sum
    column: amount
    tolerance: 0.01
  - type: missingKeys
    column: order_id
```

```bash
odcr reconcile reconciliations/orders.recon.yaml --batch-id 42
```

Check types: `rowCount`, `sum`, `min`, `max`, `distinctCount`, `nullCount`, `missingKeys`, with `tolerance` or `tolerancePercent`.

## End-to-end tracing

```bash
odcr checkpoint -C postgres-dev --pipeline orders --stage source --batch-id 42 --rows 1200
odcr run contracts/orders.odcs.yaml -C postgres-dev --batch-id 42 --where "load_id='42'" \
     --pipeline orders --stage ingestion
odcr checkpoint -C postgres-dev --pipeline orders --stage gold --batch-id 42 --object gold.orders
odcr trace -C postgres-dev --pipeline orders --batch-id 42
```

```text
source             1200 rows           batch      ok
ingestion          1200 rows (+0)      batch      pass   orders
gold               1188 rows (-12)     batch      ok     gold.orders  <-- lost 12 rows
```

For streaming and CDC, call the same functions per micro-batch (see `examples/streaming_microbatch.py`).

## Meta tables

Created in the `odcr_meta` schema (configurable) on each platform. All are append-only, so history is kept.

| Table | One row per |
| --- | --- |
| `contracts` | contract version seen (with a hash of the YAML) |
| `validation_runs` | contract check of a table or batch |
| `check_results` | rule evaluated in a run |
| `quarantine_log` | failed batch |
| `notifications` | alert sent (or failed) |
| `reconciliation_runs` / `reconciliation_results` | source-vs-target comparison and its checks |
| `pipeline_events` | stage checkpoint per batch |

```bash
odcr history -C postgres-dev --contract-id orders
```

## Python API

```python
from odcr import load_contract, run_contract
from odcr.adapters import get_adapter
from odcr.config import load_config

config = load_config("odcr.yaml")
with get_adapter(config.connection("postgres-dev")) as db:
    result = run_contract(load_contract("contracts/orders.odcs.yaml"), db, config,
                          batch_id="42", where="load_id = '42'")
    if not result.passed:
        raise SystemExit(result.summary())
```

## Platforms

| Platform | Status |
| --- | --- |
| PostgreSQL | tested end to end |
| MySQL / MariaDB | tested end to end |
| SQL Server / Azure SQL | implemented, needs testers |
| Databricks, Snowflake, BigQuery, Trino, Oracle | next: see `docs/adding-an-adapter.md` |

## Development

```bash
pip install -e ".[dev]"
docker compose up -d postgres mysql
pytest
```

## Documentation

- [Architecture](docs/architecture.md)
- [Contract reference: what odcr checks](docs/contract-reference.md)
- [Streaming, CDC, Event Hub and queues](docs/streaming-and-cdc.md)
- [Adding a platform adapter](docs/adding-an-adapter.md)
- [Roadmap](docs/roadmap.md)

## Contributing

Contributions are welcome: adapters, checks, integrations, docs and examples. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the issues labelled `good first issue`. Please follow the [Code of Conduct](CODE_OF_CONDUCT.md) and report security issues as described in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
