"""Pattern for streaming, CDC, Event Hub, Kafka or queue ingestion.

Each micro-batch (an offset range, a time window, a CDC transaction batch) gets a batch_id.
The job records what the queue delivered, writes the micro-batch, then lets odcr check it.

Shown with Spark Structured Streaming's foreachBatch; the same three calls work in any consumer loop.
(Native Spark / Databricks, Kafka and Event Hub adapters are on the roadmap.)
"""

from pyspark.sql import functions as F

from odcr import checkpoint, load_contract, run_contract
from odcr.adapters import get_adapter
from odcr.config import load_config

config = load_config("odcr.yaml")
contract = load_contract("contracts/orders.odcs.yaml")


def process_microbatch(batch_df, epoch_id: int) -> None:  # Spark foreachBatch signature
    batch_id = f"epoch-{epoch_id}"
    rows = batch_df.count()
    with get_adapter(config.connection("postgres-dev")) as db:
        checkpoint(db, pipeline="orders_stream", stage="queue", batch_id=batch_id, row_count=rows,
                   mode="streaming", config=config)
        (batch_df.withColumn("load_id", F.lit(batch_id))
         .write.jdbc(url="jdbc:postgresql://localhost/odcr", table="orders", mode="append"))
        result = run_contract(contract, db, config, batch_id=batch_id, where=f"load_id = '{batch_id}'",
                              pipeline="orders_stream", stage="bronze")
        if not result.passed:
            # quarantine is already logged and teams are notified; decide whether to stop the stream
            print(result.summary())


# stream.writeStream.foreachBatch(process_microbatch).start()
