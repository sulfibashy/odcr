# Reconciliation

Does the target hold exactly what the source sent, for this batch? Source and target can be on different
platforms (Oracle to Snowflake, SQL Server to Databricks, files in ADLS to PostgreSQL).

```yaml
kind: Reconciliation
id: orders-oracle-to-databricks
contract: orders
source: {connection: oracle_erp, object: sales.orders, where: "load_id = '{batch_id}'"}
target: {connection: lakehouse, object: bronze.orders, where: "load_id = '{batch_id}'"}
checks:
  - type: rowCount
  - type: sum
    column: amount
    tolerance: 0.01            # or tolerancePercent: 0.1
  - type: distinctCount
    column: customer_id
  - type: max
    column: order_date
  - type: missingKeys          # lists keys missing on either side
    column: order_id
```

```bash
odcr reconcile reconciliations/orders.recon.yaml --batch-id 42
```

Check types: `rowCount`, `sum`, `min`, `max`, `distinctCount`, `nullCount`, `missingKeys`. Use `sourceColumn` /
`targetColumn` when names differ. Results go to `reconciliation_runs` and `reconciliation_results`.
