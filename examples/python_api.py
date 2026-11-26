"""Use odcr from Python, e.g. inside an ingestion job.

    python examples/python_api.py
"""

from odcr import checkpoint, load_contract, load_reconciliation, run_contract, run_reconciliation, trace
from odcr.adapters import get_adapter
from odcr.config import load_config

config = load_config("odcr.yaml")
contract = load_contract("contracts/orders.odcs.yaml")
batch_id = "2026-11-26T10"

with get_adapter(config.connection("postgres-dev")) as db:
    # 1. The source system says how many rows it sent
    checkpoint(db, pipeline="orders", stage="source", batch_id=batch_id, row_count=1200, config=config)

    # 2. Ingestion gate: check only this batch, log results, quarantine and notify on failure
    result = run_contract(contract, db, config, batch_id=batch_id, where=f"load_id = '{batch_id}'",
                          pipeline="orders", stage="ingestion")
    print(result.summary())
    if not result.passed:
        raise SystemExit("Batch rejected by the data contract")

    # 3. Later stages record their own checkpoints
    checkpoint(db, pipeline="orders", stage="gold", batch_id=batch_id, object_name="gold.orders",
               where=f"load_id = '{batch_id}'", config=config)

    # 4. See the whole journey of the batch, with row loss flagged
    for step in trace(db, pipeline="orders", batch_id=batch_id, config=config):
        print(step.stage, step.row_count, step.flag)

# 5. Reconcile source and target, even across platforms
recon = load_reconciliation("reconciliations/orders.recon.yaml")
with get_adapter(config.connection("postgres-dev")) as src, get_adapter(config.connection("mysql-dev")) as tgt:
    print(run_reconciliation(recon, src, tgt, config, batch_id=batch_id).summary())
