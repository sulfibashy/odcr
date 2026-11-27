# Apache Kafka

Topics as objects: each run checks the messages since the last run.

| | |
| --- | --- |
| Adapter name | `kafka` (aliases: `confluent`, `msk`, `redpanda`, `aiven-kafka`, `event-streams`) |
| Runs on | on-premise, Confluent Cloud, Amazon MSK, Aiven, Redpanda, IBM Event Streams |
| Install | `pip install odcr-kafka` |
| Python driver | `confluent_kafka` |
| Batch filter example | `load_id = '{batch_id}'` |
| Testing | End-to-end tests run against a live instance in CI on every push. |

## Create a project

```bash
pip install odcr-kafka
odcr init my_contracts --adapter kafka
cd my_contracts
```

The generated project is also in the repository: [`examples/kafka`](https://github.com/sulfibashy/odcr/tree/main/examples/kafka).

## Connection

```yaml
connections:
  main:
    type: kafka
    bootstrap_servers: ${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}
    group_id: ${KAFKA_GROUP_ID:-odcr}
    start: earliest
    meta_path: ${ODCR_META_PATH:-odcr_meta.duckdb}
```

Values like `${NAME}` come from environment variables or a `.env` file next to `odcr.yaml`; `${file:/path}`
reads a secret file. See [Security](../security.md) for TLS and authentication.

## Notes

- physicalName is the topic; message values are JSON objects.
- TLS / SASL: security_protocol, sasl_mechanism, ssl_ca_location, or any librdkafka setting under config:.
- mock: true uses an in-process broker (for tests: messages are not kept between commands).

## Check it

```bash
odcr doctor -C main
odcr run --contract-id orders -C main --batch-id batch-001 --where "load_id = 'batch-001'"
```
