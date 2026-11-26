"""End-to-end: reconciliation (same platform and cross-platform), stage tracing, streaming micro-batches, CLI."""

from __future__ import annotations

import json

import pytest
import yaml

from odcr.adapters import get_adapter
from odcr.cli import main
from odcr.contract import parse_contract
from odcr.meta import table_name as meta_table
from odcr.observe import checkpoint, trace
from odcr.reconcile import parse_reconciliation, run_reconciliation
from odcr.runner import run_contract
from tests.conftest import GOOD_ROWS, connection_options, contract_doc, create_orders, drop_table, require

pytestmark = pytest.mark.e2e


def recon_spec(src: str, tgt: str, batch_filter: bool = True) -> dict:
    where = "load_id = '{batch_id}'" if batch_filter else None
    return {"kind": "Reconciliation", "id": "orders-recon",
            "source": {"object": src, "where": where}, "target": {"object": tgt, "where": where},
            "checks": [{"type": "rowCount"}, {"type": "sum", "column": "amount", "tolerance": 0.01},
                       {"type": "distinctCount", "column": "customer_id"}, {"type": "max", "column": "order_id"},
                       {"type": "nullCount", "column": "amount"}, {"type": "missingKeys", "column": "order_id"}]}


def test_reconcile_same_platform(db, config, webhook):
    src, tgt = "recon_src_" + db.dialect, "recon_tgt_" + db.dialect
    create_orders(db, src, GOOD_ROWS)
    create_orders(db, tgt, GOOD_ROWS)
    try:
        recon = parse_reconciliation(recon_spec(src, tgt))
        ok = run_reconciliation(recon, db, db, config, batch_id="A")
        assert ok.status == "pass", ok.summary()
        # lose one row and change an amount in the target
        q = db.quote
        db.execute(f"DELETE FROM {q(tgt)} WHERE {q('order_id')} = 4")
        db.execute(f"UPDATE {q(tgt)} SET {q('amount')} = 99 WHERE {q('order_id')} = 1")
        bad = run_reconciliation(recon, db, db, config, batch_id="A")
        assert bad.status == "fail"
        res = {r.check_id: r for r in bad.results}
        assert (res["rowCount"].source_value, res["rowCount"].target_value) == ("4", "3")
        assert res["sum(amount)"].status == "failed"
        assert res["max(order_id)"].status == "failed"
        assert "1 missing in target (e.g. 4)" in res["missingKeys(order_id)"].message
        assert res["nullCount(amount)"].status == "passed"
        assert len(webhook.calls) == 1 and webhook.calls[0]["path"] == "/platform"
        p = db.placeholder
        assert int(db.scalar(f"SELECT COUNT(*) FROM {meta_table(db, config.meta_schema, 'reconciliation_results')} "
                             f"WHERE run_id = {p} AND status = 'failed'", [bad.run_id])) == 4
    finally:
        drop_table(db, src)
        drop_table(db, tgt)


def test_reconcile_postgres_to_mysql(config, webhook):
    require("postgres")
    require("mysql")
    pg = get_adapter(connection_options("postgres")).connect()
    my = get_adapter(connection_options("mysql")).connect()
    try:
        create_orders(pg, "xrecon_orders", GOOD_ROWS)
        create_orders(my, "xrecon_orders", GOOD_ROWS)
        recon = parse_reconciliation(recon_spec("xrecon_orders", "xrecon_orders"))
        assert run_reconciliation(recon, pg, my, config, batch_id="A").status == "pass"
        my.execute("DELETE FROM `xrecon_orders` WHERE `order_id` = 2")
        res = run_reconciliation(recon, pg, my, config, batch_id="A")
        assert res.status == "fail"
        assert {r.check_id for r in res.results if r.status == "failed"} == {
            "rowCount", "sum(amount)", "distinctCount(customer_id)", "missingKeys(order_id)"}
        # results are stored in the target platform (MySQL) by default
        assert int(my.scalar(f"SELECT COUNT(*) FROM `{config.meta_schema}`.`reconciliation_runs` "
                             f"WHERE run_id = %s", [res.run_id])) == 1
    finally:
        drop_table(pg, "xrecon_orders")
        drop_table(my, "xrecon_orders")
        pg.close()
        my.close()


def test_trace_batch_through_stages(db, config, table_name, webhook):
    """source -> ingestion (contract check) -> silver -> gold; gold loses rows and is flagged."""
    create_orders(db, table_name, GOOD_ROWS)
    try:
        pipe = f"orders_pipeline_{table_name}"
        checkpoint(db, pipeline=pipe, stage="source", batch_id="A", row_count=4, config=config)
        run_contract(parse_contract(contract_doc(table_name, webhook.url)), db, config, batch_id="A",
                     where="load_id = 'A'", pipeline=pipe, stage="ingestion")
        checkpoint(db, pipeline=pipe, stage="silver", batch_id="A", object_name=table_name,
                   where="load_id = 'A'", config=config)
        checkpoint(db, pipeline=pipe, stage="gold", batch_id="A", row_count=3, config=config)
        checkpoint(db, pipeline=pipe, stage="consumption", batch_id="A", row_count=3, config=config)
        steps = trace(db, pipeline=pipe, batch_id="A", config=config)
        assert [s.stage for s in steps] == ["source", "ingestion", "silver", "gold", "consumption"]
        assert [s.row_count for s in steps] == [4, 4, 4, 3, 3]
        assert [s.flag for s in steps] == ["", "", "", "lost 1 rows", ""]
        assert steps[1].status == "pass"
        assert trace(db, pipeline=pipe, batch_id="A", config=config, tolerance=1)[3].flag == ""
    finally:
        drop_table(db, table_name)


