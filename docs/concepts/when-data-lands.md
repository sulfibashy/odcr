# Checking data the moment it lands

How data arrives does not matter. What matters is the **load unit** and where it lands.

| Ingestion | Load unit (`batch_id`) | Lands in |
| --- | --- | --- |
| Batch file / ETL load | file name or load id | ADLS / S3 / GCS / folder, or a table |
| CDC (IBM CDC, Debezium, ADF, GoldenGate) | transaction batch or time window | a table (bronze / staging) |
| Streaming (Event Hub, Kafka, Kinesis) | offset range or Spark `epoch_id` | a Delta / Iceberg table or files |
| Queues (Service Bus, SQS, MQ) | message batch id | a table or files |

## Three ways to trigger the check

**1. Right after the load, from the pipeline** (recommended): the job that lands data calls odcr and stops
on exit code 1.

```bash
odcr run --contract-id orders --batch-id "$LOAD_ID" --where "load_id = '$LOAD_ID'" --pipeline orders --stage bronze
```

**2. Watch for new data** — a small always-on service, or a scheduler running `--once`:

```bash
odcr watch --contract-id orders --batch-column load_id --interval 60     # tables: every new load_id
odcr watch --contract-id orders -C lake --once                           # files: every new file in the glob
```

Processed batches are remembered in the `pipeline_events` meta table, so nothing is checked twice, even after a
restart.

**3. Storage events** — Azure Event Grid (Blob Created), S3 Event Notifications or a Databricks file arrival
trigger start a Function / Lambda / job that runs `odcr run --for-object <path that arrived>`.

## Files in ADLS, S3, GCS or a landing folder

```yaml
connections:
  lake:
    type: files
    storage: azure                         # local | azure | s3 | gcs
    account_name: ${AZURE_STORAGE_ACCOUNT}  # auth: managed identity / az login by default
```

```yaml
schema:
  - name: orders
    physicalName: abfss://landing@mylake.dfs.core.windows.net/orders/*/*.parquet
```

Files are read in place (DuckDB engine), so checking needs no loading and no cluster.

## Streaming micro-batches (Spark)

```python
def check(batch_df, epoch_id):
    batch_id = f"epoch-{epoch_id}"
    batch_df.withColumn("load_id", F.lit(batch_id)).write.mode("append").saveAsTable("bronze.orders")
    with get_adapter(config.connection("main")) as db:
        result = run_contract(contract, db, config, batch_id=batch_id,
                              where=f"load_id = '{batch_id}'", pipeline="orders_stream", stage="bronze")

stream.writeStream.foreachBatch(check).start()
```
