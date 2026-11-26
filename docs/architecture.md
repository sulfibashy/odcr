# Architecture

```
            ODCS contract (YAML in Git)          odcr.yaml (connections, meta schema, notifications)
                         │                                   │
                         ▼                                   ▼
   CLI (odcr) / Python API ──► contract.py (load + validate ODCS v3)
                         │
                         ▼
                  runner.py  ── schema checks (live catalog) + checks.py (portable SQL)
                         │
          ┌──────────────┼──────────────────────┬──────────────────────┐
          ▼              ▼                      ▼                      ▼
   adapters/*      meta.py (meta tables    notify.py (Slack,      observe.py (stage checkpoints,
   (Postgres,      inside each platform)   Teams, webhook,        trace per batch)
   MySQL, SQL                              email)                 reconcile.py (source vs target)
   Server, ...)
```

## Modules

| Module | Responsibility |
| --- | --- |
| `contract.py` | Parse and validate ODCS v3 YAML into typed objects; resolve support channels (with `${ENV}` URLs). |
| `checks.py` | Turn properties and quality rules into portable SQL checks; evaluate ODCS comparators. |
| `runner.py` | Run schema and data checks for a table or batch; decide pass / warn / fail; log, quarantine, notify. |
| `reconcile.py` | Compare aggregates and keys between a source and a target, on the same or different platforms. |
| `observe.py` | Record stage checkpoints per batch and build an end-to-end trace that flags row loss or gain. |
| `meta.py` | Meta table definitions and dialect-aware DDL. |
| `notify.py` | Deliver alerts using only the standard library; every attempt is logged. |
| `adapters/` | One small class per platform: connection, quoting, catalog lookup, DDL differences. |
| `cli.py` | `odcr init / lint / meta-init / run / reconcile / checkpoint / trace / history`. |

## Design principles

- **ODCS is the contract format.** No proprietary spec.
- **The platform stores its own history.** Meta tables live next to the data, in the platform's dialect.
- **A load unit is a batch_id.** Batch files, CDC transactions, Kafka offset ranges and streaming windows are all treated the same way.
- **Never crash the pipeline by accident.** A broken check is recorded as `error`; a failed notification is recorded as `failed`. Only the final status decides the exit code.
- **Small core, plug-in adapters.** Adding a platform does not touch the core.
