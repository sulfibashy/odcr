# Contributing to odcr

Thank you for helping. Every contribution counts: code, docs, examples, bug reports and ideas.

## Ground rules

- **ODCS is the contract format.** We follow the [Open Data Contract Standard](https://github.com/bitol-io/open-data-contract-standard) and never invent a competing spec.
- **Few dependencies.** The core needs only PyYAML. Database drivers are optional extras. The [Data Contract CLI](https://github.com/datacontract/datacontract-cli) is an optional extra for linting. Please don't add other frameworks.
- **Clean room.** Never submit code, configs, table names or documents from your employer. Check that your employment contract allows you to contribute.
- **Sign off your commits** (Developer Certificate of Origin): `git commit -s`.

## Set up

```bash
git clone <repo> && cd odcr
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres mysql
pytest            # unit + end-to-end tests; unreachable databases are skipped
```

## Good first contributions

| Area | Example task |
| --- | --- |
| Adapters | Snowflake, Databricks SQL, BigQuery, Oracle, Trino, DuckDB (see `docs/adding-an-adapter.md`) |
| Checks | ODCS `pattern` (regex) checks per dialect, freshness / SLA checks |
| Notifications | PagerDuty, Opsgenie, Jira issue creation |
| Integrations | Airflow operator, dbt post-hook, GitHub Action |
| Docs | Tutorials, contract examples per industry |

## Pull requests

1. Open an issue first for anything larger than a small fix.
2. Add tests: unit tests for logic, an end-to-end test for anything that touches a database.
3. `pytest` must pass. CI runs against PostgreSQL and MySQL on Python 3.10, 3.12 and 3.13.
4. Keep PRs small and focused.

Bigger design changes go through a short RFC: an issue titled `RFC: ...` describing the problem, the proposal and alternatives.
