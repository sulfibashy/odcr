# End-to-end observability

Every stage records a checkpoint per batch; `odcr trace` shows the journey and flags lost or gained rows.

```bash
odcr checkpoint --pipeline orders --stage source --batch-id 42 --rows 1200
odcr run --contract-id orders --batch-id 42 --where "load_id='42'" --pipeline orders --stage ingestion
odcr checkpoint --pipeline orders --stage gold --batch-id 42 --object gold.orders --where "load_id='42'"
odcr checkpoint --pipeline orders --stage consumption --batch-id 42 --rows 1188 --mode batch
odcr trace --pipeline orders --batch-id 42
```

```text
source             1200 rows           batch      ok
ingestion          1200 rows (+0)      batch      pass   orders
gold               1188 rows (-12)     batch      ok     gold.orders  <-- lost 12 rows
consumption        1188 rows (+0)      batch      ok
```

Known stages are ordered automatically: source, extract, ingestion, queue, landing, raw / bronze, staging,
silver, gold, mart, serving, consumption. Modes: `batch`, `streaming`, `cdc`, `queue`, `microbatch`.

Because every result is in ordinary tables on your platform, any BI tool (Power BI, Tableau, Databricks SQL,
Grafana) can show contract health, failures by source team, and trends.
