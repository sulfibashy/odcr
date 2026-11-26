"""Ingestion gate: call this the moment a batch, micro-batch, CDC transaction or file has landed.

    python jobs/ingestion_gate.py batch-001
"""

import sys

from odcr import checkpoint, run_contract
from odcr.adapters import get_adapter
from odcr.config import load_config
from odcr.repository import ContractRepository

WHERE = "c.load_id = '{batch_id}'"  # filter selecting one batch on this platform
batch_id = sys.argv[1] if len(sys.argv) > 1 else "batch-001"
config = load_config("odcr.yaml")
contract = ContractRepository.from_config(config).get("orders")

with get_adapter(config.connection("main")) as db:
    # 1. What the source says it sent (from the file manifest, the CDC log or the Kafka / Event Hub offsets)
    checkpoint(db, pipeline="orders", stage="source", batch_id=batch_id, row_count=4, config=config)
    # 2. Check exactly this batch against the contract; logs, quarantines and notifies on failure
    result = run_contract(contract, db, config, batch_id=batch_id, where=WHERE.replace("{batch_id}", batch_id),
                          pipeline="orders", stage="ingestion")
    print(result.summary())
    sys.exit(0 if result.passed else 1)
