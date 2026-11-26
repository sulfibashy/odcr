from pathlib import Path

import pytest
import yaml

from odcr.contract import ContractError, load_contract, parse_contract

TEMPLATE = Path(__file__).parents[2] / "src" / "odcr" / "templates" / "contract.odcs.yaml"


def base_doc(**overrides):
    doc = {"apiVersion": "v3.0.2", "kind": "DataContract", "id": "c1", "version": "1.0.0",
           "schema": [{"name": "t", "properties": [{"name": "a", "logicalType": "integer"}]}]}
    doc.update(overrides)
    return doc


def test_template_loads():
    c = load_contract(TEMPLATE)
    assert c.id == "orders" and c.version == "1.0.0"
    assert c.owner == "order-team-lead"
    obj = c.object("orders")
    assert [p.name for p in obj.properties] == ["order_id", "customer_id", "status", "amount", "order_date"]
    assert obj.properties[0].primary_key
    assert {r.metric for r in obj.quality if r.type == "library"} == {"rowCount"}
    assert any(r.type == "sql" for r in obj.quality)


def test_hash_changes_with_content(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(base_doc()))
    h1 = load_contract(p).yaml_hash
    p.write_text(yaml.safe_dump(base_doc(version="1.0.1")))
    assert load_contract(p).yaml_hash != h1


@pytest.mark.parametrize("missing", ["apiVersion", "kind", "id", "version", "schema"])
def test_required_fields(missing):
    doc = base_doc()
    doc.pop(missing)
    with pytest.raises(ContractError) as exc:
        parse_contract(doc)
    assert any(missing in p for p in exc.value.problems)


def test_rejects_non_v3_and_wrong_kind():
    with pytest.raises(ContractError) as exc:
        parse_contract(base_doc(apiVersion="v2.2.2", kind="Other"))
    joined = " ".join(exc.value.problems)
    assert "not ODCS v3" in joined and "kind must be DataContract" in joined


def test_odcs_30_rule_aliases_and_default_comparator():
    doc = base_doc()
    doc["schema"][0]["properties"][0]["quality"] = [
        {"rule": "nullCheck"},
        {"rule": "duplicateCount", "mustBeLessThan": 2},
        {"rule": "validValues", "validValues": [1, 2]},
    ]
    rules = parse_contract(doc).schema[0].properties[0].quality
    assert [r.metric for r in rules] == ["nullValues", "duplicateValues", "invalidValues"]
    assert (rules[0].comparator, rules[0].threshold) == ("mustBe", 0)
    assert (rules[1].comparator, rules[1].threshold) == ("mustBeLessThan", 2)
    assert rules[2].arguments["validValues"] == [1, 2]


@pytest.mark.parametrize("rule,problem", [
    ({"type": "library"}, "needs 'metric'"),
    ({"type": "library", "metric": "nope"}, "unsupported metric"),
    ({"type": "library", "metric": "invalidValues"}, "validValues"),
    ({"type": "sql"}, "needs 'query'"),
    ({"type": "weird"}, "unknown quality type"),
    ({"type": "library", "metric": "rowCount"}, "rowCount needs a comparator"),
    ({"type": "library", "metric": "nullValues", "mustBeBetween": 3}, "list of two numbers"),
])
def test_invalid_quality_rules(rule, problem):
    doc = base_doc()
    doc["schema"][0]["quality"] = [rule]
    with pytest.raises(ContractError) as exc:
        parse_contract(doc)
    assert any(problem in p for p in exc.value.problems), exc.value.problems


@pytest.mark.parametrize("value,expected", [("warning", "warning"), ("warn", "warning"), ("info", "warning"),
                                            ("error", "error"), ("critical", "error"), (None, "error")])
def test_severity_mapping(value, expected):
    doc = base_doc()
    rule = {"type": "library", "metric": "nullValues"}
    if value:
        rule["severity"] = value
    doc["schema"][0]["properties"][0]["quality"] = [rule]
    assert parse_contract(doc).schema[0].properties[0].quality[0].severity == expected


def test_support_contacts_with_env_interpolation(monkeypatch):
    monkeypatch.setenv("SRC_HOOK", "https://hooks.example.com/abc")
    doc = base_doc(support=[
        {"channel": "#a", "tool": "slack", "url": "${SRC_HOOK}"},
        {"channel": "#b", "tool": "teams", "url": "${UNSET_HOOK}"},          # empty -> skipped
        {"channel": "team@example.com", "tool": "email"},
        {"channel": "x", "tool": "email", "url": "mailto:x@example.com"},
    ])
    contacts = parse_contract(doc).contacts
    assert [(c.kind, c.target) for c in contacts] == [
        ("slack", "https://hooks.example.com/abc"), ("email", "team@example.com"), ("email", "x@example.com")]


def test_missing_file_and_bad_yaml(tmp_path):
    with pytest.raises(ContractError):
        load_contract(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    with pytest.raises(ContractError):
        load_contract(bad)


def test_object_lookup_by_physical_name():
    doc = base_doc()
    doc["schema"][0]["physicalName"] = "sales.t_raw"
    c = parse_contract(doc)
    assert c.object("sales.t_raw").name == "t"
    with pytest.raises(KeyError):
        c.object("missing")
