"""Low-cardinality metrics and JSON logging helpers."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class Observability:
    """Application metrics with stable names and no transaction identifiers as labels."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.received = Counter(
            "fraudlatch_transactions_received_total",
            "Transactions received",
            registry=self.registry,
        )
        self.processed = Counter(
            "fraudlatch_transactions_processed_total",
            "Transactions processed",
            registry=self.registry,
        )
        self.failures = Counter(
            "fraudlatch_processing_failures_total",
            "Processing failures",
            ["component"],
            registry=self.registry,
        )
        self.retries = Counter(
            "fraudlatch_retries_total", "Retries scheduled", registry=self.registry
        )
        self.dlq = Counter(
            "fraudlatch_dlq_messages_total", "Messages sent to DLQ", registry=self.registry
        )
        self.processing_seconds = Histogram(
            "fraudlatch_processing_duration_seconds", "Processing duration", registry=self.registry
        )
        self.outbox_pending = Gauge(
            "fraudlatch_outbox_pending_total", "Pending outbox events", registry=self.registry
        )

    def exposition(self) -> bytes:
        """Return Prometheus text exposition bytes."""

        return generate_latest(self.registry)


class JsonLogFormatter(logging.Formatter):
    """Render safe structured fields as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", {})
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if isinstance(fields, Mapping):
            payload.update({str(key): value for key, value in fields.items()})
        return json.dumps(payload, sort_keys=True, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Configure one stdout JSON handler for local services."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def emit_log(logger: logging.Logger, message: str, **fields: Any) -> None:
    """Emit correlation fields without making logging failures business-critical."""

    try:
        logger.info(message, extra={"fields": fields})
    except Exception:
        pass
