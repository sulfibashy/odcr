"""`odcr init`: create a ready-to-run odcr project for one adapter, like `dbt init`.

    my_contracts/
    ├── odcr.yaml                     connections, meta tables, notifications, contract repository
    ├── .env.example                  every environment variable the connection needs
    ├── contracts/sales/orders.odcs.yaml
    ├── reconciliations/orders.recon.yaml
    ├── seeds/orders.csv              sample data (`odcr seed` loads it into your platform)
    ├── jobs/ingestion_gate.py | .sh | .ps1     how pipelines call odcr (Linux, macOS, Windows)
    ├── tests/test_contracts.py       every contract must be valid
    ├── .github/workflows/contracts.yml   and  azure-pipelines.yml     CI for the contract repository
    ├── README.md
    └── .gitignore
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from . import samples
from .adapters import ADAPTERS, AdapterInfo, resolve

PROMPT_ORDER = ["duckdb", "files", "sqlite", "postgres", "mysql", "sqlserver", "oracle", "db2", "trino",
                "databricks", "snowflake", "bigquery", "redshift", "athena", "synapse", "fabric", "mongodb", "cosmosdb"]


def physical_name(info: AdapterInfo) -> str:
    return "landing/orders/*.parquet" if info.name == "files" else "orders"


def _custom_rule(info: AdapterInfo) -> str:
    if info.name == "mongodb":
        return ("      - type: custom\n        name: orders.no_negative_amounts\n        engine: mongodb\n"
                "        description: Amounts must never be negative\n"
                "        implementation: '{\"amount\": {\"$lt\": 0}}'\n        mustBe: 0\n")
    if info.name == "cosmosdb":
        return ("      - type: custom\n        name: orders.no_negative_amounts\n        engine: cosmosdb\n"
                "        description: Amounts must never be negative\n"
                "        implementation: c.amount < 0\n        mustBe: 0\n")
    return ("      - type: sql\n        name: orders.no_negative_amounts\n"
            "        description: Amounts must never be negative\n"
            "        query: SELECT COUNT(*) FROM {object} WHERE amount < 0\n        mustBe: 0\n")


def contract_yaml(info: AdapterInfo) -> str:
    return f"""# ODCS v3 data contract (Open Data Contract Standard). One file per dataset; reviewed like code.
apiVersion: v3.0.2
kind: DataContract
id: orders
name: Orders
version: 1.0.0
status: active
domain: sales
dataProduct: orders
description:
  purpose: Orders from the web shop. Arrives as hourly batches, CDC or a stream; checked the moment it lands.

team:
  - username: order-team-lead
    role: owner

# The source team is notified here when this contract is broken.
# Supported tools: slack, teams, email, googlechat, discord, pagerduty, opsgenie, webhook
support:
  - channel: "#orders-data-alerts"
    tool: slack
    url: ${{ORDERS_SLACK_WEBHOOK}}
  - channel: orders-team
    tool: teams
    url: ${{ORDERS_TEAMS_WEBHOOK}}
  - channel: orders-team@example.com
    tool: email
    url: mailto:orders-team@example.com

schema:
  - name: orders
    physicalName: {physical_name(info)}
    physicalType: {"file" if info.name == "files" else "table"}
    properties:
      - name: order_id
        logicalType: integer
        primaryKey: true          # required + unique
      - name: customer_id
        logicalType: integer
        required: true
      - name: status
        logicalType: string
        required: true
        quality:
          - type: library
            metric: invalidValues
            arguments:
              validValues: [NEW, PAID, SHIPPED, CANCELLED]
            mustBe: 0
      - name: amount
        logicalType: number
        quality:
          - type: library
            metric: nullValues
            mustBeLessOrEqualTo: 1
            unit: percent
            severity: warning     # notify, but do not stop the pipeline
      - name: order_date
        logicalType: date
        required: true
      - name: load_id
        logicalType: string
        description: Batch, micro-batch, CDC transaction or file id
    quality:
      - type: library
        metric: rowCount
        mustBeGreaterThan: 0
{_custom_rule(info)}"""


def config_yaml(info: AdapterInfo, platform_channel: str, platform_target: str, meta_schema: str) -> str:
    conn = yaml.safe_dump({"main": info.connection}, sort_keys=False, default_flow_style=False).rstrip()
    conn = "\n".join("  " + line for line in conn.splitlines())
    channel = {
        "slack": "    - type: slack\n      url: ${PLATFORM_SLACK_WEBHOOK}",
        "teams": "    - type: teams\n      url: ${PLATFORM_TEAMS_WEBHOOK}",
        "email": f"    - type: email\n      to: [{platform_target or 'data-platform@example.com'}]",
        "none": "",
    }.get(platform_channel, "")
    return f"""# odcr project configuration. ${{VAR}} and ${{VAR:-default}} come from environment variables;
