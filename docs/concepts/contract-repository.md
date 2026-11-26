# The central contract repository

The one prerequisite for odcr is a **central repository of data contracts**: ODCS YAML files, one per dataset,
reviewed through pull requests like code. Producers change a contract in a pull request; consumers review it;
CI validates it (`odcr lint`); every pipeline that lands data enforces the version on `main`.

```text
data-contracts/                    (a Git repository: GitHub, Azure DevOps, GitLab, Bitbucket)
├── contracts/
│   ├── sales/orders.odcs.yaml
│   ├── sales/customers.odcs.yaml
│   └── finance/ledger.odcs.yaml
└── .github/workflows/contracts.yml   odcr lint contracts  (created by odcr init)
```

## Point odcr at it

```yaml
# odcr.yaml — a folder (local, mounted, or a network share)
contracts:
  path: contracts

# or straight from Git: cloned into a local cache and refreshed on every run
contracts:
  git: https://github.com/acme/data-contracts.git      # SSH works too: git@github.com:acme/data-contracts.git
  ref: main
  path: contracts
  token_env: GIT_TOKEN                                  # HTTPS token for private repositories (optional)
```

The cache lives in `~/.cache/odcr` (override with `ODCR_CACHE_DIR`). Git must be installed for the `git:` form.

## Finding a contract

```bash
odcr contracts                                    # list: id, version, objects, file
odcr run --contract-id orders                     # by id
odcr run --for-object sales.orders                # by the table it describes
odcr run --for-object abfss://landing@lake.dfs.core.windows.net/orders/2026/11/26/part-1.parquet   # file globs match
odcr lint                                         # validate the whole repository
```

Contract ids must be unique; `odcr lint` and `odcr doctor` report duplicates and invalid files.
