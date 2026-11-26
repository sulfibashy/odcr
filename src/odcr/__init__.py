"""odcr - Open Data Contract Runtime.

Enforce ODCS data contracts at ingestion, reconcile source and target,
and trace every batch from ingestion to consumption. Results and history
are stored in meta tables inside the platform the data lives in.
"""

__version__ = "0.2.1"

from .contract import Contract, load_contract  # noqa: E402
from .observe import checkpoint, trace  # noqa: E402
from .reconcile import ReconResult, load_reconciliation, run_reconciliation  # noqa: E402
from .repository import ContractRepository  # noqa: E402
from .runner import RunResult, run_contract  # noqa: E402

__all__ = [
    "__version__",
    "Contract",
    "load_contract",
    "RunResult",
    "run_contract",
    "ReconResult",
    "load_reconciliation",
    "run_reconciliation",
    "checkpoint",
    "trace",
    "ContractRepository",
]
