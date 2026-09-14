import csv
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts.prepare_banksim import ConversionError, convert_dataset, write_outputs

HEADER = ["step", "customer", "merchant", "category", "amount", "fraud"]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def test_conversion_is_deterministic_and_excludes_labels(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_csv(source, [["1", "c", "m", "cat", "12.34", "1"], ["2", "z", "m", "cat", "0", "0"]])
    first, manifest = convert_dataset(source, seed="test")
    second, _ = convert_dataset(source, seed="test")
    assert first == second
    assert manifest["canonical_row_count"] == 1
    assert manifest["skipped_row_count"] == 1
    assert "fraud" not in first[0]
    assert first[0]["event_time"].isoformat() == "2026-01-02T00:00:00+00:00"

    output = tmp_path / "out.parquet"
    result = tmp_path / "manifest.json"
    write_outputs(first, manifest, output, result)
    assert pq.read_table(output).column_names == [
        "transaction_id",
        "customer_id",
        "merchant_id",
        "category",
        "amount",
        "source_step",
        "source",
        "event_time",
        "source_metadata",
    ]


def test_conversion_reports_row_reference_for_invalid_input(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_csv(source, [["1", "c", "m", "cat", "-1", "0"]])
    with pytest.raises(ConversionError, match="line 2"):
        convert_dataset(source)
