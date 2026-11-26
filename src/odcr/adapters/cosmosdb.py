"""Azure Cosmos DB for NoSQL adapter (azure-cosmos).

Objects are containers in `database`. Batch filters (`where`) are Cosmos SQL conditions on the alias `c`,
e.g. "c.load_id = '42'". Write platform-specific rules as ODCS custom rules:

    - type: custom
      engine: cosmosdb
      implementation: "c.amount < 0"          # condition: counts matching items
      mustBe: 0

For Cosmos DB for MongoDB, use the `mongodb` adapter instead.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .base import UnsupportedCheck
from .document import DocumentAdapter, infer_columns

if TYPE_CHECKING:  # pragma: no cover
    from ..checks import Check

SYSTEM = ("id", "_rid", "_self", "_etag", "_attachments", "_ts")


def prop(column: str) -> str:
    """c["field"] (nested: c["a"]["b"]) — safe for any field name."""
    return "c" + "".join('["' + part.replace('"', '\\"') + '"]' for part in column.split("."))


def is_null(column: str) -> str:
    p = prop(column)
    return f"(NOT IS_DEFINED({p}) OR IS_NULL({p}))"


def not_null(column: str) -> str:
    p = prop(column)
    return f"(IS_DEFINED({p}) AND NOT IS_NULL({p}))"


def where_clause(*conditions: str | None) -> str:
    parts = [f"({c})" for c in conditions if c]
    return (" WHERE " + " AND ".join(parts)) if parts else ""


class CosmosDBAdapter(DocumentAdapter):
    dialect = "cosmosdb"
    driver = "azure.cosmos"
    sample_size = 500

    def _connect(self) -> Any:
        try:
            from azure.cosmos import CosmosClient
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Cosmos DB support needs: pip install 'odcr[cosmosdb]'") from exc
        o = self.options
        if o.get("connection_string"):
            return CosmosClient.from_connection_string(o["connection_string"])
        credential: Any = o.get("key")
        if not credential:
            from azure.identity import DefaultAzureCredential  # Entra ID / managed identity

            credential = DefaultAzureCredential()
        return CosmosClient(o["endpoint"], credential=credential,
                            connection_verify=bool(o.get("verify_ssl", True)))

    def _db(self, name: str | None = None) -> Any:
        self.connect()
        return self.conn.get_database_client(name or self.options.get("database", "odcr"))

    def _container(self, name: str, database: str | None = None) -> Any:
        return self._db(database).get_container_client(name)

    def _query(self, container: Any, sql: str, params: list[dict[str, Any]] | None = None) -> list[Any]:
        return list(container.query_items(sql, parameters=params or None, enable_cross_partition_query=True))

    def ping(self) -> bool:
        self.connect()
        list(self.conn.list_databases(max_item_count=1))
        return True

    def current_schema(self) -> str | None:
        return self.options.get("database", "odcr")

    def system_columns(self) -> tuple[str, ...]:
        return SYSTEM

    # ---------------------------------------------------------------- catalog and data
    def columns(self, name: str) -> dict[str, str]:
        try:
            docs = self._query(self._container(name), f"SELECT TOP {self.sample_size} * FROM c")
        except Exception:  # noqa: BLE001 - container does not exist
            return {}
        return infer_columns(docs, SYSTEM, iso_dates=True) or {"id": "string"}

    def count(self, name: str, where: Any = None) -> int:
        rows = self._query(self._container(name), "SELECT VALUE COUNT(1) FROM c" + where_clause(where))
        return int(rows[0]) if rows else 0

    def metric_query(self, check: Check) -> tuple[str, list[dict[str, Any]]]:
        col, args, metric, w = check.column, check.args, check.metric, check.where
        if metric == "rowCount":
            return "SELECT VALUE COUNT(1) FROM c" + where_clause(w), []
        if metric == "nullValues":
            return "SELECT VALUE COUNT(1) FROM c" + where_clause(w, is_null(col or "")), []
        if metric == "missingValues":
            missing = [m for m in args.get("missingValues", []) if m is not None]
            cond = is_null(col or "") + (f" OR ARRAY_CONTAINS(@missing, {prop(col or '')})" if missing else "")
            return ("SELECT VALUE COUNT(1) FROM c" + where_clause(w, cond),
                    [{"name": "@missing", "value": missing}] if missing else [])
        if metric == "invalidValues":
            cond = f"{not_null(col or '')} AND NOT ARRAY_CONTAINS(@valid, {prop(col or '')})"
            return ("SELECT VALUE COUNT(1) FROM c" + where_clause(w, cond),
                    [{"name": "@valid", "value": list(args.get("validValues", []))}])
        if metric == "duplicateValues":
            cols = [col] if col else list(args.get("properties", []))
            if not cols:
                raise ValueError("duplicateValues on an object needs arguments.properties")
            select = ", ".join(f"{prop(c)} AS k{i}" for i, c in enumerate(cols))
            conds = " AND ".join(not_null(c) for c in cols)
            group = ", ".join(prop(c) for c in cols)
            return f"SELECT {select}, COUNT(1) AS n FROM c{where_clause(w, conds)} GROUP BY {group}", []
        raise ValueError(f"Unsupported metric {metric}")

    def evaluate(self, check: Check) -> Any:
        container = self._container(check.physical_name)
        if check.metric:
            sql, params = self.metric_query(check)
            rows = self._query(container, sql, params)
            check.sql = sql
            if check.metric == "duplicateValues":
                return sum(int(r["n"]) - 1 for r in rows if int(r["n"]) > 1)
            return rows[0] if rows else 0
        if check.check_type == "custom" and check.engine in ("cosmosdb", "cosmos"):
            impl = str(check.query).strip()
            sql = impl if impl.upper().startswith("SELECT") else \
                "SELECT VALUE COUNT(1) FROM c" + where_clause(check.where, impl)
            check.sql = sql
            rows = self._query(container, sql)
            return rows[0] if rows else 0
        raise UnsupportedCheck(f"{check.check_type} rules do not run on Cosmos DB; use a custom rule "
                               "with engine: cosmosdb")

    def aggregate(self, name: str, where: Any, func: str, column: str | None) -> Any:
        container = self._container(name)
        if func == "rowCount":
            return self.count(name, where)
        if func == "nullCount":
            rows = self._query(container, "SELECT VALUE COUNT(1) FROM c" + where_clause(where, is_null(column or "")))
            return rows[0] if rows else 0
        if func == "distinctCount":
            return len([v for v in self.distinct_values(name, where, column or "", 10_000_000) if v is not None])
        fn = {"sum": "SUM", "min": "MIN", "max": "MAX"}[func]
        rows = self._query(container, f"SELECT VALUE {fn}({prop(column or '')}) FROM c" + where_clause(where))
        return rows[0] if rows else None

    def distinct_values(self, name: str, where: Any, column: str, limit: int) -> list[Any]:
        rows = self._query(self._container(name), f"SELECT DISTINCT VALUE {prop(column)} FROM c" + where_clause(where))
        return rows[:limit]

    # ---------------------------------------------------------------- meta (containers in the meta database)
    def meta_ensure(self, schema: str) -> None:
        if schema in self._meta_ready:
            return
        from azure.cosmos import PartitionKey

        from ..meta import TABLES

        self.connect()
        db = self.conn.create_database_if_not_exists(schema)
        for table in TABLES:
            db.create_container_if_not_exists(id=table, partition_key=PartitionKey(path="/id"))
        self._meta_ready.add(schema)

    @staticmethod
    def _json(value: Any) -> Any:
        if isinstance(value, (dt.datetime, dt.date)):
            return value.isoformat()
        return value

    def meta_insert(self, schema: str, table: str, rows: list[dict[str, Any]]) -> None:
        container = self._container(table, schema)
        for r in rows:
            container.upsert_item({"id": uuid.uuid4().hex, **{k: self._json(v) for k, v in r.items()}})

    def meta_count(self, schema: str, table: str, where: dict[str, Any] | None = None) -> int:
        conds = [f"{prop(k)} = @p{i}" for i, k in enumerate(where or {})]
        params = [{"name": f"@p{i}", "value": self._json(v)} for i, v in enumerate((where or {}).values())]
        rows = self._query(self._container(table, schema), "SELECT VALUE COUNT(1) FROM c" + where_clause(*conds),
                           params)
        return int(rows[0]) if rows else 0

    def meta_select(self, schema: str, table: str, columns: list[str], where: dict[str, Any] | None = None,
                    order_by: str | None = None, descending: bool = True,
                    limit: int | None = None) -> list[dict[str, Any]]:
        conds = [f"{prop(k)} = @p{i}" for i, k in enumerate(where or {})]
        params = [{"name": f"@p{i}", "value": self._json(v)} for i, v in enumerate((where or {}).values())]
        top = f"TOP {int(limit)} " if limit else ""
        sql = f"SELECT {top}* FROM c" + where_clause(*conds)
        if order_by:
            sql += f" ORDER BY {prop(order_by)} {'DESC' if descending else 'ASC'}"
        return [{c: doc.get(c) for c in columns} for doc in self._query(self._container(table, schema), sql, params)]

    # ---------------------------------------------------------------- sample data
    def drop_table(self, name: str) -> None:
        try:
            self._db().delete_container(name)
        except Exception:  # noqa: BLE001
            pass

    def create_sample(self, name: str, columns: list[tuple[str, str]], rows: list[Sequence[Any]]) -> None:
        from azure.cosmos import PartitionKey

        self.drop_table(name)
        self.connect()
        db = self.conn.create_database_if_not_exists(self.options.get("database", "odcr"))
        container = db.create_container_if_not_exists(id=name, partition_key=PartitionKey(path="/id"))
        for r in rows:
            doc = {c: self._json(self.to_doc_value(v)) for (c, _), v in zip(columns, r)}
            container.upsert_item({"id": uuid.uuid4().hex, **doc})
