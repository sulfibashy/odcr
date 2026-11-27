# Azure Data Factory and Synapse pipelines

After the Copy / Data Flow activity that lands the batch, add one of:

1. **Databricks Python activity / notebook** (if you use Databricks): `%pip install odcr-databricks` and the
   [Python API](../reference/python-api.md).
2. **Azure Function activity**: a small HTTP function with `odcr-<adapter>` in `requirements.txt` that runs
   `run_contract` and returns HTTP 500 when the contract fails.
3. **Custom activity (Azure Batch)** or a self-hosted integration runtime VM running
   `odcr run --contract-id orders --batch-id @{pipeline().RunId} --where "load_id = '@{pipeline().RunId}'"`.

For file arrivals in ADLS, a **storage event trigger** (Blob created) can start the pipeline that runs
`odcr run --for-object @{triggerBody().folderPath}/@{triggerBody().fileName}` with the `files` adapter.

Use a managed identity: the `files` adapter (ADLS), `sqlserver` / `synapse` / `fabric`
(`authentication: ActiveDirectoryMsi`) and `cosmosdb` (no key → `DefaultAzureCredential`) all support it.
