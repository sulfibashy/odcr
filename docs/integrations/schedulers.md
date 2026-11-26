# Schedulers, SSIS and dbt

`odcr init` generates three ready-made wrappers in `jobs/`:

| Script | For |
| --- | --- |
| `ingestion_gate.sh` | cron, Control-M, Autosys, Tivoli, Informatica / Ab Initio on Linux and Unix |
| `ingestion_gate.ps1` | Windows Task Scheduler, SQL Server Agent (PowerShell step), SSIS Execute Process Task |
| `ingestion_gate.py` | anything that runs Python |

```bash
jobs/ingestion_gate.sh 2026-11-26-01                      # Linux / macOS / Unix
powershell -File jobs\ingestion_gate.ps1 -BatchId 2026-11-26-01   # Windows
```

**SSIS:** Execute Process Task → `powershell.exe -File C:\odcr\project\jobs\ingestion_gate.ps1 -BatchId ?`, with
*FailTaskIfReturnCodeIsNotSuccessValue* on.

**dbt:** run odcr on sources before `dbt build`, or on models after it:

```bash
odcr run --contract-id orders --batch-id "$LOAD_ID" --where "load_id = '$LOAD_ID'" && dbt build
```
