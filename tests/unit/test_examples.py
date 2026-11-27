"""The reference projects in examples/ must match what `odcr init` generates today."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_examples_are_up_to_date(tmp_path):
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_examples.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    gen.generate(tmp_path)
    expected = {p.relative_to(tmp_path): p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    actual = {p.relative_to(ROOT / "examples"): p.read_text(encoding="utf-8")
              for p in (ROOT / "examples").rglob("*") if p.is_file()}
    assert sorted(actual) == sorted(expected), "run: python scripts/generate_examples.py"
    stale = [str(k) for k in expected if actual[k] != expected[k]]
    assert not stale, f"out of date (run python scripts/generate_examples.py): {stale[:5]}"


def test_adapter_docs_are_up_to_date(tmp_path):
    spec = importlib.util.spec_from_file_location("gendocs", ROOT / "scripts" / "generate_docs.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    gen.generate(tmp_path)
    for page in (tmp_path / "adapters").glob("*.md"):
        current = (ROOT / "docs" / "adapters" / page.name).read_text(encoding="utf-8")
        assert current == page.read_text(encoding="utf-8"), f"run: python scripts/generate_docs.py ({page.name})"


def test_connector_packages_are_up_to_date(tmp_path):
    spec = importlib.util.spec_from_file_location("conn", ROOT / "scripts" / "build_connectors.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    gen.generate(out=tmp_path)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(p.name for p in (ROOT / "connectors").iterdir()), "run: python scripts/build_connectors.py"
    for name in names:
        for f in ("pyproject.toml", "README.md"):
            assert (tmp_path / name / f).read_text() == (ROOT / "connectors" / name / f).read_text(), \
                f"connectors/{name}/{f} is stale: run python scripts/build_connectors.py"
    assert "odcr-postgres" in names and "odcr-all" in names and "odcr-synapse" in names