def test_streaming_microbatches(db, config, table_name, webhook):
    """Simulate a CDC / Event Hub stream: each micro-batch is checked and checkpointed as it lands."""
    create_orders(db, table_name, [])
    contract = parse_contract(contract_doc(table_name, webhook.url))
    q = db.quote
    insert = (f"INSERT INTO {q(table_name)} ({', '.join(q(c) for c in ['order_id', 'customer_id', 'status', 'amount', 'order_date', 'load_id'])}) "
              f"VALUES ({db.params(6)})")
    batches = {
        "offset-0-99": [(1, 1, "NEW", 1.0, "2026-11-01", "offset-0-99"), (2, 2, "PAID", 2.0, "2026-11-01", "offset-0-99")],
        "offset-100-199": [(3, 3, "NEW", 3.0, "2026-11-01", "offset-100-199")],
        "offset-200-299": [(4, None, "NEW", 4.0, "2026-11-01", "offset-200-299")],  # bad event
    }
    try:
        statuses = {}
        for batch_id, rows in batches.items():
            db.executemany(insert, rows)
            checkpoint(db, pipeline="orders_stream", stage="queue", batch_id=batch_id, row_count=len(rows),
                       mode="streaming", config=config)
            res = run_contract(contract, db, config, batch_id=batch_id, where=f"load_id = '{batch_id}'",
                               pipeline="orders_stream", stage="bronze", send_notifications=False)
            statuses[batch_id] = res.status
        assert statuses == {"offset-0-99": "pass", "offset-100-199": "pass", "offset-200-299": "fail"}
        steps = trace(db, pipeline="orders_stream", batch_id="offset-200-299", config=config)
        assert [(s.stage, s.mode, s.row_count, s.status) for s in steps] == [
            ("queue", "streaming", 1, "ok"), ("bronze", "batch", 1, "fail")]
        assert "stage status fail" in steps[1].flag
    finally:
        drop_table(db, table_name)


def _write_config(tmp_path, kind, config, webhook):
    cfg = {"connections": {"db": connection_options(kind)}, "meta": {"schema": config.meta_schema},
           "notifications": {"notify_on": ["fail"], "platform_team": [{"type": "webhook", "url": webhook.url}]}}
    path = tmp_path / "odcr.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return str(path)


def test_cli_end_to_end(db, config, table_name, webhook, tmp_path, capsys):
    kind = {"postgres": "postgres", "mysql": "mysql", "sqlserver": "sqlserver"}[db.dialect]
    cfg = _write_config(tmp_path, kind, config, webhook)
    create_orders(db, table_name, GOOD_ROWS)
    contract = tmp_path / "orders.odcs.yaml"
    contract.write_text(yaml.safe_dump(contract_doc(table_name, None)))
    try:
        assert main(["meta-init", "-c", cfg, "-C", "db"]) == 0
        assert main(["run", str(contract), "-c", cfg, "-C", "db", "--batch-id", "A", "--where", "load_id = 'A'",
                     "--pipeline", f"p_{table_name}", "--stage", "ingestion"]) == 0
        capsys.readouterr()
        db.execute(f"UPDATE {db.quote(table_name)} SET {db.quote('status')} = 'BROKEN'")
        assert main(["run", str(contract), "-c", cfg, "-C", "db", "--batch-id", "A2", "--json"]) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "fail" and out["notifications"][0]["status"] == "sent"
        assert main(["history", "-c", cfg, "-C", "db", "--contract-id", "orders", "--limit", "2", "--json"]) == 0
        hist = json.loads(capsys.readouterr().out)
        assert [h["status"] for h in hist] == ["fail", "pass"]
        assert main(["checkpoint", "-c", cfg, "-C", "db", "--pipeline", f"p_{table_name}", "--stage", "gold",
                     "--batch-id", "A", "--rows", "2"]) == 0
        capsys.readouterr()
        assert main(["trace", "-c", cfg, "-C", "db", "--pipeline", f"p_{table_name}", "--batch-id", "A"]) == 1
        assert "lost 2 rows" in capsys.readouterr().out
        spec = tmp_path / "recon.yaml"
        spec.write_text(yaml.safe_dump(recon_spec(table_name, table_name, batch_filter=False)))
        assert main(["reconcile", str(spec), "-c", cfg, "--source", "db", "--target", "db"]) == 0
    finally:
        drop_table(db, table_name)
