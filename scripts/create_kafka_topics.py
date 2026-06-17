#!/usr/bin/env python3
"""Create all required Kafka topics. Safe to run multiple times (idempotent)."""
import os
import sys
import time

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")

TOPICS = [
    {"name": "doc-ingest", "partitions": 12, "retention_ms": 86_400_000},   # 24h
    {"name": "doc-chunk",  "partitions": 24, "retention_ms": 43_200_000},   # 12h
    {"name": "doc-embed",  "partitions": 24, "retention_ms": 43_200_000},   # 12h
    {"name": "doc-dlq",    "partitions":  6, "retention_ms": 604_800_000},  # 7d
]


def create_topics() -> None:
    try:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError, NoBrokersAvailable
    except ImportError:
        print("  kafka-python not installed — skipping topic creation")
        return

    # Wait for broker to be available
    for attempt in range(12):
        try:
            admin = KafkaAdminClient(
                bootstrap_servers=KAFKA_BROKERS,
                client_id="pvh-topic-setup",
                request_timeout_ms=10_000,
            )
            break
        except NoBrokersAvailable:
            if attempt == 11:
                print(f"  ✗ Kafka not reachable at {KAFKA_BROKERS} after 60s")
                sys.exit(1)
            print(f"  Waiting for Kafka broker... ({attempt + 1}/12)")
            time.sleep(5)

    new_topics = [
        NewTopic(
            name=t["name"],
            num_partitions=t["partitions"],
            replication_factor=1,
            topic_configs={
                "retention.ms":         str(t["retention_ms"]),
                "min.insync.replicas":  "1",
                "segment.bytes":        "134217728",  # 128 MB
            },
        )
        for t in TOPICS
    ]

    for topic in new_topics:
        try:
            admin.create_topics([topic], validate_only=False)
            print(f"  ✓ Created : {topic.name} ({topic.num_partitions} partitions)")
        except TopicAlreadyExistsError:
            print(f"  ✓ Exists  : {topic.name} — skipping")
        except Exception as e:
            print(f"  ✗ Failed  : {topic.name} — {e}")

    admin.close()


if __name__ == "__main__":
    print(f"Creating Kafka topics on {KAFKA_BROKERS}...")
    create_topics()
    print("Done.")
