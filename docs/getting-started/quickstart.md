# Quickstart

## 1. Create a project

```bash
pip install odcr-duckdb
odcr init my_contracts
```

`odcr init` asks a few questions, like `dbt init`:

```text
Creating an odcr project. Press Enter to accept the [default].

Project name [my_contracts]:
Adapters:
   1. duckdb      DuckDB
   2. files       Files: ADLS, S3, GCS, local
   ...
Which platform will odcr check [duckdb]: 4
Schema for the meta tables [odcr_meta]:
Platform team alerts (slack, teams, email, none) [email]: teams
```

The project is created in a new folder named after the project. Non-interactive (CI, scripts): `odcr init my_contracts --adapter snowflake --alerts teams --no-input`.

## 2. Connect

```bash
cd my_contracts
cp .env.example .env          # Windows: copy .env.example .env — then fill in the connection
odcr doctor                   # driver, connection, TLS, permissions, meta tables, contracts
```

## 3. Try it on sample data

```bash
odcr meta-init
odcr seed                     # sample orders: batch-001 is clean, batch-002 breaks the contract
odcr run --contract-id orders --batch-id batch-001 --where "load_id = 'batch-001'"
odcr run --contract-id orders --batch-id batch-002 --where "load_id = 'batch-002'"
```

```text
Contract orders v1.0.0 batch=batch-002: FAIL
  orders: FAIL (4 rows, 4 failed, 0 warnings)
    - [failed] orders.order_id.unique: expected = 0, got 1 (unique: no duplicate values)
    - [failed] orders.customer_id.required: expected = 0, got 1 (required: no NULL values)
    - [failed] orders.status.invalidValues: expected = 0, got 1
    - [failed] orders.no_negative_amounts: expected = 0, got 1 (Amounts must never be negative)
```

## 4. Check data as it lands

```bash
odcr watch --contract-id orders --batch-column load_id            # tables: every new load_id
odcr watch --contract-id orders --once                            # files: every new file (files adapter)
odcr history --contract-id orders
```

Next: put your own contracts in `contracts/` (or point `odcr.yaml` at your shared contract repository),
and call `jobs/ingestion_gate.*` from your pipelines.

## Start over

```bash
cd ..                        # step out of the project folder
odcr destroy my_contracts    # shows what will be deleted, then asks you to type the project name
odcr init                    # create it again
```

`odcr destroy` deletes only the project folder; tables and meta tables in your databases are not touched.