# ${{file:/run/secrets/name}} reads a secret file. Never put passwords or tokens in this file.
name: {{name}}

# The central contract repository. A folder in this project, or a shared Git repository:
#   contracts: {{git: https://github.com/acme/data-contracts.git, ref: main, path: contracts, token_env: GIT_TOKEN}}
contracts:
  path: contracts

connections:
{conn}

# Meta tables (runs, check results, quarantine, notifications, reconciliation, pipeline events) are
# created in this schema on the platform itself. Use `connection:` to store them on another platform.
meta:
  schema: {meta_schema}

# quarantine: failed batches are logged in quarantine_log and the command exits with code 1.
on_fail: quarantine

notifications:
  notify_on: [fail, warn]
  # The platform team hears about every failure, on every contract.
  platform_team:
    - type: console
{channel}
  smtp:                      # used by email channels; TLS is verified with the system CA store
    host: ${{SMTP_HOST:-localhost}}
    port: ${{SMTP_PORT:-587}}
    starttls: true
    user: ${{SMTP_USER:-}}
    password: ${{SMTP_PASSWORD:-}}
    from: odcr@example.com
  # ca_bundle: /etc/ssl/certs/corporate-ca.pem   # private CA / TLS-inspecting proxy
  # proxy: http://proxy.example.com:8080
"""


def env_example(info: AdapterInfo) -> str:
    text = yaml.safe_dump(info.connection) + "\nORDERS_SLACK_WEBHOOK ORDERS_TEAMS_WEBHOOK PLATFORM_SLACK_WEBHOOK " \
                                             "PLATFORM_TEAMS_WEBHOOK SMTP_HOST SMTP_USER SMTP_PASSWORD"
    names = sorted(set(re.findall(r"\$\{([A-Z0-9_]+)", text)) | set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", text.split("\n")[-1])))
    lines = ["# Copy to .env (never commit it) or set these in your scheduler / secret store.",
             f"# Connection: {info.title}"]
    defaults = dict(re.findall(r"\$\{([A-Z0-9_]+):-([^}]*)\}", text))
    lines += [f"{n}={defaults.get(n, '')}" for n in names]
    return "\n".join(lines) + "\n"


def recon_yaml(info: AdapterInfo) -> str:
    where = info.where_example
    return f"""# Reconciliation: does the target hold exactly what the source sent, for this batch?
# Source and target can be different platforms: add a second connection to odcr.yaml and name it here.
kind: Reconciliation
id: orders-source-to-target
contract: orders
source:
  connection: main
  object: {physical_name(info)}
  where: {yaml.safe_dump(where, default_style='"').strip()}
target:
  connection: main
  object: {physical_name(info)}
  where: {yaml.safe_dump(where, default_style='"').strip()}
checks:
  - type: rowCount
  - type: sum
    column: amount
    tolerance: 0.01
  - type: distinctCount
    column: customer_id
  - type: missingKeys
    column: order_id
"""


def job_py(info: AdapterInfo) -> str:
    return f'''"""Ingestion gate: call this the moment a batch, micro-batch, CDC transaction or file has landed.

    python jobs/ingestion_gate.py batch-001
