# Development

```bash
git clone https://github.com/sulfibashy/odcr && cd odcr
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                                  # DuckDB, SQLite, files and MongoDB (in-memory) always run
docker compose up -d                                    # PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, Trino, MongoDB
pytest                                                  # now against every server too
ruff check src tests
```

## Environment variables for end-to-end tests

| Variable | Target |
| --- | --- |
| `ODCR_PG_HOST`, `ODCR_MYSQL_HOST`, `ODCR_MARIADB_HOST` | PostgreSQL, MySQL, MariaDB |
| `ODCR_MSSQL_HOST`, `ODCR_ORACLE_HOST`, `ODCR_TRINO_HOST`, `ODCR_MONGO_URI` | SQL Server, Oracle, Trino, MongoDB |
| `ODCR_TEST_<ADAPTER>` | JSON connection options for any adapter, e.g. `ODCR_TEST_SNOWFLAKE='{"type": "snowflake", ...}'` |

In GitHub Actions the cloud targets run when the repository has secrets named `ODCR_TEST_SNOWFLAKE`,
`ODCR_TEST_DATABRICKS`, `ODCR_TEST_BIGQUERY`, `ODCR_TEST_REDSHIFT`, `ODCR_TEST_ATHENA`, `ODCR_TEST_SYNAPSE`,
`ODCR_TEST_FABRIC`, `ODCR_TEST_COSMOSDB`, `ODCR_TEST_DB2`.

## Regenerated files

`examples/` and `docs/adapters/` are generated from the adapter registry; tests fail when they are stale:

```bash
python scripts/generate_examples.py
python scripts/generate_docs.py
```

## Releasing

1. Move the `Unreleased` changelog entries under the new version, and set that version in `pyproject.toml` and
   `src/odcr/__init__.py` (between releases `main` carries a `.devN` version, e.g. `0.2.2.dev0`, so installs from
   Git never look like a release).
2. Run **Actions → release → Run workflow** (or push a tag `vX.Y.Z`). It tests, builds, publishes to PyPI
   (trusted publishing) and creates the GitHub release and tag from the changelog. Run **docs** to update the site.
3. Bump `main` to the next `.dev0` version.
