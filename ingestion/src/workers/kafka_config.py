"""
Shared Kafka client configuration for aiokafka producers/consumers.

IMPORTANT (bug found by web-verifying the aiokafka API rather than
assuming it): AIOKafkaProducer / AIOKafkaConsumer take `ssl_context` (an
ssl.SSLContext object), NOT a bare `ssl_cafile` string kwarg. An earlier
draft of dlq_producer.py / stream_consumer.py passed ssl_cafile directly
as a kwarg — that would have raised a TypeError the first time either
ran against a real SASL_SSL broker (e.g. Aiven, the exact scenario
KAFKA_SSL_CAFILE etc. exist to support). aiokafka.helpers.create_ssl_context()
is the documented way to build the context from cafile/certfile/keyfile
paths. Centralized here so dlq_producer.py and stream_consumer.py share
one correct implementation instead of two independently-maintained ones.
"""
from aiokafka.helpers import create_ssl_context

from ..config import settings


def kafka_client_kwargs() -> dict:
    """Common kwargs for both AIOKafkaProducer and AIOKafkaConsumer,
    built from ingestion/src/config.py's Kafka settings."""
    kwargs: dict = {
        "bootstrap_servers": settings.KAFKA_BROKERS,
        "security_protocol": settings.KAFKA_SECURITY_PROTOCOL,
    }
    if settings.KAFKA_USERNAME and settings.KAFKA_PASSWORD:
        kwargs.update(
            sasl_mechanism=settings.KAFKA_SASL_MECHANISM,
            sasl_plain_username=settings.KAFKA_USERNAME,
            sasl_plain_password=settings.KAFKA_PASSWORD,
        )
    if settings.KAFKA_SSL_CAFILE or settings.KAFKA_SSL_CERTFILE:
        kwargs["ssl_context"] = create_ssl_context(
            cafile=settings.KAFKA_SSL_CAFILE or None,
            certfile=settings.KAFKA_SSL_CERTFILE or None,
            keyfile=settings.KAFKA_SSL_KEYFILE or None,
        )
    return kwargs