"""

import sys

from odcr import checkpoint, run_contract
from odcr.adapters import get_adapter
from odcr.config import load_config
from odcr.repository import ContractRepository

WHERE = {info.where_example!r}  # filter selecting one batch on this platform
batch_id = sys.argv[1] if len(sys.argv) > 1 else "batch-001"
config = load_config("odcr.yaml")
contract = ContractRepository.from_config(config).get("orders")

with get_adapter(config.connection("main")) as db:
    # 1. What the source says it sent (from the file manifest, the CDC log or the Kafka / Event Hub offsets)
    checkpoint(db, pipeline="orders", stage="source", batch_id=batch_id, row_count=4, config=config)
    # 2. Check exactly this batch against the contract; logs, quarantines and notifies on failure
    result = run_contract(contract, db, config, batch_id=batch_id, where=WHERE.replace("{{batch_id}}", batch_id),
                          pipeline="orders", stage="ingestion")
    print(result.summary())
    sys.exit(0 if result.passed else 1)
'''


def job_sh(info: AdapterInfo) -> str:
    where = info.where_example.replace("{batch_id}", "${BATCH_ID}").replace('"', '\\"')
    return f"""#!/usr/bin/env sh
# Ingestion gate for Linux / macOS / Unix schedulers (cron, Control-M, Informatica post-session command,
# Ab Initio Run Program component, Autosys). Exit code 1 stops the downstream job.
set -eu
BATCH_ID="${{1:-batch-001}}"
cd "$(dirname "$0")/.."
odcr run --contract-id orders --connection main --batch-id "$BATCH_ID" \\
  --where "{where}" --pipeline orders --stage ingestion
"""


def job_ps1(info: AdapterInfo) -> str:
    where = info.where_example.replace("{batch_id}", "$BatchId").replace('"', '`"')
    return f"""# Ingestion gate for Windows (Task Scheduler, SQL Server Agent, SSIS Execute Process, Informatica on Windows).
