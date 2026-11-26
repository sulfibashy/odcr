# Integrations

ETL tools and orchestrators are not adapters: the data they move lands in a platform odcr already supports, and
they call odcr right after the load. Every integration uses the same contract: **exit code 0 = pass or warn,
1 = the batch broke the contract, 2 = configuration problem.**

| Tool | How | Page |
| --- | --- | --- |
| Apache Airflow | `OdcrContractOperator`, `OdcrReconcileOperator`, `OdcrCheckpointOperator` | [Airflow](airflow.md) |
| Informatica PowerCenter / IDMC | post-session command or Command Task | [Informatica](informatica.md) |
| Ab Initio | Run Program component / Conduct>It plan task | [Ab Initio](abinitio.md) |
| Azure Data Factory / Synapse pipelines | Databricks / Azure Function / Batch activity | [Azure Data Factory](azure-data-factory.md) |
| Databricks Workflows, Auto Loader, DLT | Python task, `foreachBatch`, wheel task | [Databricks](databricks.md) |
| SSIS, SQL Server Agent, Control-M, Autosys, cron | `jobs/ingestion_gate.ps1` / `.sh` | [Schedulers](schedulers.md) |
| dbt | `on-run-end` / post-hook calling `odcr run` | [Schedulers](schedulers.md) |
| CI/CD (GitHub Actions, Azure DevOps) | validate contracts on every pull request | [CI/CD](ci-cd.md) |
