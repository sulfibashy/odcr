# SQLite

Built into Python; ideal for trying odcr and for unit tests.

| | |
| --- | --- |
| Adapter name | `sqlite` (aliases: none) |
| Runs on | local |
| Install | `pip install odcr` |
| Python driver | `sqlite3` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr
odcr init my_contracts --adapter sqlite
cd my_contracts
```

The generated project is also in the repository: [`examples/sqlite`](https://github.com/sulfibashy/odcr/tree/main/examples/sqlite).

## Connection

```yaml
connections:
  main:
    type: sqlite
    path: ${SQLITE_PATH:-odcr.sqlite}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- No schemas: meta tables are prefixed (odcr_meta_validation_runs, ...).

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
