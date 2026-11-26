"""Microsoft SQL Server / Azure SQL adapter (pyodbc + Microsoft ODBC Driver 18)."""

from __future__ import annotations

from typing import Any

from .base import Adapter


class SQLServerAdapter(Adapter):
    dialect = "sqlserver"
    placeholder = "?"
    default_schema_sql = "SELECT SCHEMA_NAME()"

    def _connect(self) -> Any:
        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover
            raise ImportError("SQL Server support needs: pip install 'odcr[sqlserver]'") from exc
        o = self.options
        if o.get("connection_string"):
            return pyodbc.connect(o["connection_string"], autocommit=True)
        driver = o.get("driver", "ODBC Driver 18 for SQL Server")
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={o.get('host', 'localhost')},{int(o.get('port', 1433))}",
            f"DATABASE={o.get('database', 'master')}",
            f"UID={o.get('user') or o.get('username')}",
            f"PWD={o.get('password', '')}",
            f"TrustServerCertificate={'yes' if o.get('trust_server_certificate', True) else 'no'}",
        ]
        return pyodbc.connect(";".join(parts), autocommit=True)

    def quote(self, identifier: str) -> str:
        return "[" + identifier.replace("]", "]]") + "]"

    def limit(self, select_sql: str, n: int) -> str:
        assert select_sql.upper().startswith("SELECT ")
        return f"SELECT TOP {int(n)} " + select_sql[7:]

    def create_schema(self, schema: str) -> None:
        name = schema.replace("'", "''")
        self.execute(f"IF SCHEMA_ID('{name}') IS NULL EXEC('CREATE SCHEMA {self.quote(schema)}')")

    def create_table_sql(self, table: str, columns_sql: str) -> list[str]:
        name = table.replace("'", "''")
        return [f"IF OBJECT_ID('{name}', 'U') IS NULL CREATE TABLE {table} ({columns_sql})"]

    def meta_types(self) -> dict[str, str]:
        return {
            "id": "NVARCHAR(64)",
            "name": "NVARCHAR(255)",
            "short": "NVARCHAR(32)",
            "text": "NVARCHAR(MAX)",
            "ts": "DATETIME2",
            "int": "BIGINT",
            "num": "FLOAT",
        }
