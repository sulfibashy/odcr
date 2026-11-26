"""Contract linting: built-in checks, plus the official Data Contract CLI when it is installed."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .contract import ContractError, load_contract


@dataclass
class LintResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    datacontract_cli: str | None = None  # output of `datacontract lint`, when used


def lint(path: str | Path, use_datacontract_cli: bool = False) -> LintResult:
    try:
        contract = load_contract(path)
    except ContractError as exc:
        return LintResult(False, exc.problems or [str(exc)])
    res = LintResult(True)
    for obj in contract.schema:
        if not obj.properties:
            res.warnings.append(f"{obj.name}: no properties; schema checks are skipped")
        for p in obj.properties:
            if not p.logical_type:
                res.warnings.append(f"{obj.name}.{p.name}: no logicalType; type is not checked")
    if not contract.contacts:
        res.warnings.append("no support channels with a url (slack/teams/email); the source team will not be notified")
    if use_datacontract_cli:
        exe = shutil.which("datacontract")
        if not exe:
            res.warnings.append("datacontract CLI not found; install with: pip install 'odcr[lint]'")
        else:
            proc = subprocess.run([exe, "lint", str(path)], capture_output=True, text=True, check=False)
            res.datacontract_cli = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                res.ok = False
                res.problems.append("datacontract lint failed (see output)")
    return res
