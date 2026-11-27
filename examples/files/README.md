# files_example

Data contracts and data quality checks with [odcr](https://github.com/sulfibashy/odcr) on **Files: ADLS, S3, GCS, local**.

## Setup

```bash
pip install "odcr[files]"
cp .env.example .env        # fill in connection details (Windows: copy .env.example .env)
odcr doctor -C main         # test the connection, TLS and permissions
odcr meta-init -C main      # create the meta tables
odcr seed -C main           # optional: load the sample orders data
```

## Check data when it lands

```bash
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
odcr run --contract-id orders -C main --batch-id batch-002 --where "load_id = 'batch-002'"   # fails on purpose
odcr watch --contract-id orders -C main --once     # every new file, once
odcr history -C main
```

From a pipeline: `jobs/ingestion_gate.sh` (Linux/macOS/Unix), `jobs/ingestion_gate.ps1` (Windows) or
`jobs/ingestion_gate.py` (Python, Spark, Airflow). Exit code 1 means the batch broke the contract.

## Layout

| Path | What it is |
| --- | --- |
| `contracts/` | The contract repository: one ODCS YAML per dataset. Point `odcr.yaml` to a shared Git repo instead if you have one. |
| `reconciliations/` | Source-versus-target comparisons per batch. |
| `seeds/` | Sample data. |
| `jobs/` | Scripts your scheduler or ETL tool calls. |
| `tests/` | `pytest` validates every contract. |
| `.github/`, `azure-pipelines.yml` | CI that validates contracts on every pull request. |
| `pipelines/` | Templates: ingestion → contract gate → transformation, for Azure DevOps and GitHub Actions. |
