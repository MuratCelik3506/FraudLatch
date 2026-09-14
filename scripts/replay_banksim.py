#!/usr/bin/env python3
"""Replay canonical BankSim Parquet rows through the ingestion API."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pyarrow.parquet as pq


@dataclass(frozen=True)
class ReplayConfig:
    api_url: str
    rate: float
    limit: int
    fraud_only: bool
    start_step: int | None
    end_step: int | None
    raw_path: Path


def load_fraud_rows(path: Path) -> set[int]:
    """Load source row numbers whose evaluation label is fraud."""

    if not path.is_file():
        raise ValueError(f"--fraud-only requires the raw CSV at {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            line
            for line, row in enumerate(csv.DictReader(handle), start=2)
            if row.get("fraud") == "1"
        }


def selected_rows(path: Path, config: ReplayConfig) -> list[dict[str, Any]]:
    """Read Parquet batches and apply deterministic filters."""

    parquet = pq.ParquetFile(path)
    selected: list[dict[str, Any]] = []
    fraud_rows = load_fraud_rows(config.raw_path) if config.fraud_only else set()
    for batch in parquet.iter_batches(batch_size=1024):
        for row in batch.to_pylist():
            metadata = json.loads(row["source_metadata"])
            step = int(row["source_step"])
            if config.start_step is not None and step < config.start_step:
                continue
            if config.end_step is not None and step > config.end_step:
                continue
            if config.fraud_only and metadata["source_row"] not in fraud_rows:
                continue
            selected.append(row)
            if config.limit and len(selected) >= config.limit:
                return selected
    return selected


async def replay(path: Path, config: ReplayConfig, client: httpx.AsyncClient) -> dict[str, Any]:
    """Send selected rows with bounded retry and pacing."""

    rows = selected_rows(path, config)
    sent = 0
    failures: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            key: row[key]
            for key in (
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
        }
        payload["amount"] = str(payload["amount"])
        payload["event_time"] = payload["event_time"].isoformat()
        last_error = ""
        succeeded = False
        for attempt, delay in enumerate((0, 1, 5), start=1):
            if delay:
                await asyncio.sleep(delay)
            if sent and config.rate:
                await asyncio.sleep(1 / config.rate)
            try:
                response = await client.post("/v1/transactions", json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = str(error) or type(error).__name__
                if attempt < 3:
                    continue
                break
            if response.status_code in {200, 202}:
                sent += 1
                succeeded = True
                break
            if response.status_code >= 500 and attempt < 3:
                last_error = f"HTTP {response.status_code}"
                continue
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            break
        else:
            last_error = "retry loop exhausted"
        if not succeeded and last_error:
            failures.append({"transaction_id": row["transaction_id"], "error": last_error})
    return {"selected": len(rows), "sent": sent, "failed": len(failures), "failures": failures}


async def async_main(args: argparse.Namespace) -> int:
    config = ReplayConfig(
        api_url=args.api_url.rstrip("/"),
        rate=args.rate,
        limit=args.limit,
        fraud_only=args.fraud_only,
        start_step=args.start_step,
        end_step=args.end_step,
        raw_path=args.raw,
    )
    async with httpx.AsyncClient(base_url=config.api_url, timeout=10) as client:
        result = await replay(args.input, config, client)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/processed/banksim_canonical.parquet")
    )
    parser.add_argument("--raw", type=Path, default=Path("data/raw/bs140513_032310.csv"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--fraud-only", action="store_true")
    parser.add_argument("--start-step", type=int)
    parser.add_argument("--end-step", type=int)
    args = parser.parse_args()
    if args.rate <= 0 or args.limit < 0:
        parser.error("--rate must be positive and --limit must be non-negative")
    try:
        return asyncio.run(async_main(args))
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
