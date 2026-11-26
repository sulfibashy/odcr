# Project structure

`odcr init` creates:

```text
my_contracts/
├── odcr.yaml                         connections, meta tables, notifications, contract repository
├── .env.example                      every environment variable the connection needs
├── contracts/
│   └── sales/orders.odcs.yaml        one ODCS contract per dataset
├── reconciliations/orders.recon.yaml source-versus-target checks
├── seeds/orders.csv                  sample data (`odcr seed`)
├── jobs/
│   ├── ingestion_gate.py             Python / Spark / Airflow
│   ├── ingestion_gate.sh             Linux, macOS, Unix schedulers, Informatica, Ab Initio
│   └── ingestion_gate.ps1            Windows, SQL Server Agent, SSIS
├── tests/test_contracts.py           pytest: every contract is valid
├── .github/workflows/contracts.yml   GitHub Actions: validate contracts on every pull request
├── azure-pipelines.yml               Azure DevOps: the same
├── README.md
└── .gitignore
```

## odcr.yaml

```yaml
name: my_contracts
contracts:                       # the central contract repository
  path: contracts                # or: git: https://github.com/acme/data-contracts.git, ref: main, path: contracts
connections:
  main:                          # the default connection (-C main)
    type: postgres
    host: ${PGHOST}
    ...
  lake:
    type: files
    storage: azure
    account_name: ${AZURE_STORAGE_ACCOUNT}
meta:
  schema: odcr_meta              # meta tables live here on each platform
  # connection: main             # or store all results on one platform
on_fail: quarantine              # or: log
notifications:
  notify_on: [fail, warn]
  platform_team:
    - type: teams
      url: ${PLATFORM_TEAMS_WEBHOOK}
  smtp: {host: smtp.example.com, port: 587, starttls: true, user: ${SMTP_USER}, password: ${SMTP_PASSWORD}}
```

Every example in [`examples/`](https://github.com/sulfibashy/odcr/tree/main/examples) is a complete project
for one adapter.
