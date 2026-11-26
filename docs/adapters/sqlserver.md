# SQL Server / Azure SQL

Microsoft SQL Server and Azure SQL. Clients: pyodbc (ODBC Driver 18, Entra ID) or pytds.

| | |
| --- | --- |
| Adapter name | `sqlserver` (aliases: `mssql`, `azuresql`, `azure-sql`, `sql-managed-instance`) |
| Runs on | on-premise, Azure SQL Database, Azure SQL Managed Instance, AWS RDS |
| Install | `pip install "odcr[sqlserver]"` |
| Python driver | `pyodbc` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install "odcr[sqlserver]"
odcr init my_contracts --adapter sqlserver
cd my_contracts
```

The generated project is also in the repository: [`examples/sqlserver`](https://github.com/sulfibashy/odcr/tree/main/examples/sqlserver).

## Connection

```yaml
connections:
  main:
    type: sqlserver
    host: ${MSSQL_HOST:-localhost}
    port: ${MSSQL_PORT:-1433}
    database: ${MSSQL_DATABASE:-master}
    user: ${MSSQL_USER:-sa}
    password: ${MSSQL_PASSWORD:-}
    client: pyodbc
    encrypt: 'yes'
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- Entra ID: set authentication: ActiveDirectoryMsi (or ActiveDirectoryInteractive) and leave user/password empty.
- No ODBC driver available? Set client: pytds.
- TLS is on and the server certificate is verified (encrypt: yes). For a private CA, install it in the OS trust store; trust_server_certificate: true is for local development only.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
