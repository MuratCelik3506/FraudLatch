import csv
from pathlib import Path

import pytest

from scripts.validate_dataset import DatasetValidationError, validate_dataset

HEADER = ["step", "customer", "merchant", "category", "amount", "fraud"]


def write_csv(path: Path, rows: list[list[str]], header: list[str] | None = None) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header or HEADER)
        writer.writerows(rows)


def valid_row() -> list[str]:
    return ["1", "c1", "m1", "cat", "12.34", "0"]


def test_valid_file_returns_hash_counts_and_duplicate_report(tmp_path: Path) -> None:
    path = tmp_path / "bank.csv"
    write_csv(path, [valid_row(), valid_row()])
    manifest = validate_dataset(path)
    assert manifest["row_count"] == 2
    assert manifest["fraud_count"] == 0
    assert manifest["duplicate_rows"] == 1
    assert len(manifest["sha256"]) == 64


@pytest.mark.parametrize(
    ("rows", "header", "message"),
    [
        ([], ["step", "customer"], "missing required columns"),
        ([["1", "", "m", "cat", "1", "0"]], None, "cannot be null"),
        ([["1", "c", "m", "cat", "-1", "0"]], None, "positive number"),
        ([["1", "c", "m", "cat", "1", "yes"]], None, "binary 0 or 1"),
    ],
)
def test_invalid_file_is_rejected(
    tmp_path: Path, rows: list[list[str]], header: list[str] | None, message: str
) -> None:
    path = tmp_path / "bank.csv"
    write_csv(path, rows, header)
    with pytest.raises(DatasetValidationError, match=message):
        validate_dataset(path)


def test_missing_file_has_manual_acquisition_guidance(tmp_path: Path) -> None:
    with pytest.raises(DatasetValidationError, match="download BankSim manually"):
        validate_dataset(tmp_path / "missing.csv")
