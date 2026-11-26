"""Shared fixtures.

End-to-end tests connect to real databases. Defaults match docker-compose.yml; override with env vars:
  ODCR_PG_HOST/PORT/USER/PASSWORD/DATABASE, ODCR_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE,
  ODCR_MSSQL_HOST/PORT/USER/PASSWORD/DATABASE (SQL Server tests run only when ODCR_MSSQL_HOST is set).
Tests against a database that is not reachable are skipped, never failed.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from odcr.adapters import get_adapter
from odcr.config import Config


def _env(prefix: str, key: str, default: str) -> str:
    return os.environ.get(f"ODCR_{prefix}_{key}", default)


def connection_options(kind: str) -> dict[str, Any]:
    if kind == "postgres":
        return {"type": "postgres", "host": _env("PG", "HOST", "localhost"), "port": _env("PG", "PORT", "5432"),
                "user": _env("PG", "USER", "postgres"), "password": _env("PG", "PASSWORD", "postgres"),
                "database": _env("PG", "DATABASE", "odcr_test")}
    if kind == "mysql":
        return {"type": "mysql", "host": _env("MYSQL", "HOST", "127.0.0.1"), "port": _env("MYSQL", "PORT", "3306"),
                "user": _env("MYSQL", "USER", "odcr"), "password": _env("MYSQL", "PASSWORD", "odcr"),
                "database": _env("MYSQL", "DATABASE", "odcr_test")}
    if kind == "sqlserver":
        return {"type": "sqlserver", "host": _env("MSSQL", "HOST", "localhost"), "port": _env("MSSQL", "PORT", "1433"),
                "user": _env("MSSQL", "USER", "sa"), "password": _env("MSSQL", "PASSWORD", "Odcr_Passw0rd!"),
                "database": _env("MSSQL", "DATABASE", "master")}
    raise ValueError(kind)


def _reachable(kind: str) -> str | None:
    if kind == "sqlserver" and not os.environ.get("ODCR_MSSQL_HOST"):
        return "set ODCR_MSSQL_HOST to run SQL Server tests"
    try:
        a = get_adapter(connection_options(kind))
        a.connect()
        a.close()
        return None
    except Exception as exc:  # noqa: BLE001
        return f"{kind} not reachable: {exc}"


_REACH: dict[str, str | None] = {}


def require(kind: str) -> None:
    if kind not in _REACH:
        _REACH[kind] = _reachable(kind)
    if _REACH[kind]:
        pytest.skip(_REACH[kind])


@pytest.fixture(scope="session")
def meta_schema() -> str:
    return f"odcr_meta_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session", autouse=True)
def _cleanup_meta(meta_schema: str):
    yield
    for kind in ("postgres", "mysql"):
        if _REACH.get(kind, "unchecked") is None:
            a = get_adapter(connection_options(kind)).connect()
            try:
                if kind == "postgres":
                    a.execute(f'DROP SCHEMA IF EXISTS "{meta_schema}" CASCADE')
                else:
                    a.execute(f"DROP DATABASE IF EXISTS `{meta_schema}`")
            finally:
                a.close()


@pytest.fixture(params=["postgres", "mysql", "sqlserver"])
def db(request):
    """A connected adapter for each database that is reachable."""
    require(request.param)
    adapter = get_adapter(connection_options(request.param))
    adapter.connect()
    yield adapter
    adapter.close()


@pytest.fixture
def table_name() -> str:
    return f"orders_{uuid.uuid4().hex[:10]}"


class Webhook:
    """A local HTTP endpoint that records every JSON POST (stands in for Slack/Teams)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.calls.append({"path": self.path, "json": json.loads(body or b"{}")})
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):  # silence
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def webhook():
    w = Webhook()
    yield w
    w.close()


@pytest.fixture
def config(meta_schema: str, webhook: Webhook) -> Config:
    return Config(
        meta_schema=meta_schema,
        notifications={"notify_on": ["fail", "warn"],
                       "platform_team": [{"type": "webhook", "url": f"{webhook.url}/platform"}]},
    )


# ---- test data helpers -------------------------------------------------------------------------

def create_orders(adapter, name: str, rows: list[tuple], extra_column: bool = False,
                  drop_column: str | None = None, amount_type: str | None = None) -> None:
    q = adapter.quote
    text = "NVARCHAR(50)" if adapter.dialect == "sqlserver" else "VARCHAR(50)"
    cols = [
        ("order_id", "INTEGER"),
        ("customer_id", "INTEGER"),
        ("status", text),
        ("amount", amount_type or "DECIMAL(12,2)"),
        ("order_date", "DATE"),
        ("load_id", text),
    ]
    if drop_column:
        cols = [c for c in cols if c[0] != drop_column]
    if extra_column:
        cols.append(("discount_code", text))
    adapter.execute(f"DROP TABLE IF EXISTS {q(name)}")
    adapter.execute(f"CREATE TABLE {q(name)} ({', '.join(f'{q(c)} {t}' for c, t in cols)})")
    if rows:
        names = [c for c, _ in cols][: len(rows[0])]
        adapter.executemany(
            f"INSERT INTO {q(name)} ({', '.join(q(c) for c in names)}) VALUES ({adapter.params(len(names))})",
            rows)


def drop_table(adapter, name: str) -> None:
    adapter.execute(f"DROP TABLE IF EXISTS {adapter.quote(name)}")


GOOD_ROWS = [
    (1, 101, "NEW", 10.50, "2026-11-01", "A"),
    (2, 102, "PAID", 20.00, "2026-11-01", "A"),
    (3, 103, "SHIPPED", 30.25, "2026-11-02", "A"),
    (4, 101, "CANCELLED", 5.00, "2026-11-02", "A"),
]

BAD_ROWS = [
    (10, None, "NEW", 10.00, "2026-11-03", "B"),        # customer_id NULL (required)
    (11, 105, "LOST", 15.00, "2026-11-03", "B"),        # invalid status
    (11, 106, "PAID", -3.00, "2026-11-03", "B"),        # duplicate order_id + negative amount
    (12, 107, "PAID", 8.00, "2026-11-03", "B"),
]


def contract_doc(table: str, webhook_url: str | None = None, amount_null_severity: str = "warning") -> dict:
    doc = yaml.safe_load(
        (Path(__file__).parent.parent / "src" / "odcr" / "templates" / "contract.odcs.yaml").read_text())
    doc["schema"][0]["physicalName"] = table
    doc["schema"][0]["properties"].append({"name": "load_id", "logicalType": "string"})
    for p in doc["schema"][0]["properties"]:
        if p["name"] == "amount":
            p["quality"][0]["severity"] = amount_null_severity
    doc["support"] = [{"channel": "#source", "tool": "webhook", "url": f"{webhook_url}/source"}] if webhook_url else []
    return doc


def write_contract(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "contract.odcs.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path
