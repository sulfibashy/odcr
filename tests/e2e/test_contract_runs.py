"""End-to-end contract runs, on every reachable adapter."""

from __future__ import annotations

import pytest

from odcr import samples
from odcr.contract import parse_contract
from odcr.runner import run_contract
from tests.conftest import contract_doc, drop, load, object_name, where

pytestmark = pytest.mark.e2e

SCHEMA_IDS = {"orders.order_id.required", "orders.order_id.unique", "orders.customer_id.required",
              "orders.status.required", "orders.status.invalidValues", "orders.amount.nullValues",
              "orders.order_date.required", "orders.rowCount", "orders.no_negative_amounts"}


def test_good_batch_passes_and_is_logged(db, config, webhook):
    name = object_name(db)
    phys = load(db, name, samples.GOOD)
    try:
        contract = parse_contract(contract_doc(db, phys, webhook.url))
        result = run_contract(contract, db, config, batch_id="batch-001")
        assert result.status == "pass", result.summary()
        run = result.objects[0]
        assert run.rows_checked == 4
        ran = {r.check_id for r in run.results if r.check_type != "schema"}
        assert SCHEMA_IDS <= ran, ran
        s = config.meta_schema
        assert db.meta_count(s, "validation_runs", {"run_id": run.run_id, "status": "pass"}) == 1
        assert db.meta_count(s, "check_results", {"run_id": run.run_id}) == len(run.results)
        assert db.meta_count(s, "quarantine_log", {"run_id": run.run_id}) == 0
        assert db.meta_count(s, "contracts", {"yaml_hash": contract.yaml_hash}) == 1
        assert webhook.calls == []
    finally:
        drop(db, name)


def test_bad_batch_fails_quarantines_and_notifies(db, config, webhook):
    name = object_name(db)
    phys = load(db, name, samples.BAD)
    try:
        result = run_contract(parse_contract(contract_doc(db, phys, webhook.url)), db, config, batch_id="batch-002")
        assert result.status == "fail"
        run = result.objects[0]
        assert {r.check_id for r in run.failed} == {
            "orders.customer_id.required", "orders.order_id.unique", "orders.status.invalidValues",
            "orders.no_negative_amounts"}, result.summary()
        by_id = {r.check_id: r for r in run.results}
        assert by_id["orders.order_id.unique"].actual == "1"
        assert by_id["orders.status.invalidValues"].actual == "1"
        s = config.meta_schema
        assert db.meta_count(s, "quarantine_log", {"run_id": run.run_id, "batch_id": "batch-002"}) == 1
        assert db.meta_count(s, "check_results", {"run_id": run.run_id, "status": "failed"}) == 4
        assert sorted(c["path"] for c in webhook.calls) == ["/platform", "/source"]
        assert [d.status for d in result.notifications] == ["sent", "sent"]
        assert db.meta_count(s, "notifications", {"run_id": run.run_id, "status": "sent"}) == 2
    finally:
        drop(db, name)


def test_batch_filter_checks_only_that_batch(db, config, webhook):
    name = object_name(db)
    phys = load(db, name, samples.ROWS)
    try:
        contract = parse_contract(contract_doc(db, phys, webhook.url))
        good = run_contract(contract, db, config, batch_id="batch-001", where=where(db, "batch-001"))
        bad = run_contract(contract, db, config, batch_id="batch-002", where=where(db, "batch-002"))
        assert good.status == "pass", good.summary()
        assert good.objects[0].rows_checked == 4
        assert bad.status == "fail" and bad.objects[0].rows_checked == 4
    finally:
        drop(db, name)


def test_warning_does_not_fail_or_quarantine(db, config, webhook):
    rows = samples.GOOD + [(5, 104, "NEW", None, samples.GOOD[0][4], "batch-001")]  # 20% NULL amount
    name = object_name(db)
    phys = load(db, name, rows)
    try:
        result = run_contract(parse_contract(contract_doc(db, phys, webhook.url)), db, config, batch_id="w")
        assert result.status == "warn", result.summary()
        run = result.objects[0]
        assert [r.check_id for r in run.warned] == ["orders.amount.nullValues"]
        assert run.warned[0].actual == "20%"
        assert db.meta_count(config.meta_schema, "quarantine_log", {"run_id": run.run_id}) == 0
        assert len(webhook.calls) == 2
        doc = contract_doc(db, phys, None, amount_null_severity="error")
        assert run_contract(parse_contract(doc), db, config, send_notifications=False).status == "fail"
    finally:
        drop(db, name)


def test_schema_drift_is_caught(db, config, webhook):
    columns = [("order_id", "integer"), ("customer_id", "integer"), ("status", "string"), ("amount", "string"),
               ("load_id", "string"), ("discount_code", "string")]
    name = object_name(db)
    phys = load(db, name, [(1, 101, "NEW", "10.5", "batch-001", "X1")], columns)
    try:
        result = run_contract(parse_contract(contract_doc(db, phys, webhook.url)), db, config)
        status = {r.check_id: r.status for r in result.objects[0].results}
        assert result.status == "fail"
        assert status["orders.order_date.exists"] == "failed"
        assert status["orders.amount.type"] == "failed"
        assert status["orders.order_date.required"] == "skipped"
        assert status["orders.no_extra_columns"] == "warning"
        assert status["orders.order_id.type"] == "passed"
    finally:
        drop(db, name)


def test_missing_object(db, config, webhook):
    phys = object_name(db, "does_not_exist_" + db.dialect)
    if db.dialect == "files":
        phys = phys.replace("part-0001.parquet", "*.parquet")
    result = run_contract(parse_contract(contract_doc(db, phys, webhook.url)), db, config)
    assert result.status == "fail"
    assert [r.check_id for r in result.objects[0].failed] == ["orders.exists"]


def test_platform_specific_rule_is_skipped_elsewhere(db, config):
    name = object_name(db)
    phys = load(db, name, samples.GOOD)
    try:
        doc = contract_doc(db, phys)
        doc["schema"][0]["quality"].append({"type": "custom", "name": "other_engine", "engine": "some-other-engine",
                                            "implementation": "x"})
        if db.kind == "sql":
            doc["schema"][0]["quality"].append({"type": "sql", "name": "broken", "query": "SELECT nonsense FROM"})
        result = run_contract(parse_contract(doc), db, config, send_notifications=False)
        res = {r.check_id: r for r in result.objects[0].results}
        assert res["other_engine"].status == "skipped"
        if db.kind == "sql":
            assert res["broken"].status == "error" and "could not run" in res["broken"].message
            assert result.status == "fail"
        else:
            assert result.status == "pass"
    finally:
        drop(db, name)


def test_on_fail_log_and_contract_registered_once(db, config):
    name = object_name(db)
    phys = load(db, name, samples.BAD)
    try:
        config.on_fail = "log"
        contract = parse_contract(contract_doc(db, phys))
        r1 = run_contract(contract, db, config, send_notifications=False)
        run_contract(contract, db, config, send_notifications=False)
        assert db.meta_count(config.meta_schema, "quarantine_log", {"run_id": r1.objects[0].run_id}) == 0
        assert db.meta_count(config.meta_schema, "contracts", {"yaml_hash": contract.yaml_hash}) == 1
    finally:
        drop(db, name)
