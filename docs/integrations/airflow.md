# Apache Airflow

```bash
pip install odcr-snowflake          # in the Airflow image / environment
```

```python
from odcr.integrations.airflow import OdcrCheckpointOperator, OdcrContractOperator, OdcrReconcileOperator

load = ...  # your ingestion task

gate = OdcrContractOperator(
    task_id="orders_contract_gate",
    config_path="/opt/airflow/odcr/odcr.yaml",
    contract_id="orders",
    connection="main",
    batch_id="{{ ds_nodash }}",
    where="load_id = '{{ ds_nodash }}'",
    pipeline="orders",                 # also records an end-to-end checkpoint
)
recon = OdcrReconcileOperator(task_id="orders_recon", config_path="/opt/airflow/odcr/odcr.yaml",
                              spec_path="/opt/airflow/odcr/reconciliations/orders.recon.yaml",
                              batch_id="{{ ds_nodash }}")
load >> gate >> recon >> transform
```

The task fails (and downstream tasks do not run) when the contract is broken. Results are also in the meta
tables and notifications go out as configured.
