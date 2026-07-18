#!/usr/bin/env python3
"""Create all required Kafka topics. Safe to run multiple times."""
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_USERNAME = os.getenv("KAFKA_USERNAME", "")
KAFKA_PASSWORD = os.getenv("KAFKA_PASSWORD", "")
KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")
KAFKA_SSL_CAFILE = os.getenv("KAFKA_SSL_CAFILE", "")
KAFKA_SSL_CERTFILE = os.getenv("KAFKA_SSL_CERTFILE", "")
KAFKA_SSL_KEYFILE = os.getenv("KAFKA_SSL_KEYFILE", "")

TOPICS = [
    {"name": "doc-ingest", "partitions": 12, "retention_ms": 86_400_000},
    {"name": "doc-chunk", "partitions": 24, "retention_ms": 43_200_000},
    {"name": "doc-embed", "partitions": 24, "retention_ms": 43_200_000},
    {"name": "doc-dlq", "partitions": 6, "retention_ms": 604_800_000},
]


def kafka_admin_config() -> dict:
    """Build kafka-python admin config from .env."""
    config = {
        "bootstrap_servers": KAFKA_BROKERS,
        "client_id": "pvh-topic-setup",
        "request_timeout_ms": 10_000,
        "security_protocol": KAFKA_SECURITY_PROTOCOL,
    }

    if KAFKA_USERNAME and KAFKA_PASSWORD:
        config.update(
            sasl_mechanism=KAFKA_SASL_MECHANISM,
            sasl_plain_username=KAFKA_USERNAME,
            sasl_plain_password=KAFKA_PASSWORD,
        )
        if KAFKA_SECURITY_PROTOCOL == "PLAINTEXT":
            config["security_protocol"] = "SASL_SSL"

    if KAFKA_SSL_CAFILE:
        config["ssl_cafile"] = KAFKA_SSL_CAFILE
    if KAFKA_SSL_CERTFILE:
        config["ssl_certfile"] = KAFKA_SSL_CERTFILE
    if KAFKA_SSL_KEYFILE:
        config["ssl_keyfile"] = KAFKA_SSL_KEYFILE

    return config


def create_topics() -> None:
    try:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError
    except ImportError as exc:
        print(f"  ERROR kafka-python import failed: {exc}")
        sys.exit(1)

    admin = None
    for attempt in range(12):
        try:
            admin = KafkaAdminClient(**kafka_admin_config())
            break
        except Exception as exc:
            if attempt == 11:
                print(f"  ERROR Kafka not reachable at {KAFKA_BROKERS} after 60s: {exc}")
                sys.exit(1)
            print(f"  Waiting for Kafka broker... ({attempt + 1}/12): {exc}")
            time.sleep(5)

    if admin is None:
        print("  ERROR Kafka admin client was not created")
        sys.exit(1)

    new_topics = [
        NewTopic(
            name=t["name"],
            num_partitions=t["partitions"],
            replication_factor=1,
            topic_configs={
                "retention.ms": str(t["retention_ms"]),
                "min.insync.replicas": "1",
                "segment.bytes": "134217728",
            },
        )
        for t in TOPICS
    ]

    for topic in new_topics:
        try:
            admin.create_topics([topic], validate_only=False)
            print(f"  OK Created : {topic.name} ({topic.num_partitions} partitions)")
        except TopicAlreadyExistsError:
            print(f"  OK Exists  : {topic.name} - skipping")
        except Exception as exc:
            print(f"  ERROR Failed  : {topic.name} - {exc}")

    admin.close()


if __name__ == "__main__":
    print(f"Creating Kafka topics on {KAFKA_BROKERS}...")
    create_topics()
    print("Done.")