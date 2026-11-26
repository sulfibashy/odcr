"""Base adapter: the small interface every platform implements.

To add a platform, subclass `Adapter`, set `dialect`, `placeholder` and
`default_schema_sql`, implement `_connect`, and override any SQL that
differs (see the PostgreSQL, MySQL and SQL Server adapters).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

# Physical types accepted for each ODCS logicalType (matched on information_schema.data_type).
TYPE_FAMILIES: dict[str, set[str]] = {
    "integer": {"int", "integer", "bigint", "smallint", "tinyint", "mediumint", "int2", "int4", "int8",
                "serial", "bigserial"},
    "number": {"int", "integer", "bigint", "smallint", "tinyint", "mediumint", "numeric", "decimal",
               "double", "double precision", "float", "real", "money", "smallmoney", "int2", "int4",
               "int8", "float4", "float8"},
    "string": {"char", "varchar", "text", "character", "character varying", "nvarchar", "nchar", "ntext",
               "tinytext", "mediumtext", "longtext", "string", "uuid", "enum", "citext"},
    "date": {"date"},
    "timestamp": {"timestamp", "datetime", "datetime2", "smalldatetime", "datetimeoffset",
                  "timestamp with time zone", "timestamp without time zone", "timestamptz"},
    "boolean": {"bool", "boolean", "bit", "tinyint"},
}


def type_matches(logical_type: str | None, data_type: str) -> bool | None:
    """True/False when the logical type is checkable, None when it is not."""
    if not logical_type:
        return None
    family = TYPE_FAMILIES.get(logical_type.lower())
    if family is None:
        return None
    dt = data_type.lower().strip()
    return dt in family or any(dt.startswith(k + " ") or dt.startswith(k + "(") for k in family)


class Adapter:
    dialect = "generic"
    placeholder = "%s"
    default_schema_sql = "SELECT current_schema()"

    def __init__(self, **options: Any):
        self.options = options
        self.conn: Any = None

    # -- connection -------------------------------------------------
    def _connect(self) -> Any:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def connect(self) -> "Adapter":
        if self.conn is None:
            self.conn = self._connect()
        return self

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def __enter__(self) -> "Adapter":
        return self.connect()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- SQL helpers ------------------------------------------------
    def quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def qualify(self, name: str) -> str:
        return ".".join(self.quote(part) for part in name.split("."))

    def params(self, n: int) -> str:
        return ", ".join([self.placeholder] * n)

    def limit(self, select_sql: str, n: int) -> str:
        return f"{select_sql} LIMIT {int(n)}"

    def cursor(self) -> Any:
        self.connect()
        return self.conn.cursor()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        cur = self.cursor()
        try:
            if params:
                cur.execute(sql, tuple(params))
            else:
                cur.execute(sql)
        finally:
            cur.close()

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        rows = [tuple(r) for r in rows]
        if not rows:
            return
        cur = self.cursor()
        try:
            cur.executemany(sql, rows)
        finally:
            cur.close()

    def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        cur = self.cursor()
        try:
            cur.execute(sql, tuple(params)) if params else cur.execute(sql)
            return [tuple(r) for r in cur.fetchall()]
        finally:
            cur.close()

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.fetchall(sql, params)
        return rows[0][0] if rows else None

    # -- metadata ---------------------------------------------------
    def split_name(self, name: str) -> tuple[str, str]:
        parts = name.split(".")
        if len(parts) >= 2:
            return parts[-2], parts[-1]
        return str(self.scalar(self.default_schema_sql)), parts[0]

    def columns(self, object_name: str) -> dict[str, str]:
        """Column name (lower case) -> data type (lower case); empty when the table is missing."""
        schema, table = self.split_name(object_name)
        sql = (
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema = {self.placeholder} AND table_name = {self.placeholder}"
        )
        return {str(c).lower(): str(t).lower() for c, t in self.fetchall(sql, (schema, table))}

    def create_schema(self, schema: str) -> None:
        self.execute(f"CREATE SCHEMA IF NOT EXISTS {self.quote(schema)}")

    def create_table_sql(self, table: str, columns_sql: str) -> list[str]:
        return [f"CREATE TABLE IF NOT EXISTS {table} ({columns_sql})"]

    # Column types used for meta tables
    def meta_types(self) -> dict[str, str]:
        return {
            "id": "VARCHAR(64)",
            "name": "VARCHAR(255)",
            "short": "VARCHAR(32)",
            "text": "TEXT",
            "ts": "TIMESTAMP",
            "int": "BIGINT",
            "num": "DOUBLE PRECISION",
        }

    def insert(self, table: str, row: dict[str, Any]) -> None:
        cols = ", ".join(self.quote(c) for c in row)
        self.execute(f"INSERT INTO {table} ({cols}) VALUES ({self.params(len(row))})", list(row.values()))

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        keys = list(rows[0].keys())
        cols = ", ".join(self.quote(c) for c in keys)
        self.executemany(
            f"INSERT INTO {table} ({cols}) VALUES ({self.params(len(keys))})",
            [[r.get(k) for k in keys] for r in rows],
        )
