# Architecture and flow

odcr is a command-line tool and Python library. It runs where your pipelines run (a pipeline agent, a
scheduler server, a Databricks job, a container) and connects to the platforms where data lands. There is no
server to operate and no central database to install: results are written to meta tables on your own platforms.

## End to end

```mermaid
flowchart LR
    subgraph SRC[Sources]
        S1[Applications / ERP]
        S2[Event Hub / Kafka]
        S3[CDC: IBM CDC, Debezium]
        S4[Files: SFTP, MFT]
    end
    subgraph ING[Ingestion]
        I1[ADF / Informatica / Ab Initio / Databricks / Spark]
    end
    subgraph LAND[Where data lands]
        L1[(Database / warehouse / lakehouse table)]
        L2[(Files: ADLS, S3, GCS, landing folder)]
    end
    subgraph GIT[Central contract repository]
        C1[contracts/*.odcs.yaml<br/>GitHub / Azure Repos / GitLab]
    end
    subgraph ODCR[odcr gate]
        O1[odcr run / odcr watch]
    end
    subgraph OUT[Results]
        M1[(odcr_meta tables<br/>on the same platform)]
        N1[Teams / Slack / email /<br/>PagerDuty / Opsgenie]
    end
    T1[Transformation<br/>dbt / Databricks / SQL]
    G1[(Gold / data products)]

    S1 & S2 & S3 & S4 --> I1 --> L1 & L2
    C1 -- read on every run --> O1
    L1 & L2 -- check batch --> O1
    O1 -- pass: exit 0 --> T1 --> G1
    O1 -- fail: exit 1 + quarantine --> N1
    O1 --> M1
    G1 -- output contract --> O1
```

1. Producers and consumers agree on a contract in the **contract repository** (pull request, review, CI lint).
2. Data arrives by any route — batch, CDC, stream, file — and **lands** in a table or in files.
3. Right after landing, the pipeline (or `odcr watch`) runs **the gate**: odcr reads the contract from Git and
   checks only that batch on the platform where it landed.
4. **Pass** (exit 0): the pipeline continues to transformation. **Fail** (exit 1): the batch is quarantined, the
   source team and the platform team are notified, and the pipeline stops before bad data spreads.
5. Every run, rule result, alert, reconciliation and stage checkpoint is stored in the **meta tables**.
6. Optionally, the same gate runs on what you publish (gold tables, data products), and `odcr reconcile` /
   `odcr trace` confirm nothing was lost between stages.

## What happens inside `odcr run`

```mermaid
sequenceDiagram
    participant P as Pipeline step
    participant O as odcr
    participant G as Contract repo (Git)
    participant D as Platform (DB / files)
    participant M as Meta tables
    participant N as Teams / Slack / email
    P->>O: odcr run --contract-id orders --batch-id 42 --where "load_id='42'"
    O->>G: clone / fetch (cached), find contract "orders"
    O->>D: read the catalog: columns and types (schema checks)
    O->>D: one query per rule, limited to batch 42 (quality checks)
    O->>M: validation_runs, check_results (+ quarantine_log on failure)
    alt contract broken
        O->>N: source team (from the contract) + platform team
        O->>M: notifications
        O-->>P: exit 1 (stop the pipeline)
    else contract met
        O-->>P: exit 0 (continue)
    end
```

odcr pushes the work down to the platform: each rule is one aggregate query (`COUNT(*) ... WHERE ...`), so no
data leaves the platform and checks scale with the platform, not with the machine running odcr.

## Components

| Component | Where it lives | What it is |
| --- | --- | --- |
| `odcr` CLI / Python package | pipeline agent, scheduler host, container, Databricks cluster | `pip install "odcr[<adapter>]"` |
| Project (`odcr.yaml`) | a Git repository of the data / platform team | connections, meta schema, alerts, where the contracts are |
| Contract repository | GitHub, Azure Repos, GitLab, Bitbucket, or a folder | ODCS YAML, reviewed by producers and consumers |
| Adapters | inside the package | 18 platforms; one small class each |
| Meta tables | `odcr_meta` schema on each platform (or one central platform) | history for audits and dashboards |
| Alert channels | Teams, Slack, email, Google Chat, Discord, PagerDuty, Opsgenie, webhooks | source team + platform team |

## Deployment options

| Option | When |
| --- | --- |
| A step in the ingestion pipeline (Azure DevOps, GitHub Actions, ADF, Airflow, Databricks Workflows) | recommended: the gate sits between ingestion and transformation |
| `odcr watch` as a small service (VM, container, Kubernetes) | data arrives continuously and no pipeline owns the moment of landing |
| Storage event → Function / Lambda → `odcr run --for-object <file>` | files dropped in ADLS / S3 / GCS |
| Scheduler (`odcr watch --once` every N minutes) | simple setups, on-premise schedulers |

See [Running in pipelines](getting-started/pipelines.md) for ready-made Azure DevOps and GitHub Actions
templates, and [Commands](reference/cli.md) for every command.
