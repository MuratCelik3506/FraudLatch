import asyncio
import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.replay_banksim import ReplayConfig, replay, selected_rows


def create_parquet(path: Path) -> None:
    table = pa.table(
        {
            "transaction_id": ["t1", "t2"],
            "customer_id": ["c1", "c2"],
            "merchant_id": ["m1", "m2"],
            "category": ["cat", "cat"],
            "amount": pa.array([Decimal("1.00"), Decimal("2.00")], type=pa.decimal128(18, 2)),
            "source_step": [1, 2],
            "source": ["banksim", "banksim"],
            "event_time": pa.array(
                [datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "source_metadata": ['{"source_row": 2}', '{"source_row": 3}'],
        }
    )
    pq.write_table(table, path)


def config(raw: Path, **kwargs: object) -> ReplayConfig:
    values = {
        "api_url": "http://test",
        "rate": 1000.0,
        "limit": 0,
        "fraud_only": False,
        "start_step": None,
        "end_step": None,
        "raw_path": raw,
    }
    values.update(kwargs)
    return ReplayConfig(**values)


def test_filters_and_limit_are_deterministic(tmp_path: Path) -> None:
    parquet = tmp_path / "data.parquet"
    raw = tmp_path / "raw.csv"
    create_parquet(parquet)
    with raw.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "customer", "merchant", "category", "amount", "fraud"])
        writer.writerow(["1", "c1", "m1", "cat", "1", "1"])
        writer.writerow(["2", "c2", "m2", "cat", "2", "0"])
    assert [
        row["transaction_id"] for row in selected_rows(parquet, config(raw, fraud_only=True))
    ] == ["t1"]
    assert len(selected_rows(parquet, config(raw, limit=1))) == 1


def test_replay_retries_server_failure_without_changing_id(tmp_path: Path) -> None:
    parquet, raw = tmp_path / "data.parquet", tmp_path / "raw.csv"
    create_parquet(parquet)
    raw.write_text(
        "step,customer,merchant,category,amount,fraud\n1,c1,m1,cat,1,0\n2,c2,m2,cat,2,0\n"
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.content.decode())
        return httpx.Response(500 if len(calls) == 1 else 202)

    async def exercise() -> dict[str, object]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test"
        ) as client:
            return await replay(parquet, config(raw, limit=1), client)

    result = asyncio.run(exercise())
    assert result["sent"] == 1
    assert len(calls) == 2
    assert calls[0] == calls[1]
