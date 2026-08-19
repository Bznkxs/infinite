"""BABILong — bAbI reasoning over facts hidden in a long distractor corpus.

Published by the RMT team (HF `RMT-team/babilong`), in lengths from 0k to 10M
tokens. A handful of relevant sentences are scattered through a PG-19 book and
the question asks something that needs one, two or three of them. It is the
closest published benchmark to what this scaffold claims: the material is
arbitrarily larger than any context, the answer is a word, and the grader is
exact.

`qa1` needs one supporting fact, `qa2` two, `qa3` three; `qa4`/`qa5` are
relational; the harder splits go to counting and lists.
"""

from __future__ import annotations

import re
from typing import Any

from ..fetch import prefix_records, rows
from ..workspace import Instance

NAME = "babilong"
DATASET = "RMT-team/babilong"
#: Every length the dataset publishes. The scaffold's whole claim is that these
#: are the same problem to it.
LENGTHS = ("0k", "1k", "4k", "16k", "64k", "128k", "256k", "512k", "1M", "10M")
TASKS = ("qa1", "qa2", "qa3", "qa4", "qa5", "qa6", "qa7", "qa8", "qa9", "qa10")

#: Configurations the rows API will not serve — one record is tens of megabytes.
GIANT = ("10M",)
GIANT_PREFIX_BYTES = 64 * 1024 * 1024

TASK_TEMPLATE = """# Question about a long document

`data/corpus.txt` is {size} characters of text — far more than fits in your
canvas, so you will have to work through it rather than read it whole.

Scattered through it are a few sentences that state facts about people picking
things up, putting them down, and moving between rooms. Everything else is a
novel and is irrelevant. The facts are the only sentences of that kind in the
file, and later facts about the same person supersede earlier ones.

**Question: {question}**

Answer from the file, not from memory. The answer is one or two words — a name,
a room, an object, a list, or `yes`/`no`.

Write your response file as JSON: `answer` is the answer alone, with no
sentence around it; `evidence` quotes the sentence or sentences you took it
from.
"""


def load(*, config: str = "64k", split: str = "qa2", offset: int = 0, count: int = 1) -> list[Instance]:
    # The rows API caps its response, and one 10M-token row is 37MB of text, so
    # the longest configuration is read from the parquet file instead.
    fetched = (
        prefix_records(
            f"https://huggingface.co/datasets/{DATASET}/resolve/main/data/{split}/{config}.json",
            max_bytes=GIANT_PREFIX_BYTES,
            count=offset + count,
        )[offset:]
        if config in GIANT
        else rows(DATASET, config, split, offset, count)
    )
    instances = []
    for i, row in enumerate(fetched):
        corpus = row["input"]
        instances.append(
            Instance(
                benchmark=NAME,
                instance_id=f"{config}-{split}-{offset + i}",
                task=TASK_TEMPLATE.format(size=f"{len(corpus):,}", question=row["question"].strip()),
                files={"data/corpus.txt": corpus},
                truth={
                    "target": row["target"].strip(),
                    "question": row["question"].strip(),
                    "config": config,
                    "split": split,
                    "chars": len(corpus),
                },
                max_steps=steps_for(config),
            )
        )
    return instances


def steps_for(config: str) -> int:
    """A budget that scales with the corpus, since paging is what it costs."""
    return {"0k": 12, "1k": 12, "4k": 16, "16k": 20, "64k": 30, "128k": 40,
            "256k": 60, "512k": 80, "1M": 120, "10M": 300}.get(config, 40)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def grade(response: dict[str, Any] | None, truth: dict[str, Any]) -> dict[str, Any]:
    """The official metric: the target has to appear in the answer.

    BABILong scores a generation by whether the gold string is in it, which is
    the right call for a scaffold that may answer "kitchen" or "the kitchen".
    Exact match is reported alongside it, because the two differing is worth
    seeing.
    """
    if not response:
        return {"correct": False, "exact": False, "answer": None}
    answer = _normalise(str(response.get("answer", "")))
    target = _normalise(truth["target"])
    # A list answer ("football,apple") is graded on its members, in any order.
    members = [t for t in re.split(r"[,\s]+", target) if t]
    contains = all(m in answer.split() for m in members) if members else False
    return {
        "correct": contains,
        "exact": answer == target,
        "answer": response.get("answer"),
        "target": truth["target"],
    }
