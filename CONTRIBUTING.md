# Contributing to odcr

Thank you for helping! Code, adapters, docs, examples, bug reports and ideas are all welcome.

## Ground rules

- **ODCS is the contract format.** We follow the [Open Data Contract Standard](https://github.com/bitol-io/open-data-contract-standard)
  and never invent a competing spec.
- **Small core.** The core depends only on PyYAML; drivers are optional extras. The
  [Data Contract CLI](https://github.com/datacontract/datacontract-cli) is an optional extra for linting.
  Please don't add other quality frameworks.
- **Works everywhere.** Code must run on Windows, macOS and Linux (use `pathlib`, no shell-only features).
- **Secure by default.** Never disable TLS verification by default; never log secrets.
- **Clean room.** Never submit code, configs, table names or documents from your employer. Check that your
  employment contract allows you to contribute.
- **Sign off your commits** (Developer Certificate of Origin): `git commit -s`.

## Set up

```bash
git clone https://github.com/sulfibashy/odcr && cd odcr
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install                                     # optional: ruff on every commit
pytest                                                 # DuckDB, SQLite, files and MongoDB (in-memory)
docker compose up -d                                   # PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, Trino, MongoDB
pytest                                                 # now against every server too
```

See [docs/contributing/development.md](docs/contributing/development.md) for the test environment variables and
how cloud tests run.

## Good first contributions

| Area | Examples |
| --- | --- |
| Adapters | ClickHouse, SAP HANA, Teradata, Vertica, Exasol, Elasticsearch ([guide](docs/contributing/adding-an-adapter.md)) |
| Testing | Run the cloud end-to-end suite on Snowflake, Databricks, BigQuery, Synapse, Fabric, Db2 and report back |
| Checks | ODCS `pattern` (regex) checks per dialect, freshness / SLA checks |
| Notifications | Jira and ServiceNow incident creation |
| Integrations | Dagster and Prefect, dbt post-hook macro, GitHub Action |
| Docs | Tutorials, contract examples per industry, translations |

## Pull requests

1. Open an issue first for anything bigger than a small fix.
2. Add tests: unit tests for logic, end-to-end tests (the `db` fixture) for anything that touches a platform.
3. `pytest` and `ruff check src tests scripts` must pass. If you change adapters or scaffolding, run
   `python scripts/generate_examples.py` and `python scripts/generate_docs.py`.
4. Update `CHANGELOG.md`.
5. Keep pull requests small and focused.

Bigger design changes go through a short RFC: an issue titled `RFC: ...` with the problem, the proposal and the
alternatives. See [GOVERNANCE.md](GOVERNANCE.md) for how decisions are made.
