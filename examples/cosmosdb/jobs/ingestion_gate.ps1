# Ingestion gate for Windows (Task Scheduler, SQL Server Agent, SSIS Execute Process, Informatica on Windows).
param([string]$BatchId = "batch-001")
Set-Location (Join-Path $PSScriptRoot "..")
odcr run --contract-id orders --connection main --batch-id $BatchId `
  --where "c.load_id = '$BatchId'" --pipeline orders --stage ingestion
exit $LASTEXITCODE
