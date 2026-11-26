"""Regenerate the reference project for every adapter: python scripts/generate_examples.py

Each examples/<adapter>/ folder is exactly what `odcr init --adapter <adapter>` creates.
tests/unit/test_examples.py fails when they are out of date.
"""

import shutil
from pathlib import Path

from odcr.adapters import ADAPTERS
from odcr.scaffold import scaffold

ROOT = Path(__file__).resolve().parent.parent / "examples"


def generate(target: Path = ROOT) -> None:
    if target.exists():
        shutil.rmtree(target)
    for name in ADAPTERS:
        scaffold(target / name, name=f"{name}_example", adapter=name, platform_channel="teams")


if __name__ == "__main__":
    generate()
    print(f"Generated {len(ADAPTERS)} reference projects in {ROOT}")
