#!/usr/bin/env python3
"""Convert validated BankSim rows into deterministic canonical Parquet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.validate_dataset import LICENSE, REQUIRED_COLUMNS, SOURCE_URL

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
CANONICAL_COLUMNS = (
    "transaction_id",
    "customer_id",
    "merchant_id",
    "category",
    "amount",
    "source_step",
    "source",
    "event_time",
    "source_metadata",
)


class ConversionError(ValueError):
    """A source row cannot become a canonical transaction."""


def stable_transaction_id(seed: str, source_row: int, values: tuple[str, ...]) -> str:
    """Create an opaque ID stable for the seed and source row identity."""

    identity = "|".join((seed, str(source_row), *values))
    return f"banksim-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"


def convert_dataset(
    path: Path, *, seed: str = "fraudlatch-v1"
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert positive-amount rows and return canonical records plus evaluation metadata."""

    if not path.is_file():
        raise ConversionError(f"dataset is missing: run make data-check first ({path})")
    rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    fraud_count = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or ())]
        if missing:
            raise ConversionError(f"missing required columns: {', '.join(missing)}")
        for line_number, row in enumerate(reader, start=2):
            values = tuple((row.get(column) or "").strip() for column in REQUIRED_COLUMNS)
            step, customer, merchant, category, amount, fraud = values
            if not customer or not merchant or not category or not amount:
                raise ConversionError(f"line {line_number}: required source field is empty")
            try:
                source_step = int(step)
                numeric_amount = Decimal(amount)
            except (ValueError, InvalidOperation) as error:
                raise ConversionError(f"line {line_number}: invalid step or amount") from error
            if source_step < 0 or numeric_amount < 0:
                raise ConversionError(f"line {line_number}: step and amount must not be negative")
            if fraud not in {"0", "1"}:
                raise ConversionError(f"line {line_number}: fraud must be binary 0 or 1")
            fraud_count += fraud == "1"
            if numeric_amount == 0:
                skipped_rows.append({"line": line_number, "reason": "zero_amount"})
                continue
            transaction_id = stable_transaction_id(seed, line_number, values)
            if transaction_id in ids:
                raise ConversionError(f"line {line_number}: transaction ID collision")
            ids.add(transaction_id)
            rows.append(
                {
                    "transaction_id": transaction_id,
                    "customer_id": customer,
                    "merchant_id": merchant,
                    "category": category,
                    "amount": numeric_amount.quantize(Decimal("0.01")),
                    "source_step": source_step,
                    "source": "banksim",
                    "event_time": EPOCH + timedelta(days=source_step),
                    "source_metadata": json.dumps(
                        {"dataset": "banksim", "source_row": line_number}, sort_keys=True
                    ),
                }
            )
    return rows, {
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "seed": seed,
        "input_file": str(path),
        "source_row_count": len(rows) + len(skipped_rows),
        "canonical_row_count": len(rows),
        "skipped_row_count": len(skipped_rows),
        "skipped_rows": skipped_rows,
        "source_fraud_count": fraud_count,
        "canonical_columns": list(CANONICAL_COLUMNS),
    }


def write_outputs(
    rows: list[dict[str, Any]], manifest: dict[str, Any], output: Path, manifest_path: Path
) -> None:
    """Write a stable Parquet table and a JSON manifest."""

    table = pa.table(
        {
            "transaction_id": pa.array([row["transaction_id"] for row in rows], type=pa.string()),
            "customer_id": pa.array([row["customer_id"] for row in rows], type=pa.string()),
            "merchant_id": pa.array([row["merchant_id"] for row in rows], type=pa.string()),
            "category": pa.array([row["category"] for row in rows], type=pa.string()),
            "amount": pa.array([row["amount"] for row in rows], type=pa.decimal128(18, 2)),
            "source_step": pa.array([row["source_step"] for row in rows], type=pa.int32()),
            "source": pa.array([row["source"] for row in rows], type=pa.string()),
            "event_time": pa.array(
                [row["event_time"] for row in rows], type=pa.timestamp("us", tz="UTC")
            ),
            "source_metadata": pa.array([row["source_metadata"] for row in rows], type=pa.string()),
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output, compression="none", use_dictionary=False, write_statistics=False)
    manifest["output_file"] = str(output)
    manifest["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path("data/raw/bs140513_032310.csv"))
    parser.add_argument("--seed", default="fraudlatch-v1")
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/banksim_canonical.parquet")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/processed/banksim_canonical_manifest.json")
    )
    args = parser.parse_args()
    try:
        rows, manifest = convert_dataset(args.path, seed=args.seed)
        write_outputs(rows, manifest, args.output, args.manifest)
    except (ConversionError, OSError, pa.ArrowException) as error:
        parser.error(str(error))
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
