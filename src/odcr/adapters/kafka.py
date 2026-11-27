"""Kafka and Azure Event Hubs adapter: check the messages on a topic, the moment they arrive.

A contract's physicalName is the topic. Each run reads the messages that arrived since the last run of
the consumer group (a micro-batch), up to the end of every partition as it was when the run started,
loads them into an in-process DuckDB table and runs every check there. Offsets are committed afterwards,
so the next run checks only new messages. Nothing is written to the topic and producers are not affected.

Message values are JSON objects; every row also gets the Kafka metadata columns _kafka_topic,
_kafka_partition, _kafka_offset, _kafka_timestamp and _kafka_key. A value that is not a JSON object is
kept in _kafka_value, so `required` checks on the contract's columns fail for it.

Works with Apache Kafka, Confluent Platform / Cloud, Amazon MSK, Aiven, Redpanda, IBM Event Streams and
Azure Event Hubs (its Kafka endpoint). Security: TLS and SASL options, or any librdkafka setting in
`config:`. Event Hubs uses Entra ID (managed identity, workload identity, az login) unless a connection
string is given, so no password needs to be stored.

Meta tables are stored in a DuckDB file (`meta_path`), or on another connection with `meta: {connection: ...}`.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from .duckdb import DuckDBAdapter

META_COLUMNS = ("_kafka_topic", "_kafka_partition", "_kafka_offset", "_kafka_timestamp", "_kafka_key",
                "_kafka_value")

_OPTION_KEYS = {
    "security_protocol": "security.protocol", "sasl_mechanism": "sasl.mechanism",
    "sasl_username": "sasl.username", "sasl_password": "sasl.password",
    "ssl_ca_location": "ssl.ca.location", "ssl_certificate_location": "ssl.certificate.location",
    "ssl_key_location": "ssl.key.location", "ssl_key_password": "ssl.key.password",
    "sasl_kerberos_service_name": "sasl.kerberos.service.name", "client_id": "client.id",
}


class KafkaAdapter(DuckDBAdapter):
    dialect = "kafka"
    driver = "confluent_kafka"

    def __init__(self, **options: Any):
        super().__init__(**options)
        self._topics: dict[str, str] = {}  # topic -> DuckDB table holding this run's messages

    # ------------------------------------------------------------------ connection
    def _kafka(self) -> Any:
        if self.options.get("mock"):
            return MemoryKafka
        try:
            import confluent_kafka
        except ImportError as exc:  # pragma: no cover
            raise ImportError(f"{self.title} support needs: pip install odcr-{self.dialect}") from exc
        return confluent_kafka

    title = "Kafka"

    def _connect(self) -> Any:
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise ImportError(f"{self.title} support needs: pip install odcr-{self.dialect}") from exc
        self._kafka()
        conn = duckdb.connect(str(self.options.get("meta_path") or ":memory:"))
        conn.execute("ATTACH IF NOT EXISTS ':memory:' AS odcr_stream")  # messages live in memory only
        return conn

    def client_config(self) -> dict[str, Any]:
        """librdkafka settings shared by the consumer and the producer."""
        o = self.options
        conf: dict[str, Any] = {"bootstrap.servers": o.get("bootstrap_servers", "localhost:9092")}
        conf.update({key: o[opt] for opt, key in _OPTION_KEYS.items() if o.get(opt) not in (None, "")})
        conf.update(dict(o.get("config") or {}))
        return conf

    def consumer_config(self) -> dict[str, Any]:
        return {**self.client_config(), "group.id": self.options.get("group_id", "odcr"),
                "enable.auto.commit": False, "enable.partition.eof": False}

    def ping(self) -> bool:
        self.connect()
        ck = self._kafka()
        consumer = ck.Consumer(self.consumer_config())
        try:
            consumer.list_topics(timeout=float(self.options.get("timeout", 10)))
        finally:
            consumer.close()
        return True

    def close(self) -> None:
        self._topics.clear()
        super().close()

    # ------------------------------------------------------------------ reading a topic
    def _table(self, topic: str) -> str:
        return "odcr_stream." + self.quote("kafka__" + re.sub(r"\W", "_", topic))

    def consume(self, topic: str) -> list[dict[str, Any]]:
        """The messages that arrived since the group's last commit, as rows."""
        o = self.options
        ck = self._kafka()
        timeout = float(o.get("timeout", 30))
        limit = int(o.get("max_messages", 1_000_000))
        start = str(o.get("start", "earliest")).lower()
        consumer = ck.Consumer(self.consumer_config())
        try:
            meta = consumer.list_topics(topic, timeout=timeout).topics.get(topic)
            if meta is None or getattr(meta, "error", None) is not None or not meta.partitions:
                raise ValueError(f"Kafka topic '{topic}' does not exist or is not readable")
            parts = sorted(meta.partitions)
            committed = consumer.committed([ck.TopicPartition(topic, p) for p in parts], timeout=timeout)
            end: dict[int, int] = {}
            assign = []
            for tp in committed:
                low, high = consumer.get_watermark_offsets(ck.TopicPartition(topic, tp.partition), timeout=timeout)
                first = tp.offset if tp.offset is not None and tp.offset >= 0 else (high if start == "latest" else low)
                if first < high:
                    assign.append(ck.TopicPartition(topic, tp.partition, first))
                    end[tp.partition] = high
            rows: list[dict[str, Any]] = []
            nxt: dict[int, int] = {}
            if assign:
                consumer.assign(assign)
                deadline = time.monotonic() + timeout
                while end and len(rows) < limit and time.monotonic() < deadline:
                    for msg in consumer.consume(num_messages=min(1000, limit - len(rows)), timeout=1.0):
                        if msg.error():
                            if getattr(msg.error(), "code", lambda: None)() == getattr(
                                    getattr(ck, "KafkaError", None), "_PARTITION_EOF", object()):
                                continue
                            raise RuntimeError(f"Kafka error on {topic}: {msg.error()}")
                        p, off = msg.partition(), msg.offset()
                        if p not in end or off >= end[p]:
                            continue
                        rows.append(self.row(msg))
                        nxt[p] = off + 1
                        if off + 1 >= end[p]:
                            end.pop(p)
            if nxt and o.get("commit", True):
                consumer.commit(offsets=[ck.TopicPartition(topic, p, n) for p, n in nxt.items()], asynchronous=False)
            return rows
        finally:
            consumer.close()

    @staticmethod
    def row(msg: Any) -> dict[str, Any]:
        raw = msg.value()
        text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
        try:
            value = json.loads(text) if text is not None else None
        except ValueError:
            value = None
        row: dict[str, Any] = dict(value) if isinstance(value, dict) else {"_kafka_value": text}
        key = msg.key()
        ts_type, ts = msg.timestamp() if msg.timestamp() else (0, None)
        row.update({
            "_kafka_topic": msg.topic(), "_kafka_partition": msg.partition(), "_kafka_offset": msg.offset(),
            "_kafka_timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts / 1000)) if ts_type and ts else None,
            "_kafka_key": key.decode("utf-8", "replace") if isinstance(key, (bytes, bytearray)) else key,
        })
        return row

    def load(self, topic: str) -> str:
        """Read the topic once per run into a DuckDB table; every check of the run uses the same messages."""
        if topic in self._topics:
            return self._topics[topic]
        self.connect()
        table = self._table(topic)
        rows = self.consume(topic)
        if rows:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "messages.json"
                path.write_text("\n".join(json.dumps(r, default=str) for r in rows), encoding="utf-8")
                self.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_json_auto("
                             f"{self.literal(str(path))}, format = 'newline_delimited', sample_size = -1)")
        else:
            self.execute(f"CREATE OR REPLACE TABLE {table} (_kafka_topic VARCHAR, "
                         "_kafka_partition BIGINT, _kafka_offset BIGINT, _kafka_timestamp TIMESTAMP, "
                         "_kafka_key VARCHAR, _kafka_value VARCHAR)")
        self._topics[topic] = table
        return table

    # ------------------------------------------------------------------ odcr hooks
    def relation(self, name: str, where: str | None = None) -> str:
        if self.is_raw(name):
            return super().relation(name, where)
        table = self.load(name)
        return f"(SELECT * FROM {table} WHERE {where}) src" if where else f"{table} src"

    def columns(self, name: str) -> dict[str, str]:
        if self.is_raw(name):
            return self.raw_columns(name)
        try:
            return self.raw_columns(self.load(name))
        except ValueError:
            return {}  # the topic does not exist

    def system_columns(self) -> tuple[str, ...]:
        return META_COLUMNS

    def create_sample(self, name: str, columns: list[tuple[str, str]], rows: list) -> None:  # type: ignore[override]
        """Produce the rows to the topic as JSON messages (used by `odcr seed` and tests)."""
        ck = self._kafka()
        producer = ck.Producer(self.client_config())
        keys = [c for c, _ in columns]
        for r in rows:
            values = [float(v) if isinstance(v, Decimal) else v for v in r]  # JSON numbers, not strings
            producer.produce(name, json.dumps(dict(zip(keys, values)), default=str).encode("utf-8"))
        producer.flush(float(self.options.get("timeout", 30)))
        self._topics.pop(name, None)

    def drop_table(self, name: str) -> None:
        table = self._topics.pop(name, None)
        if table and self.conn is not None:
            self.execute(f"DROP TABLE IF EXISTS {table}")
        if self.options.get("mock"):
            MemoryKafka.topics.pop(name, None)


