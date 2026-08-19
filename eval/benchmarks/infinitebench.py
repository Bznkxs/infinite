"""∞Bench (InfiniteBench) — real long documents, 100k+ tokens average.

Published as plain jsonl files on HF (`xinrongzhang2022/InfiniteBench`). Two
tasks are used here: `longbook_choice_eng` (a question about a whole novel, four
options, graded by the option) and `longbook_qa_eng` (the same but free-form,
graded by overlap with the reference). They differ from BABILong in that the
answer is not hidden in distractors — the whole book is the material.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..fetch import prefix_lines
from ..workspace import Instance

NAME = "infinitebench"
BASE = "https://huggingface.co/datasets/xinrongzhang2022/InfiniteBench/resolve/main"
TASKS = {
    "longbook_choice_eng": "multiple choice over a whole book",
    "longbook_qa_eng": "free-form question over a whole book",
}

CHOICE_TASK = """# A question about a whole book

`data/book.txt` is {size} characters — a complete novel, far more than fits in
your canvas. Work through it; do not answer from memory of the book.

**Question: {question}**

Options:
{options}

Write your response file as JSON: `answer` is the letter of the option you
choose (A, B, C or D) and nothing else; `evidence` quotes what the book says.
"""

QA_TASK = """# A question about a whole book

`data/book.txt` is {size} characters — a complete novel, far more than fits in
your canvas. Work through it; do not answer from memory of the book.

**Question: {question}**

Write your response file as JSON: `answer` is the answer alone, as short as it
can be said (a name, a place, a phrase); `evidence` quotes what the book says.
"""


#: The files run to hundreds of megabytes and a book is well under one, so the
#: harness reads a prefix rather than the whole task.
PREFIX_BYTES = 24 * 1024 * 1024


def load(*, config: str = "longbook_choice_eng", offset: int = 0, count: int = 1, **_) -> list[Instance]:
    fetched = prefix_lines(f"{BASE}/{config}.jsonl", max_bytes=PREFIX_BYTES, count=offset + count)
    instances = []
    for index, row in enumerate(fetched):
            if index < offset:
                continue
            if len(instances) >= count:
                break
            book = row["context"]
            options = row.get("options") or []
            letters = "ABCD"
            if config.endswith("choice_eng"):
                rendered = "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(options))
                task = CHOICE_TASK.format(size=f"{len(book):,}", question=row["input"].strip(), options=rendered)
                answer = row["answer"][0] if isinstance(row["answer"], list) else row["answer"]
                target = letters[options.index(answer)] if answer in options else str(answer)
            else:
                task = QA_TASK.format(size=f"{len(book):,}", question=row["input"].strip())
                target = row["answer"][0] if isinstance(row["answer"], list) else str(row["answer"])
            instances.append(
                Instance(
                    benchmark=NAME,
                    instance_id=f"{config}-{index}",
                    task=task,
                    files={"data/book.txt": book},
                    truth={"target": target, "options": options, "config": config, "chars": len(book)},
                    max_steps=60,
                )
            )
    return instances


def _words(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


def grade(response: dict[str, Any] | None, truth: dict[str, Any]) -> dict[str, Any]:
    if not response:
        return {"correct": False, "answer": None, "target": truth["target"]}
    answer = str(response.get("answer", "")).strip()
    target = str(truth["target"]).strip()
    if truth["config"].endswith("choice_eng"):
        letter = answer[:1].upper()
        return {"correct": letter == target.upper(), "answer": answer, "target": target}
    # Free-form: ∞Bench scores by token overlap with the reference.
    gold, got = _words(target), _words(answer)
    overlap = len(gold & got) / len(gold) if gold else 0.0
    return {"correct": overlap >= 0.5, "f1": round(overlap, 3), "answer": answer, "target": target}
