"""Check data the moment it lands, whatever brought it there (batch, streaming, CDC, events, file drops).

Two ways to detect new data:

* Files (local, ADLS, S3, GCS): every new file matching the contract's physicalName glob is checked
  on its own; the file path is the batch id.
* Tables: every new value of a batch column (load_id, ingestion timestamp, CDC transaction id, Kafka
  offset range, streaming micro-batch id) is checked as one batch.

Processed batches are recorded in the pipeline_events meta table, so a restart never checks twice.
Run it as a long-lived service (`odcr watch`), from a scheduler (`odcr watch --once`), or from an
event trigger (Azure Event Grid / S3 events / Databricks file arrival triggers calling `odcr run`).
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from dataclasses import dataclass

from .adapters.base import Adapter
from .config import Config
from .contract import Contract
from .runner import RunResult, run_contract


@dataclass
class WatchEvent:
    batch_id: str
    object_name: str
    result: RunResult


def _seen(meta: Adapter, config: Config, pipeline: str, batch_id: str) -> bool:
    return meta.meta_count(config.meta_schema, "pipeline_events", {"pipeline": pipeline, "batch_id": batch_id}) > 0


def watch_once(contract: Contract, adapter: Adapter, config: Config, *, batch_column: str | None = None,
               meta: Adapter | None = None, pipeline: str | None = None, stage: str = "landing",
               send_notifications: bool = True, limit: int = 1000) -> list[WatchEvent]:
    """Check every batch or file that arrived since the last call. Returns what was checked."""
    meta = meta or adapter
    adapter.connect()
    meta.connect()
    meta.meta_ensure(config.meta_schema)
    pipeline = pipeline or f"watch:{contract.id}"
    events: list[WatchEvent] = []
    for obj in contract.schema:
        lister = getattr(adapter, "list_files", None)
        if lister is not None and batch_column is None and "(" not in obj.physical_name:
            for path in lister(obj.physical_name)[:limit]:
                if _seen(meta, config, pipeline, path):
                    continue
                single = dataclasses.replace(contract, schema=[dataclasses.replace(obj, physical_name=path)])
                res = run_contract(single, adapter, config, batch_id=path, pipeline=pipeline, stage=stage,
                                   send_notifications=send_notifications, meta=meta)
                events.append(WatchEvent(path, obj.name, res))
            continue
        if not batch_column:
            raise ValueError(f"{obj.name} is a table: pass batch_column (e.g. load_id) to detect new batches")
        values = adapter.distinct_values(obj.physical_name, None, batch_column, limit)
        for value in sorted(str(v) for v in values if v is not None):
            if _seen(meta, config, pipeline, value):
                continue
            where = (f'{{"{batch_column}": "{value}"}}' if adapter.kind == "document"
                     else f"{adapter.quote(batch_column)} = {adapter.literal(value)}")
            res = run_contract(contract, adapter, config, batch_id=value, where=where, objects=[obj.name],
                               pipeline=pipeline, stage=stage, send_notifications=send_notifications, meta=meta)
            events.append(WatchEvent(value, obj.name, res))
    return events


def watch(contract: Contract, adapter: Adapter, config: Config, *, interval: float = 60.0,
          on_event: Callable[[WatchEvent], None] | None = None, max_cycles: int | None = None,
          **kwargs: object) -> None:
    """Poll forever (or `max_cycles` times), checking new data as it lands."""
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        for event in watch_once(contract, adapter, config, **kwargs):  # type: ignore[arg-type]
            if on_event:
                on_event(event)
        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            time.sleep(interval)