class EventHubsAdapter(KafkaAdapter):
    """Azure Event Hubs through its Kafka endpoint. The event hub is the topic; the consumer group is the group."""

    dialect = "eventhubs"
    title = "Event Hubs"

    def client_config(self) -> dict[str, Any]:
        o = self.options
        namespace = str(o.get("namespace", "")).replace("https://", "").rstrip("/")
        host = namespace if "." in namespace else f"{namespace}.servicebus.windows.net"
        conf: dict[str, Any] = {"bootstrap.servers": o.get("bootstrap_servers") or f"{host}:9093",
                                "security.protocol": "SASL_SSL"}
        if o.get("connection_string"):
            conf.update({"sasl.mechanism": "PLAIN", "sasl.username": "$ConnectionString",
                         "sasl.password": o["connection_string"]})
        elif not o.get("mock"):
            conf.update({"sasl.mechanism": "OAUTHBEARER", "oauth_cb": self._entra_token(host)})
        if o.get("ssl_ca_location"):
            conf["ssl.ca.location"] = o["ssl_ca_location"]
        conf.update(dict(o.get("config") or {}))
        return conf

    def consumer_config(self) -> dict[str, Any]:
        return {**super().consumer_config(), "group.id": self.options.get("consumer_group", "$Default")
                if "group_id" not in self.options else self.options["group_id"]}

    def _entra_token(self, host: str) -> Any:
        """Entra ID tokens for the Kafka endpoint: managed identity, workload identity, az login, ..."""
        try:
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Event Hubs with Entra ID needs: pip install odcr-eventhubs") from exc
        client_id = self.options.get("managed_identity_client_id")
        credential = ManagedIdentityCredential(client_id=client_id) if client_id else DefaultAzureCredential()
        scope = f"https://{host}/.default"

        def oauth_cb(_config: str) -> tuple[str, float]:
            token = credential.get_token(scope)
            return token.token, float(token.expires_on)

        return oauth_cb


