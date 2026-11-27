# Databricks (Workflows, Auto Loader, DLT)

Install as a job or cluster library: `odcr-databricks` (PyPI). Store `odcr.yaml` and the contract repository in
a Git folder / workspace files, and the token in a secret scope.

**Workflow task after the load:**

```python
import os
from odcr import run_contract
from odcr.adapters import get_adapter
from odcr.config import load_config
from odcr.repository import ContractRepository

os.environ["DATABRICKS_TOKEN"] = dbutils.secrets.get("odcr", "token")
config = load_config("/Workspace/Repos/data/contracts/odcr.yaml")
contract = ContractRepository.from_config(config).get("orders")
batch = dbutils.widgets.get("load_id")
with get_adapter(config.connection("main")) as db:
    result = run_contract(contract, db, config, batch_id=batch, where=f"load_id = '{batch}'")
if not result.passed:
    raise Exception(result.summary())       # fails the task and the job
```

**Auto Loader / Structured Streaming:** call the same code inside `foreachBatch` with `batch_id =
f"epoch-{epoch_id}"` (see [When data lands](../concepts/when-data-lands.md)).

**Files before they are loaded:** use the `files` adapter on the landing path (`abfss://`, `s3://`, `gs://`).
