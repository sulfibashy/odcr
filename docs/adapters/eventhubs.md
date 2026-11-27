# Azure Event Hubs

Event hubs as objects, over the Kafka endpoint; Entra ID auth.

| | |
| --- | --- |
| Adapter name | `eventhubs` (aliases: `event-hubs`, `azure-event-hubs`, `eventhub`) |
| Runs on | Azure |
| Install | `pip install odcr-eventhubs` |
| Python driver | `confluent_kafka` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run when credentials are provided (`ODCR_TEST_EVENTHUBS`, see [Development](../contributing/development.md)). Unit tests cover the SQL it generates. |

## Create a project

```bash
pip install odcr-eventhubs
odcr init my_contracts --adapter eventhubs
cd my_contracts
```

The generated project is also in the repository: [`examples/eventhubs`](https://github.com/sulfibashy/odcr/tree/main/examples/eventhubs).

## Connection

```yaml
connections:
  main:
    type: eventhubs
    namespace: ${EVENTHUBS_NAMESPACE}
    consumer_group: ${EVENTHUBS_CONSUMER_GROUP:-odcr}
    start: earliest
    meta_path: ${ODCR_META_PATH:-odcr_meta.duckdb}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- physicalName is the event hub. Create a consumer group for odcr (e.g. odcr) so it does not share offsets with your consumers.
- Authentication: Entra ID (managed identity, workload identity, az login) by default; the identity needs the Azure Event Hubs Data Receiver role. Or connection_string.

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
