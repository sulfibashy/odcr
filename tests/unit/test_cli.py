from pathlib import Path

import yaml

from odcr.cli import main


def test_init_creates_starter_files(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    for rel in ("odcr.yaml", "contracts/orders.odcs.yaml", "reconciliations/orders.recon.yaml"):
        assert (tmp_path / rel).exists(), rel
    # second run does not overwrite
    (tmp_path / "odcr.yaml").write_text("custom: true\n")
    assert main(["init", str(tmp_path)]) == 0
    assert "custom" in (tmp_path / "odcr.yaml").read_text()
    assert "skip" in capsys.readouterr().out
    assert main(["init", str(tmp_path), "--force"]) == 0
    assert "connections" in (tmp_path / "odcr.yaml").read_text()


def test_lint_ok_and_failures(tmp_path, capsys):
    main(["init", str(tmp_path)])
    good = tmp_path / "contracts" / "orders.odcs.yaml"
    assert main(["lint", str(good)]) == 0
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"kind": "DataContract"}))
    assert main(["lint", str(good), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "missing required field 'id'" in out


def test_lint_warnings(tmp_path, capsys):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"apiVersion": "v3.0.2", "kind": "DataContract", "id": "x", "version": "1",
                                 "schema": [{"name": "t", "properties": [{"name": "a"}]}]}))
    assert main(["lint", str(p)]) == 0
    out = capsys.readouterr().out
    assert "no logicalType" in out and "will not be notified" in out


def test_run_with_missing_contract_or_connection(tmp_path, capsys):
    main(["init", str(tmp_path)])
    cfg = str(tmp_path / "odcr.yaml")
    assert main(["run", str(tmp_path / "nope.yaml"), "-c", cfg, "-C", "postgres-dev"]) == 2
    contract = str(tmp_path / "contracts" / "orders.odcs.yaml")
    assert main(["run", contract, "-c", cfg, "-C", "unknown-conn"]) == 2
    assert "not found" in capsys.readouterr().err


def test_templates_are_packaged():
    from importlib import resources
    names = {p.name for p in resources.files("odcr.templates").iterdir()}
    assert {"contract.odcs.yaml", "odcr.yaml", "reconciliation.yaml"} <= names
    assert Path(__file__).exists()
