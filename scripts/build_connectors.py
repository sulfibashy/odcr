"""Build the connector packages: odcr-postgres, odcr-snowflake, ... (one per adapter extra, plus odcr-all).

Each is a tiny package with no code that depends on "odcr[<extra>]" at the same version, so users can run
`pip install odcr-postgres` (no brackets, no quotes) — the same pattern as dbt-postgres.

    python scripts/build_connectors.py            # writes connectors/<name>/pyproject.toml and README.md
    python scripts/build_connectors.py --build    # also builds wheels + sdists into dist/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from odcr import __version__  # noqa: E402
from odcr.adapters import ADAPTERS  # noqa: E402

OUT = ROOT / "connectors"


def connectors() -> dict[str, str]:
    """package suffix -> title, for every extra an adapter uses, plus 'all'."""
    out: dict[str, str] = {}
    for info in ADAPTERS.values():
        if info.extra and info.extra not in out:
            titles = [i.title for i in ADAPTERS.values() if i.extra == info.extra]
            out[info.extra] = ", ".join(titles)
    out["all"] = "every platform"
    return out


def pyproject(extra: str, title: str, version: str) -> str:
    return f'''[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "odcr-{extra}"
version = "{version}"
description = "odcr connector for {title}: installs odcr with the {extra} driver."
readme = "README.md"
requires-python = ">=3.10"
license = "Apache-2.0"
authors = [{{ name = "sulfibashy" }}, {{ name = "odcr contributors" }}]
keywords = ["data contracts", "ODCS", "data quality", "odcr", "{extra}"]
classifiers = ["Programming Language :: Python :: 3", "Operating System :: OS Independent", "Topic :: Database"]
dependencies = ["odcr[{extra}]=={version}"]

[project.urls]
Homepage = "https://github.com/sulfibashy/odcr"
Documentation = "https://sulfibashy.github.io/odcr/"

[tool.setuptools]
packages = []
'''


def readme(extra: str, title: str) -> str:
    return f"""# odcr-{extra}

The [odcr](https://github.com/sulfibashy/odcr) connector for **{title}**.

```bash
pip install odcr-{extra}
odcr init my_contracts --adapter {extra if extra != 'all' else 'postgres'}
```

This package contains no code: it installs `odcr` together with the {extra} driver
(the same as `pip install "odcr[{extra}]"`). Documentation: https://sulfibashy.github.io/odcr/
"""


def generate(version: str = __version__, out: Path = OUT) -> list[Path]:
    dirs = []
    for extra, title in connectors().items():
        d = out / f"odcr-{extra}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "pyproject.toml").write_text(pyproject(extra, title, version), encoding="utf-8", newline="\n")
        (d / "README.md").write_text(readme(extra, title), encoding="utf-8", newline="\n")
        dirs.append(d)
    return dirs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="build wheels and sdists into dist/")
    args = parser.parse_args()
    for d in generate():
        if args.build:
            subprocess.run([sys.executable, "-m", "build", "--outdir", str(ROOT / "dist"), str(d)], check=True)
    print(f"{len(connectors())} connector packages for odcr {__version__}")
