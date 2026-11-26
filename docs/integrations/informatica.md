# Informatica (PowerCenter, IDMC / IICS)

Install odcr on the Informatica server (or Secure Agent host) — Windows, Linux or Unix — and call it after the
session or mapping task that lands the data.

**PowerCenter: post-session success command** (session properties → Components):

```bash
/opt/odcr/venv/bin/odcr run --config /opt/odcr/project/odcr.yaml --contract-id orders \
  --batch-id $$LOAD_ID --where "load_id = '$$LOAD_ID'" --pipeline orders --stage ingestion
```

Set *Fail task if any command fails*, so a broken contract fails the workflow. On Windows use
`C:\odcr\venv\Scripts\odcr.exe` or `jobs\ingestion_gate.ps1`.

**IDMC / IICS: Command Task** in a taskflow, after the mapping task:

```text
Script file: /opt/odcr/project/jobs/ingestion_gate.sh
Arguments:   $$LOAD_ID
```

The exit code decides the next path in the taskflow (success / fault).

**Reconciliation** of the source system against the target is the same pattern with `odcr reconcile`.
