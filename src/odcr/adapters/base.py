"""Adapter base classes.

Every platform is one small class. `Adapter` (SQL) covers relational engines; it handles
parameter styles, identifier quoting, catalog lookups, check evaluation, aggregates for
reconciliation and the meta tables. `DocumentAdapter` (in document.py) covers MongoDB and
Cosmos DB. See docs/contributing/adding-an-adapter.md.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..checks import Check

# Physical types accepted for each ODCS logicalType (matched against the platform catalog).
TYPE_FAMILIES: dict[str, set[str]] = {
    "integer": {"int", "integer", "bigint", "smallint", "tinyint", "mediumint", "int2", "int4", "int8", "int16",
                "int32", "int64", "serial", "bigserial", "number", "long", "hugeint", "ubigint", "uinteger",
                "byteint", "decfloat"},
    "number": {"int", "integer", "bigint", "smallint", "tinyint", "mediumint", "numeric", "decimal", "double",
               "double precision", "float", "real", "money", "smallmoney", "int2", "int4", "int8", "int64",
               "float4", "float8", "float64", "number", "bignumeric", "binary_double", "binary_float", "long",
               "hugeint", "decfloat", "decimal128", "int32"},
    "string": {"char", "varchar", "varchar2", "nvarchar2", "text", "character", "character varying", "nvarchar",
               "nchar", "ntext", "tinytext", "mediumtext", "longtext", "string", "uuid", "enum", "citext",
               "clob", "nclob", "graphic", "vargraphic"},
    "date": {"date", "bsondate"},
    "timestamp": {"timestamp", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "timestamptz",
                  "timestamp with time zone", "timestamp without time zone", "timestamp_ntz", "timestamp_ltz",
                  "timestamp_tz", "bsondate", "timestmp"},
    "boolean": {"bool", "boolean", "bit", "tinyint"},
}

_SIMPLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# Words that must be quoted even when the platform folds unquoted names to upper case.
RESERVED = {
    "all", "and", "as", "by", "check", "column", "comment", "date", "default", "domain", "from", "group",
    "level", "mode", "name", "number", "of", "on", "or", "order", "owner", "rows", "select", "size", "stage",
    "status", "table", "to", "user", "value", "values", "where", "file", "uid", "session", "start", "type",
}


def type_matches(logical_type: str | None, data_type: str | None) -> bool | None:
    """True/False when the logical type is checkable, None when it is not (unknown type or no catalog type)."""
    if not logical_type or not data_type:
        return None
    family = TYPE_FAMILIES.get(logical_type.lower())
    if family is None:
        return None
    t = data_type.lower().strip()
    return t in family or any(t.startswith(k + " ") or t.startswith(k + "(") or t.startswith(k + "<")
                              for k in family)


class UnsupportedCheck(Exception):
    """Raised by an adapter when a check type cannot run on that platform (the check is skipped)."""


class Adapter:
    """SQL adapter. Subclasses set class attributes and implement `_connect`."""

    kind = "sql"
    dialect = "generic"
    paramstyle = "format"  # format (%s) | qmark (?) | named (:p0) | inline (literals rendered by odcr)
    quote_open, quote_close = '"', '"'
    quote_policy = "always"  # always | needed (for platforms that fold unquoted names to upper case)
    meta_in_current_schema = False  # True: meta tables are prefixed (odcr_meta_runs) instead of a schema
    default_schema_sql = "SELECT current_schema()"
    ping_sql = "SELECT 1"
    ignore_errors: tuple[str, ...] = ()  # error texts that mean "already exists" for DDL without IF NOT EXISTS
    driver = ""  # import name of the Python driver, shown by `odcr doctor`
    multi_row_insert = False  # one INSERT ... VALUES (..), (..) instead of executemany

    _NAMED_MARK = ":__odcr__"
    _INLINE_MARK = "\x00odcr\x00"

    def __init__(self, **options: Any):
        self.options = options
        self.conn: Any = None
        self._meta_ready: set[str] = set()
        self._schema: str | None = None

    # ------------------------------------------------------------------ connection
    def _connect(self) -> Any:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def connect(self) -> Adapter:
        if self.conn is None:
            self.conn = self._connect()
        return self

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def __enter__(self) -> Adapter:
        return self.connect()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def ping(self) -> bool:
        self.connect()
        self.scalar(self.ping_sql)
        return True

    def driver_version(self) -> str:
        if not self.driver:
            return "built-in"
        try:
            mod = __import__(self.driver, fromlist=["__version__"])
            version = getattr(mod, "__version__", None) or getattr(mod, "sqlite_version", None) or "?"
            return f"{self.driver} {version}"
        except ImportError:
            return f"{self.driver} (not installed)"

    # ------------------------------------------------------------------ parameters
    @property
    def placeholder(self) -> str:
        return {"format": "%s", "qmark": "?", "named": self._NAMED_MARK, "inline": self._INLINE_MARK}[self.paramstyle]

    def params(self, n: int) -> str:
        return ", ".join([self.placeholder] * n)

    def to_db(self, value: Any) -> Any:
        """Convert a Python value before sending it to the driver (override per platform)."""
        return value

    def literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        if isinstance(value, dt.datetime):
            return f"TIMESTAMP '{value.strftime('%Y-%m-%d %H:%M:%S.%f')}'"
        if isinstance(value, dt.date):
            return f"DATE '{value.isoformat()}'"
        return "'" + str(value).replace("'", "''") + "'"

    def _bind(self, sql: str, params: Sequence[Any] | None) -> tuple[str, Any]:
        if not params:
            return sql, None
        values = [self.to_db(v) for v in params]
        if self.paramstyle in ("format", "qmark"):
            return sql, tuple(values)
        if self.paramstyle == "named":
            parts = sql.split(self._NAMED_MARK)
            out = parts[0] + "".join(f":p{i}{part}" for i, part in enumerate(parts[1:]))
            return out, {f"p{i}": v for i, v in enumerate(values)}
        parts = sql.split(self._INLINE_MARK)
        return parts[0] + "".join(self.literal(v) + part for v, part in zip(values, parts[1:])), None

    # ------------------------------------------------------------------ execution
    def cursor(self) -> Any:
        self.connect()
        return self.conn.cursor()

    def _run(self, cur: Any, sql: str, params: Sequence[Any] | None) -> None:
        q, p = self._bind(sql, params)
        if p is None:
            cur.execute(q)
        else:
            cur.execute(q, p)

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        cur = self.cursor()
        try:
            self._run(cur, sql, params)
        finally:
            self._close_cursor(cur)
        self._commit()

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        rows = [list(r) for r in rows]
        if not rows:
            return
        if self.paramstyle in ("named", "inline"):
            for r in rows:
                self.execute(sql, r)
            return
        cur = self.cursor()
        try:
            cur.executemany(sql, [tuple(self.to_db(v) for v in r) for r in rows])
        finally:
            self._close_cursor(cur)
        self._commit()

    def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        cur = self.cursor()
        try:
            self._run(cur, sql, params)
            return [tuple(r) for r in cur.fetchall()]
        finally:
            self._close_cursor(cur)

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.fetchall(sql, params)
        return rows[0][0] if rows else None

    def _close_cursor(self, cur: Any) -> None:
        close = getattr(cur, "close", None)
        if close:
            close()

    def _commit(self) -> None:
        """Most adapters run in autocommit mode; override when the driver needs explicit commits."""

    def try_execute(self, sql: str) -> bool:
        """Run DDL, ignoring 'already exists' style errors. Returns False when an error was ignored."""
        try:
            self.execute(sql)
            return True
        except Exception as exc:  # noqa: BLE001
            text = str(exc).lower()
            if any(marker.lower() in text for marker in self.ignore_errors):
                self._rollback()
                return False
            raise

    def _rollback(self) -> None:
        rb = getattr(self.conn, "rollback", None)
        if rb:
            try:
                rb()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ identifiers
    def quote(self, identifier: str) -> str:
        if self.quote_policy == "needed" and _SIMPLE.match(identifier):
            if identifier.lower() not in RESERVED:
                return identifier
            identifier = identifier.upper()
        inner = identifier.replace(self.quote_close, self.quote_close * 2)
        return f"{self.quote_open}{inner}{self.quote_close}"

    @staticmethod
    def is_raw(name: str) -> bool:
        """A table function or file path (e.g. read_parquet('landing/*.parquet')) is used as written."""
        return any(ch in name for ch in "()'/ ")

    def qualify(self, name: str) -> str:
        if self.is_raw(name):
            return name
        return ".".join(self.quote(part) for part in name.split("."))

    def split_name(self, name: str) -> tuple[str | None, str]:
        parts = name.split(".")
        if len(parts) >= 2:
            return parts[-2], parts[-1]
        return self.current_schema(), parts[0]

    def catalog_of(self, name: str) -> str | None:
        parts = name.split(".")
        return parts[0] if len(parts) >= 3 else None

    def information_schema(self, catalog: str | None) -> str:
        return f"{self.quote(catalog)}.information_schema" if catalog else "information_schema"

    def current_schema(self) -> str | None:
        if self._schema is None:
            self._schema = str(self.scalar(self.default_schema_sql))
        return self._schema

    def limit(self, select_sql: str, n: int) -> str:
        return f"{select_sql} LIMIT {int(n)}"

    # ------------------------------------------------------------------ catalog
    def columns(self, name: str) -> dict[str, str]:
        """Column name (lower case) -> data type (lower case). Empty when the object does not exist."""
        if self.is_raw(name):
            return self.raw_columns(name)
        schema, table = self.split_name(name)
        p = self.placeholder
        rows = self.fetchall(
            f"SELECT column_name, data_type FROM {self.information_schema(self.catalog_of(name))}.columns "
            f"WHERE LOWER(table_schema) = LOWER({p}) AND LOWER(table_name) = LOWER({p})", [schema, table])
        return {str(c).lower(): str(t).lower() for c, t in rows}

    def system_columns(self) -> tuple[str, ...]:
        """Columns the platform adds itself; never reported as 'outside the contract'."""
        return ()

    def raw_columns(self, expr: str) -> dict[str, str]:
        """Column names of a table function / file; types are unknown, so type checks are skipped."""
        cur = self.cursor()
        try:
            cur.execute(f"SELECT * FROM {expr} src WHERE 1 = 0")
            return {str(d[0]).lower(): "" for d in (cur.description or [])}
        except Exception:  # noqa: BLE001
            return {}
        finally:
            self._close_cursor(cur)

    # ------------------------------------------------------------------ data access
    def relation(self, name: str, where: str | None = None) -> str:
        table = self.qualify(name)
        if where:
            return f"(SELECT * FROM {table} WHERE {where}) src"
        return f"{table} src"

    def count(self, name: str, where: str | None = None) -> int:
        return int(self.scalar(f"SELECT COUNT(*) FROM {self.relation(name, where)}") or 0)

    def metric_sql(self, metric: str, name: str, where: str | None, column: str | None,
                   args: dict[str, Any]) -> tuple[str, list[Any]]:
        rel = self.relation(name, where)
        q = self.quote
        if metric == "rowCount":
            return f"SELECT COUNT(*) FROM {rel}", []
        if column is None and metric != "duplicateValues":
            raise ValueError(f"{metric} needs a column")
        if metric == "nullValues":
            return f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NULL", []  # type: ignore[arg-type]
        if metric == "missingValues":
            missing = [m for m in args.get("missingValues", []) if m is not None]
            if missing:
                return (f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NULL OR {q(column)} IN "  # type: ignore
                        f"({self.params(len(missing))})", missing)
            return f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NULL", []  # type: ignore[arg-type]
        if metric == "duplicateValues":
            cols = [column] if column else list(args.get("properties", []))
            if not cols:
                raise ValueError("duplicateValues on an object needs arguments.properties")
            group = ", ".join(q(c) for c in cols)
            not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
            return (f"SELECT COALESCE(SUM(c - 1), 0) FROM (SELECT COUNT(*) AS c FROM {rel} WHERE {not_null} "
                    f"GROUP BY {group} HAVING COUNT(*) > 1) d", [])
        if metric == "invalidValues":
            valid = list(args.get("validValues", []))
            return (f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NOT NULL AND {q(column)} NOT IN "  # type: ignore
                    f"({self.params(len(valid))})", valid)
        raise ValueError(f"Unsupported metric {metric}")

    def render_query(self, query: str, name: str, where: str | None, column: str | None) -> str:
        rel = self.relation(name, where)
        out = query
        for token in ("${object}", "{object}", "${table}", "{table}"):
            out = out.replace(token, rel)
        if column:
            for token in ("${property}", "{property}", "${column}", "{column}"):
                out = out.replace(token, self.quote(column))
        return out

    def evaluate(self, check: Check) -> Any:
        """Run one check and return the number it measures. Sets check.sql to the query that ran."""
        if check.metric:
            sql, params = self.metric_sql(check.metric, check.physical_name, check.where, check.column, check.args)
        elif check.query is not None:
            if check.engine not in (None, "sql", self.dialect):
                raise UnsupportedCheck(f"rule for engine '{check.engine}' skipped on {self.dialect}")
            sql, params = self.render_query(check.query, check.physical_name, check.where, check.column), []
        else:
            raise UnsupportedCheck("nothing to run")
        check.sql, check.params = sql, params
        return self.scalar(sql, params or None)

    def aggregate(self, name: str, where: str | None, func: str, column: str | None) -> Any:
        q = self.quote
        expr = {
            "rowCount": "COUNT(*)",
            "sum": f"SUM({q(column)})" if column else "",
            "min": f"MIN({q(column)})" if column else "",
            "max": f"MAX({q(column)})" if column else "",
            "distinctCount": f"COUNT(DISTINCT {q(column)})" if column else "",
            "nullCount": f"SUM(CASE WHEN {q(column)} IS NULL THEN 1 ELSE 0 END)" if column else "",
        }[func]
        return self.scalar(f"SELECT {expr} FROM {self.relation(name, where)}")

    def distinct_values(self, name: str, where: str | None, column: str, limit: int) -> list[Any]:
        sql = self.limit(f"SELECT DISTINCT {self.quote(column)} FROM {self.relation(name, where)}", limit)
        return [r[0] for r in self.fetchall(sql)]

    # ------------------------------------------------------------------ meta tables
    def meta_types(self) -> dict[str, str]:
        return {"id": "VARCHAR(64)", "name": "VARCHAR(255)", "short": "VARCHAR(32)", "text": "VARCHAR(4000)",
                "ts": "TIMESTAMP", "int": "BIGINT", "num": "DOUBLE PRECISION"}

    def meta_table(self, schema: str, table: str) -> str:
        if self.meta_in_current_schema:
            return self.quote(f"{schema}_{table}".replace(".", "_"))
        return f"{self.qualify(schema)}.{self.quote(table)}"

    def create_schema_sql(self, schema: str) -> str:
        return f"CREATE SCHEMA IF NOT EXISTS {self.qualify(schema)}"

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        return f"CREATE TABLE IF NOT EXISTS {table} ({columns_sql})"

    def meta_ensure(self, schema: str) -> None:
        if schema in self._meta_ready:
            return
        from ..meta import TABLES

        self.connect()
        if not self.meta_in_current_schema:
            self.try_execute(self.create_schema_sql(schema))
        types = self.meta_types()
        for table, cols in TABLES.items():
            cols_sql = ", ".join(f"{self.quote(c)} {types[t]}" for c, t in cols)
            self.try_execute(self.create_table_sql(self.meta_table(schema, table), cols_sql))
        self._meta_ready.add(schema)

    def meta_insert(self, schema: str, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        from ..meta import TABLES

        keys = [c for c, _ in TABLES[table]]
        cols = ", ".join(self.quote(c) for c in keys)
        sql = f"INSERT INTO {self.meta_table(schema, table)} ({cols}) VALUES ({self.params(len(keys))})"
        data = [[self._clip(r.get(k)) for k in keys] for r in rows]
        if self.multi_row_insert and len(data) > 1:
            group = f"({self.params(len(keys))})"
            head = f"INSERT INTO {self.meta_table(schema, table)} ({cols}) VALUES "
            for i in range(0, len(data), 200):
                chunk = data[i:i + 200]
                self.execute(head + ", ".join([group] * len(chunk)), [v for row in chunk for v in row])
            return
        if len(data) == 1:
            self.execute(sql, data[0])
        else:
            self.executemany(sql, data)

    @staticmethod
    def _clip(value: Any) -> Any:
        if isinstance(value, str) and len(value) > 3900:
            return value[:3900] + "..."
        return value

    def _where_eq(self, where: dict[str, Any] | None) -> tuple[str, list[Any]]:
        if not where:
            return "", []
        clauses = [f"{self.quote(k)} = {self.placeholder}" for k in where]
        return " WHERE " + " AND ".join(clauses), list(where.values())

    def meta_count(self, schema: str, table: str, where: dict[str, Any] | None = None) -> int:
        clause, params = self._where_eq(where)
        return int(self.scalar(f"SELECT COUNT(*) FROM {self.meta_table(schema, table)}{clause}", params or None) or 0)

    def meta_select(self, schema: str, table: str, columns: list[str], where: dict[str, Any] | None = None,
                    order_by: str | None = None, descending: bool = True,
                    limit: int | None = None) -> list[dict[str, Any]]:
        clause, params = self._where_eq(where)
        sql = f"SELECT {', '.join(self.quote(c) for c in columns)} FROM {self.meta_table(schema, table)}{clause}"
        if order_by:
            sql += f" ORDER BY {self.quote(order_by)} {'DESC' if descending else 'ASC'}"
        if limit:
            sql = self.limit(sql, limit)
        return [dict(zip(columns, row)) for row in self.fetchall(sql, params or None)]

    # ------------------------------------------------------------------ sample data (seed + tests)
    def sample_types(self) -> dict[str, str]:
        return {"integer": "INTEGER", "string": "VARCHAR(50)", "decimal": "DECIMAL(12,2)", "date": "DATE"}

    def drop_table(self, name: str) -> None:
        table = self.qualify(name)
        try:
            self.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:  # noqa: BLE001 - platforms without IF EXISTS
            self._rollback()
            try:
                self.execute(f"DROP TABLE {table}")
            except Exception:  # noqa: BLE001
                self._rollback()

    def create_sample(self, name: str, columns: list[tuple[str, str]], rows: list[Sequence[Any]]) -> None:
        """Create a table from (column, logical type) pairs and load rows. Used by `odcr seed` and tests."""
        types = self.sample_types()
        self.drop_table(name)
        cols_sql = ", ".join(f"{self.quote(c)} {types[t]}" for c, t in columns)
        self.execute(f"CREATE TABLE {self.qualify(name)} ({cols_sql})")
        if rows:
            names = ", ".join(self.quote(c) for c, _ in columns)
            self.executemany(f"INSERT INTO {self.qualify(name)} ({names}) VALUES ({self.params(len(columns))})",
                             rows)
