"""Regenerate the adapter pages and the CLI reference: python scripts/generate_docs.py"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from odcr.adapters import ADAPTERS, AdapterInfo
from odcr.cli import build_parser
from odcr.scaffold import shell_arg

DOCS = Path(__file__).resolve().parent.parent / "docs"


def adapter_page(info: AdapterInfo) -> str:
    install = f'pip install "odcr[{info.extra}]"' if info.extra else "pip install odcr"
    conn = yaml.safe_dump({"connections": {"main": info.connection}}, sort_keys=False).rstrip()
    tested = ("End-to-end tests run against a live instance in CI on every push."
              if info.tested == "ci" else
              f"End-to-end tests run when credentials are provided (`ODCR_TEST_{info.name.upper()}`, see "
              "[Development](../contributing/development.md)). Unit tests cover the SQL it generates.")
    aliases = ", ".join(f"`{a}`" for a in info.aliases) or "none"
    notes = "\n".join(f"- {n}" for n in info.notes) or "- None."
    example_where = shell_arg(info.where_example.replace("{batch_id}", "batch-001"))
    return f"""# {info.title}

{info.description}

| | |
| --- | --- |
| Adapter name | `{info.name}` (aliases: {aliases}) |
| Runs on | {info.clouds} |
| Install | `{install}` |
| Python driver | `{info.driver}` |
| Batch filter example | `{info.where_example}` |
| Testing | {tested} |

## Create a project

```bash
{install}
odcr init my_contracts --adapter {info.name}
cd my_contracts
```

The generated project is also in the repository: [`examples/{info.name}`](https://github.com/sulfibashy/odcr/tree/main/examples/{info.name}).

## Connection

```yaml
{conn}
```

Values like `${{NAME}}` come from environment variables or a `.env` file next to `odcr.yaml`; `${{file:/path}}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

{notes}

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where {example_where}
```
"""


def adapters_index() -> str:
    rows = "\n".join(
        f"| [{i.title}]({i.name}.md) | `{i.name}` | {i.clouds} | "
        f"`{'odcr[' + i.extra + ']' if i.extra else 'odcr'}` | {'CI' if i.tested == 'ci' else 'with credentials'} |"
        for i in ADAPTERS.values())
    return f"""# Adapters

One adapter per platform. Install only the extras you need: `pip install "odcr[snowflake,databricks]"`,
or everything with `pip install "odcr[all]"`. `odcr adapters` shows which drivers are installed.

| Platform | Adapter | Where | Install | End-to-end tests |
| --- | --- | --- | --- | --- |
{rows}

**ETL and orchestration tools** (Informatica, Ab Initio, Azure Data Factory, SSIS, Airflow, Databricks Workflows)
are not adapters: they call odcr when data lands. See [Integrations](../integrations/index.md).

Missing a platform? [Adding an adapter](../contributing/adding-an-adapter.md) takes about 50 lines.
"""


def cli_reference() -> str:
    os.environ["COLUMNS"] = "100"
    parser = build_parser()
    out = ["# CLI reference", "", "Generated from `odcr --help`.", ""]
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for action in sub._choices_actions:  # one entry per command (aliases excluded)
        name = action.dest.split(" ")[0]
        sp = sub.choices[name]
        out += [f"## odcr {name}", "", action.help or "", "",
                "```text", sp.format_help().strip(), "```", ""]
    return "\n".join(out)


def generate(target: Path = DOCS) -> None:
    (target / "adapters").mkdir(parents=True, exist_ok=True)
    (target / "reference").mkdir(parents=True, exist_ok=True)
    for info in ADAPTERS.values():
        (target / "adapters" / f"{info.name}.md").write_text(adapter_page(info), encoding="utf-8", newline="\n")
    (target / "adapters" / "index.md").write_text(adapters_index(), encoding="utf-8", newline="\n")
    (target / "reference" / "cli.md").write_text(cli_reference(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    generate()
    print("docs/adapters and docs/reference/cli.md regenerated")
