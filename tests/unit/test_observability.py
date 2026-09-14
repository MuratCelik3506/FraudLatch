import json
import logging

from fraudlatch.observability import JsonLogFormatter, Observability


def test_metrics_use_stable_names_without_identifiers_as_labels() -> None:
    metrics = Observability()
    metrics.received.inc()
    text = metrics.exposition().decode()
    assert "fraudlatch_transactions_received_total 1.0" in text
    assert "transaction_id" not in text


def test_json_formatter_includes_safe_correlation_fields() -> None:
    record = logging.LogRecord("test", logging.INFO, "", 0, "processed", (), None)
    record.fields = {"component": "api", "attempt": 1, "transaction_id": "txn-1"}
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["component"] == "api"
    assert payload["transaction_id"] == "txn-1"
