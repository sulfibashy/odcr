"""Project scaffolding (odcr init), the contract repository, and the CLI end to end on SQLite/DuckDB/files."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from odcr.adapters import ADAPTERS
from odcr.cli import main
from odcr.config import load_config, parse_config
from odcr.contract import ContractError
from odcr.repository import ContractRepository, sync_git
from odcr.scaffold import PROMPT_ORDER, scaffold

EXPECTED = ["odcr.yaml", ".env.example", "contracts/sales/orders.odcs.yaml", "reconciliations/orders.recon.yaml",
            "seeds/orders.csv", "jobs/ingestion_gate.py", "jobs/ingestion_gate.sh", "jobs/ingestion_gate.ps1",
            "tests/test_contracts.py", ".github/workflows/contracts.yml", "azure-pipelines.yml", "README.md",
            ".gitignore", ".odcr/project.json"]


@pytest.mark.parametrize("adapter", sorted(ADAPTERS))
def test_scaffold_every_adapter(adapter, tmp_path):
    root = tmp_path / f"proj_{adapter}"
    written = scaffold(root, adapter=adapter, platform_channel="teams")
    assert sorted(str(p.relative_to(root)).replace("\\", "/") for p in written) == sorted(EXPECTED)
    config = parse_config(yaml.safe_load((root / "odcr.yaml").read_text()), base_dir=root)
    assert config.connection("main")["type"] == adapter
    assert config.platform_team[0]["type"] == "teams"
    repo = ContractRepository.from_config(config)
    assert list(repo.contracts) == ["orders"] and not repo.errors
    env = (root / ".env.example").read_text()
    for var in ("ORDERS_SLACK_WEBHOOK", "SMTP_HOST"):
        assert f"{var}=" in env
    compile((root / "jobs/ingestion_gate.py").read_text(), "ingestion_gate.py", "exec")
    yaml.safe_load((root / "reconciliations/orders.recon.yaml").read_text())
    assert "pip install" in (root / "README.md").read_text()


def test_scaffold_refuses_non_empty_dir_and_interactive(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "keep.txt").write_text("hi")
    with pytest.raises(FileExistsError):
        scaffold(tmp_path / "x")
    answers = iter(["my_proj", str(PROMPT_ORDER.index("snowflake") + 1), "dq_meta", "email", "dq@example.com",
                    "microsoft365", "alerts@acme.com"])
    scaffold(tmp_path / "y", interactive=True, reader=lambda _: next(answers))
    text = (tmp_path / "y" / "odcr.yaml").read_text()
    assert "name: my_proj" in text and "type: snowflake" in text and "schema: dq_meta" in text
    assert "dq@example.com" in text and "provider: microsoft365" in text and "from: alerts@acme.com" in text


def write_contract(path: Path, cid: str, physical: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"apiVersion": "v3.0.2", "kind": "DataContract", "id": cid, "version": "1",
                                    "schema": [{"name": cid, "physicalName": physical,
                                                "properties": [{"name": "a", "logicalType": "integer"}]}]}))


def test_repository_loading_and_lookup(tmp_path):
    write_contract(tmp_path / "sales" / "orders.odcs.yaml", "orders", "sales.orders")
    write_contract(tmp_path / "files" / "events.yaml", "events", "landing/events/*.parquet")
    write_contract(tmp_path / "dup.yaml", "orders", "x")
    (tmp_path / "bad.yaml").write_text("kind: DataContract\nid: x\n")
    (tmp_path / "other.yaml").write_text("kind: Reconciliation\n")
    (tmp_path / "broken.yaml").write_text("a: [")
    (tmp_path / ".hidden").mkdir()
    write_contract(tmp_path / ".hidden" / "h.yaml", "hidden", "h")
    repo = ContractRepository.load(tmp_path)
    assert sorted(repo.contracts) == ["events", "orders"]
    assert len(repo.errors) == 3
    assert repo.get("orders").schema[0].physical_name in ("sales.orders", "x")
    assert [c.id for c, _ in repo.find_by_object("landing/events/2026-11-26.parquet")] == ["events"]
    assert repo.find_by_object("ORDERS")
    with pytest.raises(ContractError):
        repo.get("nope")


@pytest.mark.skipif(not shutil.which("git"), reason="git not installed")
def test_repository_from_git(tmp_path, monkeypatch):
    monkeypatch.setenv("ODCR_CACHE_DIR", str(tmp_path / "cache"))
    src = tmp_path / "src"
    write_contract(src / "contracts" / "orders.odcs.yaml", "orders", "orders")
    run = lambda *a: subprocess.run(["git", *a], cwd=src, check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c")
    config = parse_config({"contracts": {"git": src.as_uri(), "ref": "main", "path": "contracts"}})
    assert list(ContractRepository.from_config(config).contracts) == ["orders"]
    write_contract(src / "contracts" / "events.odcs.yaml", "events", "events")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c2")
    assert sorted(ContractRepository.from_config(config).contracts) == ["events", "orders"]  # refreshed
    assert sync_git(src.as_uri(), "main").exists()


@pytest.mark.parametrize("adapter", ["sqlite", "duckdb", "files"])
def test_cli_quickstart_end_to_end(adapter, tmp_path, monkeypatch, capsys):
    """Exactly what the README tells a new user to do, on platforms that need no server."""
    root = tmp_path / "proj"
    assert main(["init", str(root), "--adapter", adapter, "--no-input", "--alerts", "none"]) == 0
    monkeypatch.chdir(root)
    monkeypatch.setenv("SQLITE_PATH", str(root / "db.sqlite"))
    monkeypatch.setenv("DUCKDB_PATH", str(root / "db.duckdb"))
    monkeypatch.setenv("ODCR_META_PATH", str(root / "meta.duckdb"))
    assert main(["doctor"]) == 0
    assert "settings:" in capsys.readouterr().out
    assert main(["meta-init"]) == 0
    assert main(["seed"]) == 0
    assert main(["lint"]) == 0
    assert main(["contracts", "--json"]) == 0
    capsys.readouterr()
    w1 = "load_id = 'batch-001'"
    w2 = "load_id = 'batch-002'"
    assert main(["run", "--contract-id", "orders", "--batch-id", "batch-001", "--where", w1, "--no-notify"]) == 0
    capsys.readouterr()
    assert main(["run", "--contract-id", "orders", "--batch-id", "batch-002", "--where", w2, "--json",
                 "--no-notify"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "fail"
    assert main(["run", "--for-object", "orders" if adapter != "files" else "landing/orders/x.parquet",
                 "--where", w1, "--no-notify"]) == 0
    capsys.readouterr()
    assert main(["history", "--contract-id", "orders", "--limit", "5", "--json"]) == 0
    hist = json.loads(capsys.readouterr().out)
    assert [h["status"] for h in hist][:2] == ["pass", "fail"]
    assert main(["checkpoint", "--pipeline", "p", "--stage", "source", "--batch-id", "b", "--rows", "8"]) == 0
    assert main(["checkpoint", "--pipeline", "p", "--stage", "gold", "--batch-id", "b", "--rows", "7"]) == 0
    capsys.readouterr()
    assert main(["trace", "--pipeline", "p", "--batch-id", "b"]) == 1
    assert "lost 1 rows" in capsys.readouterr().out
    assert main(["reconcile", "reconciliations/orders.recon.yaml", "--batch-id", "batch-001", "--no-notify"]) == 0
    watch_args = ["watch", "--contract-id", "orders", "--once", "--no-notify"]
    if adapter != "files":
        watch_args += ["--batch-column", "load_id"]
    assert main(watch_args) == 1  # batch-002 is bad
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert main(watch_args) == 0  # nothing new the second time
    if adapter == "sqlite":
        result = subprocess.run(["python", "jobs/ingestion_gate.py", "batch-001"], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_cli_adapters_and_errors(tmp_path, capsys):
    assert main(["adapters"]) == 0
    out = capsys.readouterr().out
    for name in ("snowflake", "databricks", "mongodb", "cosmosdb", "files", "db2"):
        assert name in out
    assert main(["adapters", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == len(ADAPTERS)
    assert main(["run", str(tmp_path / "nope.yaml")]) == 2
    assert main(["run", "--contract-id", "x", "-c", str(tmp_path / "missing.yaml")]) == 2
    root = tmp_path / "p"
    main(["init", str(root), "--adapter", "sqlite", "--no-input"])
    assert main(["init", str(root), "--adapter", "sqlite", "--no-input"]) == 2  # not empty
    cfg = str(root / "odcr.yaml")
    assert main(["run", "--contract-id", "nope", "-c", cfg]) == 2
    assert main(["run", "-c", cfg]) == 2
    assert main(["run", "--for-object", "nothing", "-c", cfg]) == 2
    assert main(["run", "--contract-id", "orders", "-c", cfg, "-C", "unknown"]) == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"kind": "DataContract"}))
    assert main(["lint", str(bad)]) == 1
    assert load_config(cfg).meta_schema == "odcr_meta"


def test_airflow_operator_without_airflow(tmp_path, monkeypatch):
    from odcr.integrations.airflow import OdcrCheckpointOperator, OdcrContractOperator

    root = tmp_path / "p"
    main(["init", str(root), "--adapter", "sqlite", "--no-input", "--alerts", "none"])
    monkeypatch.setenv("SQLITE_PATH", str(root / "db.sqlite"))
    main(["seed", "-c", str(root / "odcr.yaml")])
    ok = OdcrContractOperator(task_id="t", config_path=str(root / "odcr.yaml"), contract_id="orders",
                              batch_id="batch-001", where="load_id = 'batch-001'", pipeline="orders")
    assert ok.execute({})["status"] == "pass"
    bad = OdcrContractOperator(task_id="t2", config_path=str(root / "odcr.yaml"), contract_id="orders",
                               where="load_id = 'batch-002'")
    with pytest.raises(RuntimeError, match="FAIL"):
        bad.execute({})
    assert OdcrCheckpointOperator(task_id="c", config_path=str(root / "odcr.yaml"), pipeline="orders",
                                  stage="gold", batch_id="batch-001", row_count=4).execute({})


def test_interactive_only_asks_for_what_was_not_given(tmp_path):
    asked: list[str] = []

    def reader(prompt: str) -> str:
        asked.append(prompt)
        return ""

    scaffold(tmp_path / "p", adapter="postgres", interactive=True, reader=reader)
    assert not any("Which platform" in q for q in asked), asked  # --adapter given: not asked again
    assert any("Project name" in q for q in asked)
    assert "type: postgres" in (tmp_path / "p" / "odcr.yaml").read_text()
    asked.clear()
    scaffold(tmp_path / "q", name="n", adapter="postgresql", interactive=True, reader=reader)
    assert not any("Project name" in q or "Which platform" in q for q in asked)


def test_adapter_typo_gets_a_suggestion(tmp_path):
    with pytest.raises(ValueError, match="Did you mean 'postgres'"):
        scaffold(tmp_path / "p", adapter="postgress")


def test_init_creates_a_folder_named_after_the_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    answers = iter(["sales_contracts", "", "", "none", "", ""])
    written = scaffold(None, adapter="postgres", interactive=True, reader=lambda _: next(answers))
    assert (tmp_path / "sales_contracts" / "odcr.yaml").exists()
    assert all(tmp_path / "sales_contracts" in p.parents for p in written)
    assert not (tmp_path / "odcr.yaml").exists()  # nothing written into the current folder
    assert main(["init", "--name", "finance", "--adapter", "sqlite", "--no-input"]) == 0
    assert (tmp_path / "finance" / "odcr.yaml").exists()
    assert main(["init", "--adapter", "sqlite", "--no-input"]) == 0
    assert (tmp_path / "odcr_project" / "odcr.yaml").exists()
    with pytest.raises(ValueError):
        scaffold(None, interactive=True, reader=lambda _: "bad name!")


def test_destroy_removes_the_project_safely(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "proj", "--adapter", "sqlite", "--no-input"]) == 0
    (tmp_path / "proj" / ".env").write_text("SECRET=1\n")
    (tmp_path / "keep.txt").write_text("not part of the project")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["destroy", "proj"]) == 2  # no confirmation possible: refused
    assert (tmp_path / "proj").exists()
    out = capsys.readouterr().out
    assert ".env" in out and "NOT touched" in out  # user files are listed before deleting
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "wrong")
    assert main(["destroy", "proj"]) == 1 and (tmp_path / "proj").exists()  # wrong name: cancelled
    monkeypatch.setattr("builtins.input", lambda _: "proj")
    assert main(["destroy", "proj"]) == 0
    assert not (tmp_path / "proj").exists() and (tmp_path / "keep.txt").exists()
    assert main(["destroy", "."]) == 2  # not an odcr project
    assert main(["init", "p2", "--adapter", "sqlite", "--no-input"]) == 0
    monkeypatch.chdir(tmp_path / "p2")
    assert main(["destroy", "--yes"]) == 2  # refuses while you are inside it
    monkeypatch.chdir(tmp_path)
    assert main(["destroy", "p2", "--yes"]) == 0 and not (tmp_path / "p2").exists()


@pytest.mark.parametrize("provider,expected,secret", [
    ("smtp-relay", "provider: smtp-relay", False), ("microsoft365", "provider: microsoft365", False),
    ("aws-ses", "provider: aws-ses", False), ("smtp", "${keyring:SMTP_PASSWORD}", True),
    ("gmail", "host: smtp.gmail.com", True)])
def test_init_mail_providers(provider, expected, secret, tmp_path, capsys):
    root = tmp_path / provider
    assert main(["init", str(root), "--adapter", "postgres", "--no-input", "--mail", provider,
                 "--mail-from", "alerts@acme.com", "--alerts-email", "platform@acme.com"]) == 0
    text = (root / "odcr.yaml").read_text()
    assert expected in text and "platform@acme.com" in text and "password: ${SMTP" not in text
    assert "SMTP_PASSWORD=" not in (root / ".env.example").read_text()  # never a plain-text password
    assert ("odcr secret set SMTP_PASSWORD" in capsys.readouterr().out) is secret
    yaml.safe_load(text)
