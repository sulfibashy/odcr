"""Microsoft SQL Server family: SQL Server (on-premise), Azure SQL Database, Azure SQL Managed Instance,
Azure Synapse Analytics (dedicated SQL pools) and Microsoft Fabric Warehouse.

Two Python clients are supported:
  client: pyodbc   (default) needs the Microsoft ODBC Driver 18; supports Entra ID authentication
  client: pytds    pure Python, no ODBC driver needed
"""

from __future__ import annotations

from typing import Any

from .base import Adapter


class SQLServerAdapter(Adapter):
    dialect = "sqlserver"
    quote_open, quote_close = "[", "]"
    default_schema_sql = "SELECT SCHEMA_NAME()"
    ignore_errors = ("there is already an object named", "already exists")

    def __init__(self, **options: Any):
        super().__init__(**options)
        self.client = str(options.get("client", "pyodbc")).lower()
        self.paramstyle = "format" if self.client == "pytds" else "qmark"
        self.driver = "pytds" if self.client == "pytds" else "pyodbc"

    def _connect(self) -> Any:
        o = self.options
        if self.client == "pytds":
            try:
                import pytds
            except ImportError as exc:  # pragma: no cover
                raise ImportError("SQL Server (pytds) support needs: pip install odcr-sqlserver") from exc
            return pytds.connect(server=o.get("host", "localhost"), port=int(o.get("port", 1433)),
                                 database=o.get("database", "master"), user=o.get("user") or o.get("username"),
                                 password=o.get("password", ""), autocommit=True)
        try:
            import pyodbc
        except ImportError as exc:  # pragma: no cover
            raise ImportError("SQL Server support needs: pip install odcr-sqlserver and the Microsoft "
                              "ODBC Driver 18, or set client: pytds") from exc
        if o.get("connection_string"):
            return pyodbc.connect(o["connection_string"], autocommit=True)
        parts = [
            f"DRIVER={{{o.get('driver', 'ODBC Driver 18 for SQL Server')}}}",
            f"SERVER={o.get('host', 'localhost')},{int(o.get('port', 1433))}",
            f"DATABASE={o.get('database', 'master')}",
            f"Encrypt={o.get('encrypt', 'yes')}",
            f"TrustServerCertificate={'yes' if o.get('trust_server_certificate', False) else 'no'}",
        ]
        if o.get("authentication"):  # e.g. ActiveDirectoryInteractive, ActiveDirectoryMsi, ActiveDirectoryPassword
            parts.append(f"Authentication={o['authentication']}")
        if o.get("user") or o.get("username"):
            parts += [f"UID={o.get('user') or o.get('username')}", f"PWD={o.get('password', '')}"]
        return pyodbc.connect(";".join(parts), autocommit=True)

    def limit(self, select_sql: str, n: int) -> str:
        if select_sql.upper().startswith("SELECT DISTINCT "):
            return f"SELECT DISTINCT TOP {int(n)} " + select_sql[16:]
        return f"SELECT TOP {int(n)} " + select_sql[7:]

    def create_schema_sql(self, schema: str) -> str:
        name = schema.replace("'", "''")
        return f"IF SCHEMA_ID('{name}') IS NULL EXEC('CREATE SCHEMA {self.quote(schema)}')"

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        name = table.replace("'", "''")
        return f"IF OBJECT_ID('{name}', 'U') IS NULL CREATE TABLE {table} ({columns_sql})"

    def meta_types(self) -> dict[str, str]:
        return {"id": "NVARCHAR(64)", "name": "NVARCHAR(255)", "short": "NVARCHAR(32)", "text": "NVARCHAR(4000)",
                "ts": "DATETIME2", "int": "BIGINT", "num": "FLOAT"}


class SynapseAdapter(SQLServerAdapter):
    """Azure Synapse Analytics dedicated SQL pool: meta tables are HEAP tables (no MAX columns)."""

    dialect = "synapse"

    def create_table_sql(self, table: str, columns_sql: str) -> str:
        name = table.replace("'", "''")
        return f"IF OBJECT_ID('{name}') IS NULL CREATE TABLE {table} ({columns_sql}) WITH (HEAP)"


class FabricWarehouseAdapter(SQLServerAdapter):
    """Microsoft Fabric Warehouse / SQL analytics endpoint: VARCHAR only, DATETIME2(6)."""

    dialect = "fabric"

    def meta_types(self) -> dict[str, str]:
        return {"id": "VARCHAR(64)", "name": "VARCHAR(255)", "short": "VARCHAR(32)", "text": "VARCHAR(4000)",
                "ts": "DATETIME2(6)", "int": "BIGINT", "num": "FLOAT"}

    def sample_types(self) -> dict[str, str]:
        return {"integer": "INT", "string": "VARCHAR(50)", "decimal": "DECIMAL(12,2)", "date": "DATE"}
