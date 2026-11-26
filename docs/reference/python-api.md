# Python API

```python
from odcr import (ContractRepository, checkpoint, load_contract, load_reconciliation, run_contract,
                  run_reconciliation, trace)
from odcr.adapters import get_adapter
from odcr.config import load_config
from odcr.watch import watch_once

config = load_config("odcr.yaml")                         # also loads .env next to it
contract = ContractRepository.from_config(config).get("orders")

with get_adapter(config.connection("main")) as db:
    result = run_contract(contract, db, config, batch_id="42", where="load_id = '42'",
                          pipeline="orders", stage="ingestion")
    result.status        # "pass" | "warn" | "fail"
    result.passed        # False only for "fail"
    result.summary()     # human-readable
    result.to_dict()     # every check, value and notification

    checkpoint(db, pipeline="orders", stage="gold", batch_id="42", object_name="gold.orders",
               where="load_id = '42'", config=config)
    for step in trace(db, pipeline="orders", batch_id="42", config=config):
        print(step.stage, step.row_count, step.flag)

    for event in watch_once(contract, db, config, batch_column="load_id"):
        print(event.batch_id, event.result.status)

recon = load_reconciliation("reconciliations/orders.recon.yaml")
with get_adapter(config.connection("erp")) as src, get_adapter(config.connection("main")) as tgt:
    print(run_reconciliation(recon, src, tgt, config, batch_id="42").summary())
```

Store results on another platform: `run_contract(..., meta=get_adapter(config.connection("central")))`.
