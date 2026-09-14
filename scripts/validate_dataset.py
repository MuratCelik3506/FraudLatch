#!/usr/bin/env python3
"""Validate the manually acquired BankSim CSV without changing its contents."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SOURCE_URL = "https://www.kaggle.com/datasets/ealaxi/banksim1"
LICENSE = "CC BY-NC-SA 4.0"
REQUIRED_COLUMNS = ("step", "customer", "merchant", "category", "amount", "fraud")


class DatasetValidationError(ValueError):
    """A source file cannot be safely passed to canonical conversion."""


def validate_dataset(path: Path) -> dict[str, Any]:
    """Return a deterministic provenance manifest or raise an actionable error."""

    if not path.is_file():
        raise DatasetValidationError(
            f"dataset is missing: {path}; download BankSim manually from {SOURCE_URL}, "
            f"extract bs140513_032310.csv, and place it at this path"
        )

    digest = hashlib.sha256()
    with path.open("rb") as raw:
        for chunk in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(chunk)

    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as error:
        raise DatasetValidationError(f"cannot read dataset {path}: {error}") from error

    with handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise DatasetValidationError(f"missing required columns: {', '.join(missing)}")

        row_count = 0
        fraud_count = 0
        duplicates: Counter[tuple[str, ...]] = Counter()
        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            values = tuple((row.get(column) or "").strip() for column in REQUIRED_COLUMNS)
            duplicates[values] += 1
            step, customer, merchant, category, amount, fraud = values
            if not customer or not merchant or not category or not amount:
                raise DatasetValidationError(
                    f"line {line_number}: IDs, category, and amount cannot be null"
                )
            try:
                if int(step) < 0:
                    raise ValueError
            except ValueError as error:
                raise DatasetValidationError(
                    f"line {line_number}: step must be a non-negative integer"
                ) from error
            try:
                if float(amount) <= 0:
                    raise ValueError
            except ValueError as error:
                raise DatasetValidationError(
                    f"line {line_number}: amount must be a positive number"
                ) from error
            if fraud not in {"0", "1"}:
                raise DatasetValidationError(f"line {line_number}: fraud must be binary 0 or 1")
            fraud_count += fraud == "1"

    duplicate_rows = sum(count - 1 for count in duplicates.values() if count > 1)
    return {
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "file": str(path),
        "sha256": digest.hexdigest(),
        "row_count": row_count,
        "fraud_count": fraud_count,
        "duplicate_rows": duplicate_rows,
        "required_columns": list(REQUIRED_COLUMNS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=Path("data/raw/bs140513_032310.csv"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/processed/banksim_validation_manifest.json")
    )
    args = parser.parse_args()
    try:
        manifest = validate_dataset(args.path)
    except DatasetValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
