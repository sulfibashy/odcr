"""The central contract repository: every ODCS contract in one Git repository (or folder).

    contracts:
      path: contracts                       # a folder next to odcr.yaml, or an absolute path / network share
    # or straight from Git (cached locally, refreshed on every run):
    contracts:
      git: https://github.com/acme/data-contracts.git     # or git@github.com:acme/data-contracts.git
      ref: main
      path: contracts                       # folder inside the repository
      token_env: GIT_TOKEN                  # optional: HTTPS token for private repositories

Works with any Git host: GitHub, Azure DevOps (Azure Repos), GitLab, Bitbucket, Gitea, on-premise servers.
Authentication, in order of preference:
  * nothing to configure: SSH keys, or Git Credential Manager / `az login` / `gh auth` on the machine;
  * in pipelines: the pipeline's own token, e.g. Azure DevOps $(System.AccessToken) or GitHub's GITHUB_TOKEN,
    passed in an environment variable named by `token_env` (never written to disk or logs).

Override the source per command without editing odcr.yaml:
    odcr run --contracts https://dev.azure.com/acme/data/_git/contracts --contracts-ref main --contract-id orders
    ODCR_CONTRACTS=git@github.com:acme/data-contracts.git odcr lint

Contracts are found by id (`--contract-id orders`) or by the object they describe (`--for-object sales.orders`).
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import Config, ConfigError
from .contract import Contract, ContractError, parse_contract

PATTERNS = ("*.odcs.yaml", "*.odcs.yml", "*.contract.yaml", "*.contract.yml", "*.yaml", "*.yml")


def cache_dir() -> Path:
    base = os.environ.get("ODCR_CACHE_DIR") or (Path.home() / ".cache" / "odcr")
    return Path(base)


def _redact(text: str) -> str:
    import re

    return re.sub(r"https://[^/@\s]+@", "https://***@", text)


def _git(*args: str, cwd: Path | None = None) -> None:
    exe = shutil.which("git")
    if not exe:
        raise ConfigError("git is not installed; install Git or point contracts.path to a local folder")
    proc = subprocess.run([exe, *args], cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        shown = " ".join(a for a in args if "@" not in a or a.startswith("git@"))
        raise ConfigError(f"git {shown} failed: {_redact(proc.stderr.strip())[:500]}")


GIT_PREFIXES = ("https://", "http://", "ssh://", "git@", "git://", "file://")


def is_git_source(source: str) -> bool:
    return source.startswith(GIT_PREFIXES) or source.endswith(".git")


def contracts_spec(source: str, ref: str | None = None, path: str | None = None) -> dict[str, Any]:
    """A `contracts:` block from a command-line / environment value: a folder or a Git URL."""
    if is_git_source(source):
        spec: dict[str, Any] = {"git": source, "ref": ref or "main", "token_env": "GIT_TOKEN"}
        if path is not None:
            spec["path"] = path
        return spec
    return {"path": source}


def sync_git(url: str, ref: str = "main", token_env: str | None = None, token_user: str = "x-access-token") -> Path:
    """Clone or refresh the contract repository into the local cache and return its folder."""
    target = cache_dir() / "repos" / hashlib.sha1(f"{url}@{ref}".encode()).hexdigest()[:12]
    auth_url = url
    if token_env and os.environ.get(token_env) and url.startswith("https://"):
        auth_url = url.replace("https://", f"https://{token_user}:{os.environ[token_env]}@", 1)
    if (target / ".git").exists():
        _git("-c", "credential.interactive=never", "fetch", "--depth", "1", auth_url, ref, cwd=target)
        _git("reset", "--hard", "FETCH_HEAD", cwd=target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _git("-c", "credential.interactive=never", "clone", "--depth", "1", "--branch", ref, auth_url, str(target))
    return target


@dataclass
class ContractRepository:
    root: Path
    contracts: dict[str, Contract] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)  # file -> problems

    @classmethod
    def load(cls, root: str | Path) -> ContractRepository:
        repo = cls(Path(root))
        if not repo.root.exists():
            raise ConfigError(f"Contract repository not found: {repo.root}")
        seen: set[Path] = set()
        for pattern in PATTERNS:
            for path in sorted(repo.root.rglob(pattern)):
                if path in seen or any(part.startswith(".") for part in path.relative_to(repo.root).parts):
                    continue
                seen.add(path)
                text = path.read_text(encoding="utf-8")
                try:
                    doc = yaml.safe_load(text)
                except yaml.YAMLError as exc:
                    repo.errors[str(path)] = [f"not valid YAML: {exc}"]
                    continue
                if not isinstance(doc, dict) or doc.get("kind") != "DataContract":
                    continue  # other YAML (configs, reconciliations) is ignored
                try:
                    c = parse_contract(doc, path=str(path), text=text)
                except ContractError as exc:
                    repo.errors[str(path)] = exc.problems or [str(exc)]
                    continue
                if c.id in repo.contracts:
                    repo.errors[str(path)] = [f"duplicate contract id '{c.id}' (also in {repo.contracts[c.id].path})"]
                    continue
                repo.contracts[c.id] = c
        return repo

    @classmethod
    def from_config(cls, config: Config, source: str | None = None, ref: str | None = None) -> ContractRepository:
        """Load from `source` (command line), else $ODCR_CONTRACTS, else the config's `contracts:` block."""
        source = source or os.environ.get("ODCR_CONTRACTS")
        if source:
            ref = ref or os.environ.get("ODCR_CONTRACTS_REF")
            path = os.environ.get("ODCR_CONTRACTS_PATH")
            spec: dict[str, Any] = contracts_spec(source, ref, path)
        else:
            spec = dict(config.contracts or {})
            if ref and spec.get("git"):
                spec["ref"] = ref
        if spec.get("git"):
            root = sync_git(str(spec["git"]), str(spec.get("ref", "main")), spec.get("token_env"),
                            str(spec.get("token_user", "x-access-token")))
            return cls.load(root / str(spec.get("path", "")))
        path = Path(str(spec.get("path", "contracts")))
        return cls.load(path if path.is_absolute() else config.base_dir / path)

    def get(self, contract_id: str) -> Contract:
        if contract_id not in self.contracts:
            raise ContractError(f"No contract with id '{contract_id}' in {self.root} "
                                f"({len(self.contracts)} contracts found)")
        return self.contracts[contract_id]

    def find_by_object(self, name: str) -> list[tuple[Contract, str]]:
        """Contracts whose schema object (name, physicalName or file glob) matches `name`."""
        key = name.lower()
        hits: list[tuple[Contract, str]] = []
        for c in self.contracts.values():
            for obj in c.schema:
                pn = obj.physical_name.lower()
                if key in (obj.name.lower(), pn, pn.split(".")[-1]) or fnmatch.fnmatch(key, pn):
                    hits.append((c, obj.name))
        return hits