param([string]$BatchId = "batch-001")
Set-Location (Join-Path $PSScriptRoot "..")
odcr run --contract-id orders --connection main --batch-id $BatchId `
  --where "{where}" --pipeline orders --stage ingestion
exit $LASTEXITCODE
"""


TEST_PY = '''"""Every contract in the repository must be valid ODCS. Run with: pytest"""

from pathlib import Path

from odcr.repository import ContractRepository


def test_all_contracts_are_valid():
    repo = ContractRepository.load(Path(__file__).parent.parent / "contracts")
    assert repo.contracts, "no contracts found"
    assert not repo.errors, repo.errors
'''

GITHUB_CI = """name: contracts
on:
  pull_request:
  push:
    branches: [main]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install odcr pytest
      - run: odcr lint contracts
      - run: pytest -q
"""

AZURE_CI = """# Azure DevOps pipeline for the contract repository
trigger: [main]
pr: [main]
pool:
  vmImage: ubuntu-latest
steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: "3.12"
  - script: pip install odcr pytest
  - script: odcr lint contracts
  - script: pytest -q
"""

GITIGNORE = """.env
*.duckdb
*.duckdb.wal
*.sqlite
__pycache__/
.pytest_cache/
landing/
"""


def shell_arg(text: str) -> str:
    return f"'{text}'" if '"' in text else f'"{text}"'


def readme(name: str, info: AdapterInfo) -> str:
    w1 = shell_arg(info.where_example.replace("{batch_id}", "batch-001"))
    w2 = shell_arg(info.where_example.replace("{batch_id}", "batch-002"))
    extra = f'"odcr[{info.extra}]"' if info.extra else "odcr"
    return f"""# {name}

Data contracts and data quality checks with [odcr](https://github.com/sulfibashy/odcr) on **{info.title}**.

## Setup

```bash
pip install {extra}
cp .env.example .env        # fill in connection details (Windows: copy .env.example .env)
odcr doctor -C main         # test the connection, TLS and permissions
odcr meta-init -C main      # create the meta tables
odcr seed -C main           # optional: load the sample orders data
```

## Check data when it lands

```bash
odcr run --contract-id orders -C main --batch-id batch-001 --where {w1}
odcr run --contract-id orders -C main --batch-id batch-002 --where {w2}   # fails on purpose
odcr watch --contract-id orders -C main {'--once' if info.name == 'files' else '--batch-column load_id --once'}     # every new {'file' if info.name == 'files' else 'batch'}, once
odcr history -C main
```

From a pipeline: `jobs/ingestion_gate.sh` (Linux/macOS/Unix), `jobs/ingestion_gate.ps1` (Windows) or
`jobs/ingestion_gate.py` (Python, Spark, Airflow). Exit code 1 means the batch broke the contract.

## Layout

| Path | What it is |
| --- | --- |
| `contracts/` | The contract repository: one ODCS YAML per dataset. Point `odcr.yaml` to a shared Git repo instead if you have one. |
| `reconciliations/` | Source-versus-target comparisons per batch. |
| `seeds/` | Sample data. |
| `jobs/` | Scripts your scheduler or ETL tool calls. |
| `tests/` | `pytest` validates every contract. |
| `.github/`, `azure-pipelines.yml` | CI that validates contracts on every pull request. |
"""


def ask(prompt: str, default: str, options: list[str] | None = None,
        reader: Callable[[str], str] = input) -> str:
    hint = f" [{default}]" if default else ""
    while True:
        answer = reader(f"{prompt}{hint}: ").strip() or default
        if options and answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        if not options or answer in options:
            return answer
        try:
            return resolve(answer).name if options and options[0] in ADAPTERS else answer
        except ValueError:
            print(f"  choose one of: {', '.join(options)}")


def scaffold(directory: str | Path, *, name: str | None = None, adapter: str = "duckdb",
             meta_schema: str = "odcr_meta", platform_channel: str = "email", platform_target: str = "",
             force: bool = False, interactive: bool = False, reader: Callable[[str], str] = input) -> list[Path]:
    """Create the project. Returns the files written."""
    root = Path(directory)
    if interactive:
        print("Creating an odcr project. Press Enter to accept the [default].\n")
        name = ask("Project name", name or root.name or "odcr_project", reader=reader)
        print("\nAdapters:")
        for i, key in enumerate(PROMPT_ORDER, 1):
            info = ADAPTERS[key]
            print(f"  {i:>2}. {key:<11} {info.title}")
        adapter = ask("Which platform will odcr check", adapter, PROMPT_ORDER, reader=reader)
        meta_schema = ask("Schema for the meta tables", meta_schema, reader=reader)
        platform_channel = ask("Platform team alerts (slack, teams, email, none)", platform_channel,
                               ["slack", "teams", "email", "none"], reader=reader)
        if platform_channel == "email":
            platform_target = ask("Platform team email", platform_target or "data-platform@example.com",
                                  reader=reader)
    info = resolve(adapter)
    name = name or root.name or "odcr_project"
    if root.exists() and any(root.iterdir()) and not force:
        raise FileExistsError(f"{root} is not empty; use --force to write into it")
    files: dict[str, str] = {
        "odcr.yaml": config_yaml(info, platform_channel, platform_target, meta_schema).replace("{name}", name),
        ".env.example": env_example(info),
        "contracts/sales/orders.odcs.yaml": contract_yaml(info),
        "reconciliations/orders.recon.yaml": recon_yaml(info),
        "seeds/orders.csv": samples.csv_text(),
        "jobs/ingestion_gate.py": job_py(info),
        "jobs/ingestion_gate.sh": job_sh(info),
        "jobs/ingestion_gate.ps1": job_ps1(info),
        "tests/test_contracts.py": TEST_PY,
        ".github/workflows/contracts.yml": GITHUB_CI,
        "azure-pipelines.yml": AZURE_CI,
        "README.md": readme(name, info),
        ".gitignore": GITIGNORE,
    }
    written: list[Path] = []
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    if sys.platform != "win32":
        (root / "jobs/ingestion_gate.sh").chmod(0o755)
    return written


def describe(info: AdapterInfo) -> dict[str, Any]:
    return {"name": info.name, "title": info.title, "install": f"pip install \"odcr[{info.extra}]\"" if info.extra
            else "pip install odcr"}
