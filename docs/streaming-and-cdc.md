# Streaming, CDC, Event Hub and queue ingestion

odcr treats every load unit as a **batch_id**:

| Ingestion style | Good batch_id |
| --- | --- |
| Batch files | file name or load timestamp |
| CDC (IBM CDC, Debezium, ...) | commit / transaction batch or time window |
| Kafka / Event Hub | `partition-offsetFrom-offsetTo`, or the Spark `epoch_id` |
| Queues | message batch id |
| Spark Structured Streaming | `epoch-<epoch_id>` from `foreachBatch` |

For each micro-batch, the job does three things:

```python
checkpoint(db, pipeline="orders_stream", stage="queue", batch_id=batch_id,
           row_count=rows_received, mode="streaming", config=config)       # what arrived
# ... write the micro-batch, tagging rows with load_id = batch_id ...
run_contract(contract, db, config, batch_id=batch_id, where=f"load_id = '{batch_id}'",
             pipeline="orders_stream", stage="bronze")                     # what landed, checked
```

Then `odcr trace --pipeline orders_stream --batch-id <id>` shows queue → bronze → ... with row loss flagged.

See `examples/streaming_microbatch.py`. Native Kafka, Event Hub and Spark/Databricks adapters are on the roadmap.
