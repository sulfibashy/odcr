# Running in pipelines

The gate belongs **after ingestion and before transformation**: if a batch breaks its contract, odcr exits with
code 1, the pipeline stops, and nothing downstream consumes bad data. Optionally, run a second gate **after
transformation** on what you publish (gold tables, data products).

```text
ingest  ──►  odcr run (contract gate)  ──►  transform (dbt / Databricks / SQL)  ──►  odcr run (output gate)
                 │ fail: exit 1, quarantine, alert
                 ▼
               stop
```

`odcr init` generates both templates in `pipelines/`.

## Contracts in another repository

Contracts are rarely in the pipeline's own repository. odcr reads them straight from Git on every run (cached,
refreshed with a shallow fetch):

| Way | Example |
| --- | --- |
| `odcr.yaml` | `contracts: {git: https://dev.azure.com/acme/data/_git/contracts, ref: main, path: contracts, token_env: GIT_TOKEN}` |
| Command line | `odcr run --contracts https://github.com/acme/data-contracts.git --contracts-ref main --contract-id orders` |
| Environment | `ODCR_CONTRACTS=...`, `ODCR_CONTRACTS_REF=main`, `ODCR_CONTRACTS_PATH=contracts` |
| No project at all | `odcr lint https://github.com/acme/data-contracts.git` |

**Authentication without stored secrets:**

| Where odcr runs | How it reads the contract repository |
| --- | --- |
| Azure DevOps pipeline | `GIT_TOKEN: $(System.AccessToken)` (grant the build service *Read* on the contract repo) |
| GitHub Actions | `GIT_TOKEN: ${{ secrets.CONTRACTS_REPO_TOKEN }}` (fine-grained, read-only) or a GitHub App token |
| GitLab CI | `GIT_TOKEN: $CI_JOB_TOKEN` with `token_user: gitlab-ci-token` |
| Servers / laptops | nothing: SSH keys (`git@...` URLs) or Git Credential Manager / `az login` / `gh auth login` |

Any Git host works: GitHub, GitHub Enterprise, Azure Repos, GitLab, Bitbucket, Gitea, on-premise servers.

## Azure DevOps

```yaml
variables:
  - group: odcr-secrets                    # Key Vault-linked variable group
  - name: ODCR_CONTRACTS
    value: https://dev.azure.com/acme/data-platform/_git/data-contracts

stages:
  - stage: ingest
    jobs: [ ... your ingestion ... ]

  - stage: contract_gate
    dependsOn: ingest
    jobs:
      - job: odcr
        steps:
          - task: UsePythonVersion@0
            inputs: {versionSpec: "3.12"}
          - script: pip install "odcr[databricks]"
          - script: |
              odcr run --contract-id orders --batch-id "$(LOAD_ID)" \
                --where "load_id = '$(LOAD_ID)'" --pipeline orders --stage ingestion
            env:
              GIT_TOKEN: $(System.AccessToken)
              DATABRICKS_TOKEN: $(DATABRICKS_TOKEN)

  - stage: transform
    dependsOn: contract_gate               # runs only if the gate passed
    jobs: [ ... dbt build / Databricks job ... ]
```

Use a **self-hosted agent** (or a managed DevOps pool in your VNet) when the platforms are not reachable from
Microsoft-hosted agents. Prefer workload identity federation / managed identity service connections over
passwords for Azure platforms.

## GitHub Actions

```yaml
jobs:
  contract_gate:
    needs: ingest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with: {python-version: "3.12"}
      - run: pip install "odcr[snowflake]"
      - run: |
          odcr run --contracts https://github.com/acme/data-contracts.git --contract-id orders \
            --batch-id "${{ inputs.load_id }}" --where "load_id = '${{ inputs.load_id }}'"
        env:
          GIT_TOKEN: ${{ secrets.CONTRACTS_REPO_TOKEN }}
  transform:
    needs: contract_gate
```

## Other orchestrators

Airflow (`OdcrContractOperator`), Azure Data Factory, Databricks Workflows, Informatica, Ab Initio, SSIS and
schedulers: see [Integrations](../integrations/index.md). All of them use the same rule: **exit code 0 continue,
1 stop, 2 fix the configuration.**
