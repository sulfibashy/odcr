<div align="center">

# odcr — Open Data Contract Runtime

**Check every dataset against its data contract the moment it lands — on any database, lake or cloud.**

[![CI](https://github.com/sulfibashy/odcr/actions/workflows/ci.yml/badge.svg)](https://github.com/sulfibashy/odcr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/odcr.svg)](https://pypi.org/project/odcr/)
[![Python](https://img.shields.io/pypi/pyversions/odcr.svg)](https://pypi.org/project/odcr/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-sulfibashy.github.io%2Fodcr-indigo.svg)](https://sulfibashy.github.io/odcr/)
[![ODCS](https://img.shields.io/badge/contracts-ODCS%20v3-green.svg)](https://github.com/bitol-io/open-data-contract-standard)

[Documentation](https://sulfibashy.github.io/odcr/) · [Quickstart](#quickstart) · [Adapters](#adapters) · [Examples](examples/) · [Contributing](CONTRIBUTING.md)

</div>

---

odcr reads [ODCS](https://github.com/bitol-io/open-data-contract-standard) data contracts from your **central
contract repository** and enforces them wherever data arrives — a table, a lakehouse, or files in ADLS, S3, GCS
or a landing folder — however it got there: **batch, streaming, CDC, events or file drops**.

For every batch, micro-batch or file, odcr:

| | |
| --- | --- |
| **Checks** | schema (missing columns, wrong types, drift) and quality rules (nulls, duplicates, valid values, row counts, custom SQL) |
| **Decides** | pass, warn, or fail and quarantine — the exit code stops your pipeline |
| **Notifies** | the source team and the platform team: Slack, Teams, email, Google Chat, Discord, PagerDuty, Opsgenie, webhooks |
| **Logs** | every run, check and alert in meta tables created **on the platform itself** |
| **Reconciles** | source against target per batch — even Oracle → Snowflake or ADLS files → Databricks |
| **Traces** | each batch from source to consumption, flagging the stage where rows were lost |

## Quickstart

```bash
pip install "odcr[postgres]"                     # pick your platform: odcr adapters
odcr init my_contracts --adapter postgres        # creates a full project, like dbt init
cd my_contracts
cp .env.example .env                             # fill in the connection (Windows: copy)
odcr doctor                                      # driver, TLS, permissions, meta tables, contracts
odcr seed                                        # optional sample data
odcr run --contract-id orders --batch-id batch-002 --where "load_id = 'batch-002'"
```

```text
Contract orders v1.0.0 batch=batch-002: FAIL
  orders: FAIL (4 rows, 4 failed, 0 warnings)
    - [failed] orders.order_id.unique: expected = 0, got 1 (unique: no duplicate values)
    - [failed] orders.customer_id.required: expected = 0, got 1 (required: no NULL values)
    - [failed] orders.status.invalidValues: expected = 0, got 1
    - [failed] orders.no_negative_amounts: expected = 0, got 1 (Amounts must never be negative)
```

Then check new data automatically as it lands:

```bash
odcr watch --contract-id orders --batch-column load_id          # every new batch in a table
odcr watch --contract-id orders -C lake                          # every new file in ADLS / S3 / GCS
```

## Adapters

| | Platforms | Install |
| --- | --- | --- |
| **Files** | Parquet / CSV / JSON in local folders, network shares, **ADLS Gen2**, Azure Blob, **S3**, **GCS**, MinIO | `odcr[files]` |
| **Embedded** | DuckDB, SQLite | `odcr[duckdb]`, `odcr` |
| **On-premise / open source** | PostgreSQL, MySQL, MariaDB, **SQL Server**, **Oracle**, **IBM Db2**, Trino / Starburst / Presto | `odcr[postgres]` `[mysql]` `[sqlserver]` `[oracle]` `[db2]` `[trino]` |
| **Azure** | **Databricks**, **Synapse Analytics**, **Fabric Warehouse**, Azure SQL, **Cosmos DB**, Azure PostgreSQL / MySQL | `odcr[databricks]` `[synapse]` `[fabric]` `[sqlserver]` `[cosmosdb]` |
| **AWS** | Databricks, **Redshift**, **Athena**, Aurora / RDS, DocumentDB | `odcr[databricks]` `[redshift]` `[athena]` `[postgres]` `[mongodb]` |
| **GCP** | Databricks, **BigQuery**, Cloud SQL, AlloyDB | `odcr[databricks]` `[bigquery]` `[postgres]` |
| **Multi-cloud** | **Snowflake**, **MongoDB** / Atlas | `odcr[snowflake]` `[mongodb]` |

18 adapters; `pip install "odcr[all]"` installs every driver. Each has a ready-to-run reference project in
[`examples/`](examples/) and a [documentation page](https://sulfibashy.github.io/odcr/adapters/).
**Informatica, Ab Initio, Azure Data Factory, SSIS, Airflow and Databricks Workflows** call odcr after they land
data — see [Integrations](https://sulfibashy.github.io/odcr/integrations/).

## A contract

```yaml
apiVersion: v3.0.2
kind: DataContract
id: orders
version: 1.0.0
support:                                    # the source team is notified here
  - {channel: "#orders-alerts", tool: slack, url: "${ORDERS_SLACK_WEBHOOK}"}
  - {channel: orders, tool: teams, url: "${ORDERS_TEAMS_WEBHOOK}"}
  - {channel: orders-team@example.com, tool: email, url: "mailto:orders-team@example.com"}
schema:
  - name: orders
    physicalName: sales.orders              # or abfss://landing@lake.dfs.core.windows.net/orders/*.parquet
    properties:
      - {name: order_id, logicalType: integer, primaryKey: true}
      - name: status
        logicalType: string
        quality:
          - {type: library, metric: invalidValues, arguments: {validValues: [NEW, PAID, SHIPPED]}, mustBe: 0}
      - name: amount
        logicalType: number
        quality:
          - {type: library, metric: nullValues, mustBeLessOrEqualTo: 1, unit: percent, severity: warning}
    quality:
      - {type: library, metric: rowCount, mustBeGreaterThan: 0}
      - {type: sql, query: "SELECT COUNT(*) FROM {object} WHERE amount < 0", mustBe: 0}
```

## Runs everywhere

- **Operating systems:** Windows, macOS, Linux and Unix servers — tested in CI on all three major ones.
- **Install:** `pip`, `pipx`, offline wheelhouses for air-gapped servers, the [Dockerfile](Dockerfile), Databricks
  libraries, Azure Functions, AWS Lambda.
- **Security:** TLS with verified certificates by default; corporate CA bundles and proxies; secrets from
  environment variables, `.env` or secret files; managed identities, IAM roles, key-pair and OAuth. See
  [Security](https://sulfibashy.github.io/odcr/security/).

## Python API

```python
from odcr import ContractRepository, run_contract
from odcr.adapters import get_adapter
from odcr.config import load_config

config = load_config("odcr.yaml")
contract = ContractRepository.from_config(config).get("orders")
with get_adapter(config.connection("main")) as db:
    result = run_contract(contract, db, config, batch_id="42", where="load_id = '42'")
    if not result.passed:
        raise SystemExit(result.summary())
```

Airflow: `from odcr.integrations.airflow import OdcrContractOperator`.

## Contributing

odcr is community-built. Adapters are the easiest way in: [adding one](docs/contributing/adding-an-adapter.md)
is ~50 lines, and the whole end-to-end suite then runs against your platform. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) and issues labelled `good first issue`.

Licensed under the [Apache License 2.0](LICENSE).
