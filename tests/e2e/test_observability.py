"""End-to-end reconciliation, tracing, streaming micro-batches and watch, on every reachable adapter."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from odcr import samples
from odcr.adapters import get_adapter
from odcr.config import Config
from odcr.contract import parse_contract
from odcr.observe import checkpoint, trace
from odcr.reconcile import parse_reconciliation, run_reconciliation
from odcr.runner import run_contract
from odcr.watch import watch_once
from tests.conftest import connection_options, contract_doc, drop, load, object_name, require, where

pytestmark = pytest.mark.e2e


def recon_spec(src: str, tgt: str, src_where=None, tgt_where=None) -> dict:
    return {"kind": "Reconciliation", "id": "orders-recon",
            "source": {"object": src, "where": src_where}, "target": {"object": tgt, "where": tgt_where},
            "checks": [{"type": "rowCount"}, {"type": "sum", "column": "amount", "tolerance": 0.01},
                       {"type": "distinctCount", "column": "customer_id"}, {"type": "max", "column": "order_id"},
                       {"type": "nullCount", "column": "amount"}, {"type": "missingKeys", "column": "order_id"}]}


def test_reconcile_same_platform(db, config, webhook):
    src, tgt, bad = object_name(db), object_name(db), object_name(db)
    src_p = load(db, src, samples.GOOD)
    tgt_p = load(db, tgt, samples.GOOD)
    changed = [samples.GOOD[0][:3] + (Decimal("99.00"),) + samples.GOOD[0][4:]] + samples.GOOD[1:3]  # row 4 lost
    bad_p = load(db, bad, changed)
    try:
        ok = run_reconciliation(parse_reconciliation(recon_spec(src_p, tgt_p)), db, db, config, batch_id="A")
        assert ok.status == "pass", ok.summary()
        res = run_reconciliation(parse_reconciliation(recon_spec(src_p, bad_p)), db, db, config, batch_id="A")
        assert res.status == "fail"
        by = {r.check_id: r for r in res.results}
        assert (by["rowCount"].source_value, by["rowCount"].target_value) == ("4", "3")
        assert by["sum(amount)"].status == "failed"
        assert by["max(order_id)"].status == "failed"
        assert "1 missing in target (e.g. 4)" in by["missingKeys(order_id)"].message
        assert by["nullCount(amount)"].status == "passed"
        assert len(webhook.calls) == 1 and webhook.calls[0]["path"] == "/platform"
        assert db.meta_count(config.meta_schema, "reconciliation_results", {"run_id": res.run_id, "status": "failed"}) == 4
    finally:
        for n in (src, tgt, bad):
            drop(db, n)


@pytest.mark.parametrize("source,target", [("duckdb", "sqlite"), ("postgres", "mysql"), ("mongodb", "duckdb"),
                                           ("files", "postgres"), ("sqlserver", "postgres"), ("oracle", "postgres"),
                                           ("trino", "duckdb")])
def test_reconcile_across_platforms(source, target, config, session_tmp):
    s_opts, t_opts = require(source, session_tmp), require(target, session_tmp)
    s, t = get_adapter(s_opts).connect(), get_adapter(t_opts).connect()
    s.test_tmp = t.test_tmp = session_tmp
    s_name, t_name = object_name(s), object_name(t)
    try:
        s_p = load(s, s_name, samples.ROWS)
        t_p = load(t, t_name, samples.ROWS[:-1])  # the last row never arrived
        spec = recon_spec(s_p, t_p, where(s, "batch-002"), where(t, "batch-002"))
        res = run_reconciliation(parse_reconciliation(spec), s, t, config, batch_id="batch-002",
                                 send_notifications=False)
        failed = {r.check_id for r in res.results if r.status != "passed"}
        assert failed == {"rowCount", "sum(amount)", "distinctCount(customer_id)", "max(order_id)",
                          "missingKeys(order_id)"}, res.summary()
        assert t.meta_count(config.meta_schema, "reconciliation_runs", {"run_id": res.run_id}) == 1
    finally:
        drop(s, s_name)
        drop(t, t_name)
        s.close()
        t.close()


def test_trace_batch_through_stages(db, config, webhook):
    name = object_name(db)
    phys = load(db, name, samples.GOOD)
    pipe = f"pipe_{name[-12:]}"
    try:
        checkpoint(db, pipeline=pipe, stage="source", batch_id="A", row_count=4, config=config)
        run_contract(parse_contract(contract_doc(db, phys, webhook.url)), db, config, batch_id="A",
                     where=where(db, "batch-001"), pipeline=pipe, stage="ingestion")
        checkpoint(db, pipeline=pipe, stage="silver", batch_id="A", object_name=phys, where=where(db, "batch-001"),
                   config=config)
        checkpoint(db, pipeline=pipe, stage="gold", batch_id="A", row_count=3, config=config)
        checkpoint(db, pipeline=pipe, stage="consumption", batch_id="A", row_count=3, config=config)
        steps = trace(db, pipeline=pipe, batch_id="A", config=config)
        assert [s.stage for s in steps] == ["source", "ingestion", "silver", "gold", "consumption"]
        assert [s.row_count for s in steps] == [4, 4, 4, 3, 3]
        assert [s.flag for s in steps] == ["", "", "", "lost 1 rows", ""]
        assert steps[1].status == "pass"
    finally:
        drop(db, name)


def test_streaming_microbatches_with_watch(db, config):
    """Micro-batches (CDC / Event Hub / Kafka / file drops) land one after another; each is checked once."""
    contract_rows = {
        "offset-0-99": [(1, 1, "NEW", Decimal("1.00"), dt.date(2026, 11, 1), "offset-0-99"),
                        (2, 2, "PAID", Decimal("2.00"), dt.date(2026, 11, 1), "offset-0-99")],
        "offset-100-199": [(3, 3, "NEW", Decimal("3.00"), dt.date(2026, 11, 1), "offset-100-199")],
        "offset-200-299": [(4, None, "NEW", Decimal("4.00"), dt.date(2026, 11, 1), "offset-200-299")],  # bad
    }
    base = object_name(db)
    pipeline = f"stream_{base[-10:]}"
    created: list[str] = []
    try:
        seen: dict[str, str] = {}
        accumulated: list = []
        for i, (_batch, rows) in enumerate(contract_rows.items()):
            if db.dialect == "files":  # a new file per micro-batch
                name = base.replace("part-0001", f"part-{i:04d}")
                phys = load(db, name, rows)
                created.append(name)
                kwargs = {}
            else:  # rows appended to one table; the batch column tells micro-batches apart
                accumulated += rows
                phys = load(db, base, accumulated)
                created = [base]
                kwargs = {"batch_column": "load_id"}
            contract = parse_contract(contract_doc(db, phys))
            events = watch_once(contract, db, config, pipeline=pipeline, send_notifications=False, **kwargs)
            for e in events:
                seen[e.batch_id] = e.result.status
            assert len(events) == 1, [e.batch_id for e in events]  # only the new micro-batch is checked
        assert sorted(seen.values()) == ["fail", "pass", "pass"]
        again = watch_once(contract, db, config, pipeline=pipeline, send_notifications=False, **kwargs)
        assert again == []  # nothing new: nothing checked twice
    finally:
        for n in set(created):
            drop(db, n)


def test_meta_on_another_platform(config, session_tmp):
    """Read-only sources: data checked on one platform, results stored on another (meta.connection)."""
    data = get_adapter(require("duckdb", session_tmp)).connect()
    meta = get_adapter(connection_options("sqlite", session_tmp)).connect()
    data.test_tmp = session_tmp
    name = object_name(data)
    try:
        phys = load(data, name, samples.GOOD)
        res = run_contract(parse_contract(contract_doc(data, phys)), data, config, meta=meta, send_notifications=False)
        assert res.status == "pass"
        assert meta.meta_count(config.meta_schema, "validation_runs", {"run_id": res.objects[0].run_id}) == 1
    finally:
        drop(data, name)
        data.close()
        meta.close()


def test_config_type_alias(session_tmp):
    a = get_adapter({"type": "adls", "meta_path": str(session_tmp / "x.duckdb")})
    assert a.dialect == "files"
    assert isinstance(Config().meta_schema, str)
