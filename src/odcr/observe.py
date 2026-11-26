"""End-to-end observability: checkpoints per stage, per batch or micro-batch, and a trace across stages.

Works the same for batch, streaming, CDC and queue-based loads: each load unit
(a batch, a micro-batch, an offset range or a time window) gets a `batch_id`,
and each stage records how many rows it saw for that batch_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from .adapters.base import Adapter
from .checks import relation
from .config import Config
from .meta import ensure_meta, table_name

DEFAULT_STAGE_ORDER = {
    "source": 0, "extract": 5, "ingestion": 10, "queue": 12, "landing": 20, "raw": 30, "bronze": 30,
    "staging": 35, "silver": 40, "gold": 50, "mart": 55, "serving": 58, "consumption": 60,
}
MODES = {"batch", "streaming", "cdc", "queue", "microbatch"}


def _utcnow():  # local import avoids a cycle with runner
    from .runner import utcnow
    return utcnow()


def record_event(adapter: Adapter, schema: str, *, pipeline: str, stage: str, batch_id: str | None,
                 object_name: str | None = None, row_count: int | None = None, status: str = "ok",
                 mode: str = "batch", stage_order: int | None = None, details: str | None = None) -> str:
    event_id = uuid.uuid4().hex
    if stage_order is None:
        stage_order = DEFAULT_STAGE_ORDER.get(stage.lower())
    adapter.insert(table_name(adapter, schema, "pipeline_events"), {
        "event_id": event_id, "pipeline": pipeline, "stage": stage, "stage_order": stage_order,
        "batch_id": batch_id, "mode": mode, "object_name": object_name, "row_count": row_count,
        "status": status, "details": details, "event_time": _utcnow(),
    })
    return event_id


def checkpoint(adapter: Adapter, *, pipeline: str, stage: str, batch_id: str | None,
               row_count: int | None = None, object_name: str | None = None, where: str | None = None,
               mode: str = "batch", status: str = "ok", stage_order: int | None = None,
               details: str | None = None, config: Config | None = None) -> str:
    """Record that `stage` processed `batch_id`.

    Pass `row_count` directly (e.g. from a Kafka/Event Hub consumer or Spark foreachBatch), or pass
    `object_name` (+ optional `where`) and the count is taken from the table.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    config = config or Config()
    adapter.connect()
    ensure_meta(adapter, config.meta_schema)
    if row_count is None and object_name:
        row_count = int(adapter.scalar(f"SELECT COUNT(*) FROM {relation(adapter, object_name, where)}"))
    return record_event(adapter, config.meta_schema, pipeline=pipeline, stage=stage, batch_id=batch_id,
                        object_name=object_name, row_count=row_count, status=status, mode=mode,
                        stage_order=stage_order, details=details)


@dataclass
class TraceStep:
    stage: str
    stage_order: int | None
    object_name: str | None
    row_count: int | None
    status: str
    mode: str
    event_time: Any
    change: int | None = None  # rows gained (+) or lost (-) versus the previous stage
    flag: str = ""


def trace(adapter: Adapter, *, pipeline: str, batch_id: str, config: Config | None = None,
          tolerance: int = 0) -> list[TraceStep]:
    """The journey of one batch through every stage, flagging row loss or gain between stages."""
    config = config or Config()
    adapter.connect()
    ensure_meta(adapter, config.meta_schema)
    p = adapter.placeholder
    rows = adapter.fetchall(
        f"SELECT stage, stage_order, object_name, row_count, status, mode, event_time "
        f"FROM {table_name(adapter, config.meta_schema, 'pipeline_events')} "
        f"WHERE pipeline = {p} AND batch_id = {p}", (pipeline, batch_id))
    rows.sort(key=lambda r: (r[1] if r[1] is not None else 10_000, r[6]))
    steps: list[TraceStep] = []
    prev: int | None = None
    for stage, order, obj, count, status, mode, ts in rows:
        step = TraceStep(stage, order, obj, None if count is None else int(count), status, mode, ts)
        if prev is not None and step.row_count is not None:
            step.change = step.row_count - prev
            if step.change < -tolerance:
                step.flag = f"lost {-step.change} rows"
            elif step.change > tolerance:
                step.flag = f"gained {step.change} rows"
        if status in ("fail", "failed", "error"):
            step.flag = (step.flag + "; " if step.flag else "") + f"stage status {status}"
        if step.row_count is not None:
            prev = step.row_count
        steps.append(step)
    return steps
