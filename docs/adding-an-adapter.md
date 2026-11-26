# Adding a platform adapter

An adapter teaches odcr one platform's SQL dialect. Most adapters are under 60 lines.

1. Create `src/odcr/adapters/<platform>.py` and subclass `Adapter`:

```python
from .base import Adapter

class SnowflakeAdapter(Adapter):
    dialect = "snowflake"
    placeholder = "%s"                      # the driver's parameter style
    default_schema_sql = "SELECT CURRENT_SCHEMA()"

    def _connect(self):
        import snowflake.connector         # optional dependency
        return snowflake.connector.connect(**self.options, autocommit=True)
```

2. Override only what differs from the defaults in `base.py`:

| Method | Default | Override when |
| --- | --- | --- |
| `quote()` | `"name"` | identifiers use another quote (MySQL backticks, SQL Server brackets) |
| `limit()` | `... LIMIT n` | the dialect uses `TOP n` or `FETCH FIRST` |
| `columns()` | `information_schema.columns` | the platform has another catalog (e.g. Unity Catalog `system.information_schema`) |
| `create_schema()` | `CREATE SCHEMA IF NOT EXISTS` | schemas work differently (MySQL databases, SQL Server `EXEC`) |
| `create_table_sql()` | `CREATE TABLE IF NOT EXISTS` | no `IF NOT EXISTS` support |
| `meta_types()` | ANSI types | column types for the meta tables differ |

3. Register it in `src/odcr/adapters/__init__.py` (`ADAPTERS`), add the driver as an extra in `pyproject.toml`, and add the platform to `connection_options()` and to the `db` fixture's `params` in `tests/conftest.py`.

4. Every end-to-end test then runs against your platform automatically, because the `db` fixture is parametrised over the platforms. When they pass, the platform is supported.
