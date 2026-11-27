# Security: TLS, certificates and secrets

odcr runs inside your network with your credentials. It stores no credentials, sends data nowhere except the
notification channels you configure, and writes only to the meta tables.

## Encryption in transit

Every adapter uses the platform's TLS, with server certificates verified by default:

| Platform | Default | Options |
| --- | --- | --- |
| PostgreSQL / Redshift | `sslmode: prefer` (Redshift: TLS) | `sslmode: verify-full`, `sslrootcert: /path/ca.pem` (in `dsn`) |
| MySQL / MariaDB | server default | `ssl_ca: /path/ca.pem` enforces verified TLS |
| SQL Server / Azure SQL / Synapse / Fabric | `encrypt: yes`, certificate verified | `trust_server_certificate: true` only for local development |
| Oracle | as configured in the DSN | `dsn` with `(PROTOCOL=TCPS)`, `wallet_location`, `wallet_password` |
| Db2 | plain or TLS | `ssl: true` (`SECURITY=SSL`), or `dsn` with `SSLServerCertificate=` |
| MongoDB | per URI | `mongodb+srv://` (TLS on), `tls`, `tlsCAFile` in the URI |
| Trino | HTTPS when authenticated | `http_scheme: https` |
| Snowflake, Databricks, BigQuery, Athena, Cosmos DB | HTTPS only | system CA store |
| Files (ADLS / S3 / GCS) | HTTPS | `ca_bundle: /path/ca.pem`, `transport: curl` for TLS-inspecting proxies |
| Notifications (webhooks, SMTP) | HTTPS / STARTTLS, verified | `ca_bundle`, `proxy`, `smtp.ssl` / `smtp.starttls` |

**Corporate CA / TLS-inspecting proxy:** install the CA in the operating system trust store (preferred), or set
`ca_bundle` for notifications and files, `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` for cloud SDKs.

## Encryption at rest

Meta tables are ordinary tables on your platform and inherit its encryption at rest (TDE, SSE, customer-managed
keys). They contain counts, statuses, rule names and the SQL that ran — never row data and never credentials.

## Secrets

Never put secrets in `odcr.yaml` or contracts. Use:

- environment variables: `${SNOWFLAKE_PASSWORD}` (from your scheduler, Key Vault / Secrets Manager integration,
  or a `.env` file that is git-ignored);
- the **OS keychain** (macOS Keychain, Windows Credential Manager, Linux Secret Service):
  `odcr secret set SNOWFLAKE_PASSWORD`, then `password: ${keyring:SNOWFLAKE_PASSWORD}`;
- secret files: `${file:/run/secrets/snowflake_password}` (Docker / Kubernetes secrets, mounted Key Vault);
- passwordless identity where the platform supports it: Entra ID managed identity (Azure SQL, Synapse, Fabric,
  Cosmos DB, ADLS), AWS IAM roles (S3, Athena, Redshift IAM), GCP service accounts / Workload Identity
  (BigQuery, GCS), Snowflake key-pair, Databricks OAuth.

Email needs no password with `smtp-relay`, `microsoft365` (Entra ID) or `aws-ses` (IAM role); see
[Notifications](concepts/notifications.md#email-without-passwords). Contract repositories are read with SSH keys,
the machine's Git credentials, or the pipeline's own token (`$(System.AccessToken)`, `GITHUB_TOKEN`); tokens are
passed in memory and redacted from errors.

Webhook URLs and integration keys are masked in logs and in the `notifications` table.

## Least privilege

| Role | Needs |
| --- | --- |
| Checking data | `SELECT` on the checked tables (read-only) |
| Meta tables | `CREATE` once (or run `odcr meta-init` as an admin), then `INSERT` / `SELECT` on the meta schema |
| Read-only sources | set `meta.connection` to store results on another platform |

## Supply chain

Releases are built in GitHub Actions and published to PyPI with trusted publishing (no long-lived tokens).
Report vulnerabilities privately: see [SECURITY.md](https://github.com/sulfibashy/odcr/blob/main/SECURITY.md).
