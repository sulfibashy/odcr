"""Apache Airflow operators (Airflow 2.x and 3.x). Install Airflow separately; odcr does not depend on it.

    from odcr.integrations.airflow import OdcrContractOperator

    gate = OdcrContractOperator(
        task_id="orders_contract_gate",
        config_path="/opt/odcr/odcr.yaml",
        contract_id="orders",
        connection="main",
        batch_id="{{ ds_nodash }}",
        where="load_id = '{{ ds_nodash }}'",
    )
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised only where Airflow is installed
    from airflow.models import BaseOperator
except ImportError:  # Airflow not installed: keep the module importable for docs and tests
    class BaseOperator:  # type: ignore[no-redef]
        template_fields: tuple[str, ...] = ()

        def __init__(self, task_id: str, **kwargs: Any) -> None:
            self.task_id = task_id


class _OdcrBase(BaseOperator):
    def __init__(self, *, config_path: str, connection: str = "main", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.config_path = config_path
        self.connection = connection

    def _config(self):
        from odcr.config import load_config

        return load_config(self.config_path)


class OdcrContractOperator(_OdcrBase):
    """Check a batch against its contract; the task fails when the contract is broken."""

    template_fields = ("batch_id", "where", "contract_id", "contract_path")

    def __init__(self, *, contract_id: str | None = None, contract_path: str | None = None,
                 batch_id: str | None = None, where: str | None = None, pipeline: str | None = None,
                 stage: str | None = "ingestion", fail_on_warn: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.contract_id, self.contract_path = contract_id, contract_path
        self.batch_id, self.where, self.pipeline, self.stage = batch_id, where, pipeline, stage
        self.fail_on_warn = fail_on_warn

    def execute(self, context: Any = None) -> dict[str, Any]:
        from odcr.adapters import get_adapter
        from odcr.contract import load_contract
        from odcr.repository import ContractRepository
        from odcr.runner import run_contract

        config = self._config()
        contract = load_contract(self.contract_path) if self.contract_path else \
            ContractRepository.from_config(config).get(str(self.contract_id))
        with get_adapter(config.connection(self.connection)) as db:
            result = run_contract(contract, db, config, batch_id=self.batch_id, where=self.where,
                                  pipeline=self.pipeline, stage=self.stage if self.pipeline else None)
        if result.status == "fail" or (self.fail_on_warn and result.status == "warn"):
            raise RuntimeError(result.summary())
        return result.to_dict()


class OdcrReconcileOperator(_OdcrBase):
    """Reconcile source and target for a batch; the task fails on any difference."""

    template_fields = ("batch_id", "spec_path")

    def __init__(self, *, spec_path: str, batch_id: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.spec_path, self.batch_id = spec_path, batch_id

    def execute(self, context: Any = None) -> dict[str, Any]:
        from odcr.adapters import get_adapter
        from odcr.reconcile import load_reconciliation, run_reconciliation

        config = self._config()
        recon = load_reconciliation(self.spec_path)
        with get_adapter(config.connection(recon.source.connection or self.connection)) as s, \
                get_adapter(config.connection(recon.target.connection or self.connection)) as t:
            result = run_reconciliation(recon, s, t, config, batch_id=self.batch_id)
        if not result.passed:
            raise RuntimeError(result.summary())
        return {"run_id": result.run_id, "status": result.status}


class OdcrCheckpointOperator(_OdcrBase):
    """Record a stage checkpoint for end-to-end tracing."""

    template_fields = ("batch_id",)

    def __init__(self, *, pipeline: str, stage: str, batch_id: str, row_count: int | None = None,
                 object_name: str | None = None, where: str | None = None, mode: str = "batch",
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.pipeline, self.stage, self.batch_id = pipeline, stage, batch_id
        self.row_count, self.object_name, self.where, self.mode = row_count, object_name, where, mode

    def execute(self, context: Any = None) -> str:
        from odcr.adapters import get_adapter
        from odcr.observe import checkpoint

        config = self._config()
        with get_adapter(config.connection(self.connection)) as db:
            return checkpoint(db, pipeline=self.pipeline, stage=self.stage, batch_id=self.batch_id,
                              row_count=self.row_count, object_name=self.object_name, where=self.where,
                              mode=self.mode, config=config)
