# Commands

| Command | What it does |
| --- | --- |
| [`odcr init`](#odcr-init) | create a new odcr project (like dbt init) |
| [`odcr destroy`](#odcr-destroy) | delete a project created by odcr init (asks for confirmation) |
| [`odcr secret`](#odcr-secret) | store a password or token in the OS keychain (no plain-text secrets) |
| [`odcr adapters`](#odcr-adapters) | list supported platforms and how to install each |
| [`odcr doctor`](#odcr-doctor) | check a connection, its driver, the meta tables and the contracts |
| [`odcr seed`](#odcr-seed) | load the sample orders data into a connection |
| [`odcr lint`](#odcr-lint) | validate contract files or folders (default: the contract repository) |
| [`odcr contracts`](#odcr-contracts) | list the contracts in the contract repository |
| [`odcr meta-init`](#odcr-meta-init) | create the meta schema and tables |
| [`odcr run`](#odcr-run) | check a table, file or batch against its contract |
| [`odcr watch`](#odcr-watch) | check every new file or batch the moment it lands |
| [`odcr reconcile`](#odcr-reconcile) | compare source and target for a batch |
| [`odcr checkpoint`](#odcr-checkpoint) | record that a stage processed a batch |
| [`odcr trace`](#odcr-trace) | show a batch's journey through every stage |
| [`odcr history`](#odcr-history) | recent validation runs |

Exit codes: `0` pass or warn, `1` the data broke the contract (or a failure), `2` usage or configuration error. Every command accepts `--help`.

## odcr init

create a new odcr project (like dbt init)

```text
usage: odcr init [-h] [--adapter ADAPTER] [--name NAME] [--meta-schema META_SCHEMA]
                 [--alerts {slack,teams,email,none}] [--alerts-email ALERTS_EMAIL]
                 [--mail {smtp-relay,microsoft365,aws-ses,smtp,gmail}] [--mail-from MAIL_FROM]
                 [--no-input] [--force]
                 [directory]

positional arguments:
  directory             folder to create (default: a new folder named after the project)

options:
  -h, --help            show this help message and exit
  --adapter, -a ADAPTER
                        platform, e.g. postgres, snowflake, databricks (see: odcr adapters)
  --name NAME           project name (default: the directory name)
  --meta-schema META_SCHEMA
  --alerts {slack,teams,email,none}
                        platform team alert channel
  --alerts-email ALERTS_EMAIL
                        platform team email address
  --mail {smtp-relay,microsoft365,aws-ses,smtp,gmail}
                        how email is sent (default asks; smtp-relay with --no-input)
  --mail-from MAIL_FROM
                        sender address for email alerts
  --no-input            do not ask questions; use the options and defaults
  --force               write into a non-empty directory
```

## odcr destroy

delete a project created by odcr init (asks for confirmation)

```text
usage: odcr destroy [-h] [--yes] [directory]

positional arguments:
  directory   project folder (default: the current folder)

options:
  -h, --help  show this help message and exit
  --yes, -y   do not ask for confirmation
```

## odcr secret

store a password or token in the OS keychain (no plain-text secrets)

```text
usage: odcr secret [-h] [--stdin] {set,delete,check} name

positional arguments:
  {set,delete,check}
  name                secret name, used in odcr.yaml as ${keyring:NAME}

options:
  -h, --help          show this help message and exit
  --stdin             read the value from standard input (for automation)
```

## odcr adapters

list supported platforms and how to install each

```text
usage: odcr adapters [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json
```

## odcr doctor

check a connection, its driver, the meta tables and the contracts

```text
usage: odcr doctor [-h] [--config CONFIG] [--connection CONNECTION] [--json]
                   [--contracts CONTRACTS] [--contracts-ref CONTRACTS_REF]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --contracts CONTRACTS
                        contract repository: a folder or a Git URL (GitHub, Azure DevOps, GitLab,
                        ...); default: odcr.yaml or $ODCR_CONTRACTS
  --contracts-ref CONTRACTS_REF
                        branch or tag of a Git contract repository (default: main)
```

## odcr seed

load the sample orders data into a connection

```text
usage: odcr seed [-h] [--config CONFIG] [--connection CONNECTION] [--json] [--table TABLE]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --table TABLE         target table / collection / file path (default: orders)
```

## odcr lint

validate contract files or folders (default: the contract repository)

```text
usage: odcr lint [-h] [--config CONFIG] [--contracts CONTRACTS] [--contracts-ref CONTRACTS_REF]
                 [--datacontract-cli]
                 [paths ...]

positional arguments:
  paths

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG
  --contracts CONTRACTS
                        contract repository: a folder or a Git URL (GitHub, Azure DevOps, GitLab,
                        ...); default: odcr.yaml or $ODCR_CONTRACTS
  --contracts-ref CONTRACTS_REF
                        branch or tag of a Git contract repository (default: main)
  --datacontract-cli    also run `datacontract lint` if installed
```

## odcr contracts

list the contracts in the contract repository

```text
usage: odcr contracts [-h] [--config CONFIG] [--json] [--contracts CONTRACTS]
                      [--contracts-ref CONTRACTS_REF]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --json                machine-readable output
  --contracts CONTRACTS
                        contract repository: a folder or a Git URL (GitHub, Azure DevOps, GitLab,
                        ...); default: odcr.yaml or $ODCR_CONTRACTS
  --contracts-ref CONTRACTS_REF
                        branch or tag of a Git contract repository (default: main)
```

## odcr meta-init

create the meta schema and tables

```text
usage: odcr meta-init [-h] [--config CONFIG] [--connection CONNECTION] [--json]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
```

## odcr run

check a table, file or batch against its contract

```text
usage: odcr run [-h] [--contract-id CONTRACT_ID] [--for-object FOR_OBJECT] [--contracts CONTRACTS]
                [--contracts-ref CONTRACTS_REF] [--config CONFIG] [--connection CONNECTION]
                [--json] [--batch-id BATCH_ID] [--where WHERE] [--object OBJECT]
                [--pipeline PIPELINE] [--stage STAGE] [--fail-on-warn] [--no-notify]
                [contract]

positional arguments:
  contract              contract file (or use --contract-id / --for-object)

options:
  -h, --help            show this help message and exit
  --contract-id CONTRACT_ID
                        contract id in the contract repository
  --for-object FOR_OBJECT
                        find the contract describing this table / collection / path
  --contracts CONTRACTS
                        contract repository: a folder or a Git URL (GitHub, Azure DevOps, GitLab,
                        ...); default: odcr.yaml or $ODCR_CONTRACTS
  --contracts-ref CONTRACTS_REF
                        branch or tag of a Git contract repository (default: main)
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --batch-id BATCH_ID   id of the batch / micro-batch / CDC transaction / file
  --where WHERE         filter selecting the batch: SQL, or JSON for MongoDB
  --object OBJECT       only check this schema object (repeatable)
  --pipeline PIPELINE   pipeline name, to record an end-to-end checkpoint
  --stage STAGE         stage name for the checkpoint, e.g. landing, bronze, gold
  --fail-on-warn        exit 1 on warnings too
  --no-notify
```

## odcr watch

check every new file or batch the moment it lands

```text
usage: odcr watch [-h] [--contract-id CONTRACT_ID] [--for-object FOR_OBJECT]
                  [--contracts CONTRACTS] [--contracts-ref CONTRACTS_REF] [--config CONFIG]
                  [--connection CONNECTION] [--json] [--batch-column BATCH_COLUMN]
                  [--interval INTERVAL] [--once] [--pipeline PIPELINE] [--no-notify]
                  [contract]

positional arguments:
  contract              contract file (or use --contract-id / --for-object)

options:
  -h, --help            show this help message and exit
  --contract-id CONTRACT_ID
                        contract id in the contract repository
  --for-object FOR_OBJECT
                        find the contract describing this table / collection / path
  --contracts CONTRACTS
                        contract repository: a folder or a Git URL (GitHub, Azure DevOps, GitLab,
                        ...); default: odcr.yaml or $ODCR_CONTRACTS
  --contracts-ref CONTRACTS_REF
                        branch or tag of a Git contract repository (default: main)
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --batch-column BATCH_COLUMN
                        column identifying a batch in a table (e.g. load_id)
  --interval INTERVAL   seconds between polls (default 60)
  --once                check what is new, then exit (for schedulers)
  --pipeline PIPELINE   pipeline name (default: watch:<contract id>)
  --no-notify
```

## odcr reconcile

compare source and target for a batch

```text
usage: odcr reconcile [-h] [--config CONFIG] [--json] [--source SOURCE] [--target TARGET]
                      [--batch-id BATCH_ID] [--pipeline PIPELINE] [--contract CONTRACT]
                      [--no-notify]
                      spec

positional arguments:
  spec

options:
  -h, --help           show this help message and exit
  --config, -c CONFIG  config file (default: ./odcr.yaml)
  --json               machine-readable output
  --source SOURCE      override source connection
  --target TARGET      override target connection
  --batch-id BATCH_ID
  --pipeline PIPELINE
  --contract CONTRACT  contract file, to notify its source team
  --no-notify
```

## odcr checkpoint

record that a stage processed a batch

```text
usage: odcr checkpoint [-h] [--config CONFIG] [--connection CONNECTION] [--json]
                       --pipeline PIPELINE --stage STAGE --batch-id BATCH_ID [--rows ROWS]
                       [--object OBJECT] [--where WHERE]
                       [--mode {batch,streaming,cdc,queue,microbatch}] [--status STATUS]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --pipeline PIPELINE
  --stage STAGE
  --batch-id BATCH_ID
  --rows ROWS           row count (otherwise counted from --object)
  --object OBJECT       table / collection / path to count rows from
  --where WHERE
  --mode {batch,streaming,cdc,queue,microbatch}
  --status STATUS
```

## odcr trace

show a batch's journey through every stage

```text
usage: odcr trace [-h] [--config CONFIG] [--connection CONNECTION] [--json] --pipeline PIPELINE
                  --batch-id BATCH_ID [--tolerance TOLERANCE]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --pipeline PIPELINE
  --batch-id BATCH_ID
  --tolerance TOLERANCE
                        allowed row change between stages
```

## odcr history

recent validation runs

```text
usage: odcr history [-h] [--config CONFIG] [--connection CONNECTION] [--json]
                    [--contract-id CONTRACT_ID] [--limit LIMIT]

options:
  -h, --help            show this help message and exit
  --config, -c CONFIG   config file (default: ./odcr.yaml)
  --connection, -C CONNECTION
                        connection name from the config (default: main)
  --json                machine-readable output
  --contract-id CONTRACT_ID
  --limit LIMIT
```