# ---------------------------------------------------------------------- in-memory broker
class _Msg:
    def __init__(self, topic: str, partition: int, offset: int, value: bytes, key: Any, ts: int):
        self._t, self._p, self._o, self._v, self._k, self._ts = topic, partition, offset, value, key, ts

    def error(self) -> None:
        return None

    def topic(self) -> str:
        return self._t

    def partition(self) -> int:
        return self._p

    def offset(self) -> int:
        return self._o

    def value(self) -> bytes:
        return self._v

    def key(self) -> Any:
        return self._k

    def timestamp(self) -> tuple[int, int]:
        return 1, self._ts


class _TP:
    def __init__(self, topic: str, partition: int, offset: int = -1001):
        self.topic, self.partition, self.offset = topic, partition, offset


class _TopicMeta:
    def __init__(self, partitions: int):
        self.partitions = {p: None for p in range(partitions)}
        self.error = None


class _Metadata:
    def __init__(self, topics: dict[str, _TopicMeta]):
        self.topics = topics


class _MemoryConsumer:
    def __init__(self, conf: dict[str, Any]):
        self.group = conf.get("group.id", "odcr")
        self._assigned: list[_TP] = []

    def list_topics(self, topic: str | None = None, timeout: float = 0) -> _Metadata:
        names = [topic] if topic else list(MemoryKafka.topics)
        return _Metadata({n: _TopicMeta(len(MemoryKafka.topics[n])) for n in names if n in MemoryKafka.topics})

    def committed(self, tps: list[_TP], timeout: float = 0) -> list[_TP]:
        return [_TP(tp.topic, tp.partition, MemoryKafka.offsets.get((self.group, tp.topic, tp.partition), -1001))
                for tp in tps]

    def get_watermark_offsets(self, tp: _TP, timeout: float = 0) -> tuple[int, int]:
        return 0, len(MemoryKafka.topics[tp.topic][tp.partition])

    def assign(self, tps: list[_TP]) -> None:
        self._assigned = [_TP(t.topic, t.partition, t.offset) for t in tps]

    def consume(self, num_messages: int = 1, timeout: float = 0) -> list[_Msg]:
        out: list[_Msg] = []
        for tp in self._assigned:
            log = MemoryKafka.topics[tp.topic][tp.partition]
            while tp.offset < len(log) and len(out) < num_messages:
                value, key, ts = log[tp.offset]
                out.append(_Msg(tp.topic, tp.partition, tp.offset, value, key, ts))
                tp.offset += 1
        return out

    def commit(self, offsets: list[_TP], asynchronous: bool = False) -> None:
        for tp in offsets:
            MemoryKafka.offsets[(self.group, tp.topic, tp.partition)] = tp.offset

    def close(self) -> None:
        self._assigned = []


class _MemoryProducer:
    def __init__(self, conf: dict[str, Any]):
        self.partitions = int(conf.get("num.partitions", 2))
        self._n = 0

    def produce(self, topic: str, value: bytes, key: Any = None) -> None:
        log = MemoryKafka.topics.setdefault(topic, [[] for _ in range(self.partitions)])
        log[self._n % len(log)].append((value, key, int(time.time() * 1000)))
        self._n += 1

    def flush(self, timeout: float = 0) -> int:
        return 0


class MemoryKafka:
    """A tiny in-process broker with the confluent_kafka API (`mock: true`): try odcr and run tests offline."""

    topics: dict[str, list[list[tuple[bytes, Any, int]]]] = {}
    offsets: dict[tuple[str, str, int], int] = {}
    Consumer = _MemoryConsumer
    Producer = _MemoryProducer
    TopicPartition = _TP
