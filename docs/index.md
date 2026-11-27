# odcr — Open Data Contract Runtime

**Check every dataset against its data contract the moment it lands, on any platform.**

odcr reads [ODCS](https://github.com/bitol-io/open-data-contract-standard) data contracts from a central Git
repository and enforces them wherever data arrives: a database table, a lakehouse table, or files in ADLS,
S3, GCS or a local landing folder. It does not matter how the data got there — batch, streaming, CDC, events
or file drops. Each load unit has a `batch_id`, and odcr:

1. **checks** it against the contract: schema (columns, types, drift) and quality rules;
2. **decides** pass, warn, or fail and quarantine (the exit code stops your pipeline);
3. **notifies** the source team (from the contract) and the platform team: Slack, Teams, email, Google Chat,
   Discord, PagerDuty, Opsgenie or any webhook;
4. **logs** everything in meta tables created **on the platform itself**, so history lives next to the data;
5. **reconciles** source and target, even across platforms;
6. **traces** each batch from source to consumption and flags where rows were lost.

```bash
pip install odcr-postgres          # or snowflake, databricks, sqlserver, mongodb, files, ... (18 adapters)
odcr init my_contracts --adapter postgres
cd my_contracts && odcr doctor && odcr run --contract-id orders
```

<div class="grid cards" markdown>

- **[Install](getting-started/installation.md)** — Windows, macOS, Linux and Unix servers, offline and behind proxies
- **[Quickstart](getting-started/quickstart.md)** — a working project in five minutes
- **[Adapters](adapters/index.md)** — 18 platforms: on-premise, Azure, AWS, GCP, Snowflake, documents and files
- **[When data lands](concepts/when-data-lands.md)** — batch, streaming, CDC and file arrival
- **[Integrations](integrations/index.md)** — Airflow, Informatica, Ab Initio, ADF, Databricks, SSIS
- **[Security](security.md)** — TLS, certificates, secrets and least privilege

</div>
