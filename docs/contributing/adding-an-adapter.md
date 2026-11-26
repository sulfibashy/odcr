# Adding an adapter

An adapter teaches odcr one platform. Most are 30–60 lines.

1. Create `src/odcr/adapters/<platform>.py`, subclass `Adapter` (SQL) or `DocumentAdapter`:

```python
from .base import Adapter

class ClickHouseAdapter(Adapter):
    dialect = "clickhouse"
    driver = "clickhouse_connect"
    paramstyle = "format"            # format (%s) | qmark (?) | named (:p0) | inline (odcr renders literals)
    quote_open = quote_close = "`"

    def _connect(self):
        import clickhouse_connect.dbapi
        return clickhouse_connect.dbapi.connect(host=self.options["host"], ...)

    def meta_types(self):
        return {"id": "String", "name": "String", "short": "String", "text": "String",
                "ts": "DateTime64(6)", "int": "Int64", "num": "Float64"}

    def create_table_sql(self, table, columns_sql):
        return f"CREATE TABLE IF NOT EXISTS {table} ({columns_sql}) ENGINE = MergeTree ORDER BY tuple()"
```

2. Override only what differs from `base.py`:

| Method / attribute | Default | Override when |
| --- | --- | --- |
| `paramstyle` | `format` | the driver uses `?`, named or no parameters |
| `quote_open/close`, `quote_policy` | `"`, always | backticks / brackets; `needed` for upper-case-folding platforms |
| `columns()` | `information_schema.columns` | another catalog (SYSCAT, ALL_TAB_COLUMNS, DESCRIBE) |
| `limit()` | `LIMIT n` | `TOP n` / `FETCH FIRST` |
| `create_schema_sql()` / `create_table_sql()` | `IF NOT EXISTS` | no `IF NOT EXISTS` (set `ignore_errors`) |
| `meta_types()` / `sample_types()` | ANSI | platform types |
| `meta_in_current_schema` | False | no schemas (prefix meta tables) |

3. Register it in `src/odcr/adapters/__init__.py` (`ADAPTERS`, with extra, connection template and aliases),
   add the extra to `pyproject.toml`, and run `python scripts/generate_examples.py` and
   `python scripts/generate_docs.py`.

4. Add the target to `tests/conftest.py` (`TARGETS` and `connection_options`). **Every end-to-end test then runs
   against your platform** — the contract runs, quarantine, notifications, reconciliation (also across
   platforms), tracing and streaming micro-batches. When they pass, the adapter is supported. Add a service to
   `.github/workflows/ci.yml` if it runs in a container.
