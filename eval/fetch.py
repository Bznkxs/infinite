"""Getting benchmark data, with no credentials and no dataset library.

Hugging Face serves public datasets over two plain HTTP endpoints — a rows API
that returns JSON, and the raw files themselves. Everything here uses one of
those, so the harness has no dependency a fresh checkout does not already have.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CACHE = Path(__file__).resolve().parent / "cache"
ROWS = "https://datasets-server.huggingface.co/rows"
USER_AGENT = "InfiniteAgent-eval/0.1"


def _get(url: str, *, tries: int = 4, timeout: float = 120.0) -> bytes:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # transient 5xx and read timeouts are routine
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"could not fetch {url}: {last}")


def cached(name: str, url: str) -> Path:
    """Download once into eval/cache and return the path."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists() or path.stat().st_size == 0:
        path.write_bytes(_get(url))
    return path


def prefix_records(url: str, *, max_bytes: int, count: int = 1) -> list[dict[str, Any]]:
    """The first records of a giant JSON array, without downloading the array.

    BABILong's longest configurations are published as one JSON file per split:
    `qa2/10M.json` is 4GB, and neither the rows API nor the parquet conversion
    will serve from it. The file is an array of objects and the CDN honours a
    range request, so the first record can be read from a prefix — 60MB for a
    37MB context.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Range": f"bytes=0-{max_bytes - 1}"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        text = response.read().decode("utf-8", errors="replace")
    text = text.lstrip()
    if text.startswith("["):
        text = text[1:]
    decoder = json.JSONDecoder()
    records, index = [], 0
    while len(records) < count:
        while index < len(text) and text[index] in ", \n\r\t":
            index += 1
        try:
            record, index = decoder.raw_decode(text, index)
        except json.JSONDecodeError as exc:
            if not records:
                raise RuntimeError(
                    f"no complete record in the first {max_bytes} bytes of {url}"
                ) from exc
            break
        records.append(record)
    return records


def prefix_lines(url: str, *, max_bytes: int, count: int) -> list[dict[str, Any]]:
    """The first records of a huge jsonl file, from a range request.

    ∞Bench publishes one file per task and they run to hundreds of megabytes;
    each line is one instance and a book is under a megabyte, so a prefix holds
    plenty. Only complete lines are decoded — the last one is always partial.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Range": f"bytes=0-{max_bytes - 1}"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        text = response.read().decode("utf-8", errors="replace")
    records = []
    for line in text.splitlines()[:-1]:
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            break
        if len(records) >= count:
            break
    return records


def parquet_rows(dataset: str, config: str, split: str, limit: int = 1) -> list[dict[str, Any]]:
    """The rows API refuses a row it cannot fit in a response — 10M tokens of
    BABILong is 37MB — so the longest configurations come from the parquet
    files themselves. `pyarrow` is an eval-harness dependency, not one of the
    scaffold's, and it is imported here so a checkout without it still runs
    everything else.
    """
    import pyarrow.parquet as pq  # noqa: PLC0415 — optional, and only for the giants

    listing = json.loads(_get(f"https://huggingface.co/api/datasets/{dataset}/parquet"))
    files = listing[config][split] if isinstance(listing, dict) else []
    if not files:
        raise RuntimeError(f"no parquet listed for {dataset} {config}/{split}")
    path = cached(f"{dataset.replace('/', '_')}-{config}-{split}.parquet", files[0])
    table = pq.read_table(path)
    return table.slice(0, limit).to_pylist()


def rows(dataset: str, config: str, split: str, offset: int, length: int) -> list[dict[str, Any]]:
    """A slice of a public dataset through the rows API.

    The API caps a response at a few megabytes, so `length` stays small for the
    long configurations — one row of BABILong at 1M tokens is 4MB of text.
    """
    query = urllib.parse.urlencode(
        {
            "dataset": dataset,
            "config": config,
            "split": split,
            "offset": offset,
            "length": length,
        }
    )
    payload = json.loads(_get(f"{ROWS}?{query}"))
    return [item["row"] for item in payload["rows"]]
