"""Every contract in the repository must be valid ODCS. Run with: pytest"""

from pathlib import Path

from odcr.repository import ContractRepository


def test_all_contracts_are_valid():
    repo = ContractRepository.load(Path(__file__).parent.parent / "contracts")
    assert repo.contracts, "no contracts found"
    assert not repo.errors, repo.errors
