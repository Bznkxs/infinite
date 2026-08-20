"""Infinite writing: produce far more than a context can hold, at a fixed one.

The [Infinite Context Test](../../docs/Design%20Tests%20(Top%20Down).md) asks for
three things and the project has evidence for two. Reading has six live results
and a scaling test; complexity has the width probe. **Writing has never been put
to a model at all** — the offline test asserts that appending ten thousand lines
through `bash` does not move the request, which was never in doubt.

So this is the missing probe, and it is built to be run twice:

    python -m eval.run volume --config 120 --profile frame
    python -m eval.run volume --config 1200 --profile frame

Ten times the output, the same geometry. The claim is *not* that the run
succeeds — it is that `max_request_tokens` does not move between those two rows
while the output does. That is the same shape as the reading test, which scales
4KB to 4MB and asserts one number stays put, and it is the only shape in which
"infinite" means anything measurable.

The corpus is generated here, deterministically, from a seed. Nothing is fetched,
so unlike `width` this probe runs on a fresh clone.

**What this cannot test, stated plainly.** Any output a grader can check
mechanically is output a program could produce, and `bash` is deliberately
unbounded (0.0.8b §1) — so an agent that writes a script to emit the whole file
has passed, and arguably should: the scaffold's claim is about the context, not
about where the characters came from. What separates the two routes is
measurable rather than forbidden, so the grade reports it: `generated_chars` from
the trajectory against the bytes on disk. A run whose output is far larger than
everything it generated used a program; a run where they are comparable wrote it.
Both are results. Neither is cheating.
"""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from ..workspace import Instance

NAME = "volume"

OUTPUT = "cards.md"
SOURCE = "records.md"

#: Drawn from fixed lists so the answers are exact strings rather than a
#: judgement, and so the same seed gives the same corpus on any machine.
COLOURS = ("teal", "amber", "crimson", "slate", "olive", "indigo", "ochre", "mauve")
ROOMS = ("pantry", "cellar", "loft", "annex", "scullery", "vestibule", "gallery")
NAMES = ("Marla", "Osei", "Petra", "Ilya", "Nadia", "Rafe", "Juno", "Casimir")
ITEMS = ("kettle", "ledger", "crate", "lantern", "sextant", "hamper", "spindle")

#: One record in, one card out. The card is six lines, so the output is several
#: times the input and the work per record is a lookup rather than a paraphrase:
#: the point is the volume and the fixed context, not the difficulty.
CARD_FIELDS = ("item", "colour", "room", "keeper", "time", "weight")

RECORD_TEMPLATE = """## record {index:04d}
key: {key}

The {item} in the {room} is {colour}. {keeper} signed for it at {time}. It
weighs {weight}kg and has been there since the {season} inventory.
"""

TASK_TEMPLATE = """# Task: turn every record into a card

`{source}` holds {count} records, {source_size} characters in all — far more than
your canvas, so page through it with `load` or read it with `sed`/`grep` rather
than trying to hold it.

Write `{output}`: one card per record, in record order, nothing else in the file.
A card is exactly seven lines, the last of them blank:

    ### <key>
    item: <item>
    colour: <colour>
    room: <room>
    keeper: <name>
    time: <hh:mm>
    weight: <n>

`weight` is the number only, without `kg`. Every field comes from that record and
from no other.

{count} cards is about {output_size} characters, which is also more than your
context — so the file is the work, and the file is on disk. Append as you go.

## Done

    {check}

The scaffold runs that after every step and puts the verdict at the top of your
dump, so you can see how far through you are without counting. It counts cards;
it does not check them. Getting the count right and the fields wrong is the
failure this task is built to catch, so check your own work against the records
before you answer.

Write your response when the cards are right: `answer` is the number of cards,
`evidence` is the output of the command above.
"""

CHECK = "test $(grep -c '^### ' {output}) -eq {count}"

#: Six lines and a blank one, at about the width the templates produce.
CARD_CHARS = 90


#: Unambiguous in a proportional font and in a terminal: no I/O/0/1.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _record(
    index: int, rng: random.Random, taken: set[str]
) -> tuple[str, dict[str, str]]:
    # Unique by construction, not by luck. Five characters out of this alphabet
    # is 33.5M keys, which at 1,200 records is still a 2% chance of a collision —
    # and a collision would silently halve a record's grade, since the grader
    # keys the cards it parses.
    while True:
        key = "".join(rng.choice(ALPHABET) for _ in range(5))
        if key not in taken:
            taken.add(key)
            break
    fields = {
        "item": rng.choice(ITEMS),
        "colour": rng.choice(COLOURS),
        "room": rng.choice(ROOMS),
        "keeper": rng.choice(NAMES),
        "time": f"{rng.randrange(6, 22):02d}:{rng.randrange(0, 60):02d}",
        "weight": str(rng.randrange(2, 99)),
    }
    text = RECORD_TEMPLATE.format(
        index=index,
        key=key,
        season=rng.choice(("spring", "autumn", "winter", "summer")),
        **fields,
    )
    return text, {"key": key, **fields}


def build(count: int, *, seed: int = 8) -> tuple[str, list[dict[str, str]]]:
    """The corpus and the answers, from a seed, so a rerun is the same task."""
    rng = random.Random(seed)
    records, answers, taken = [], [], set()
    for index in range(count):
        text, fields = _record(index, rng, taken)
        records.append(text)
        answers.append(fields)
    return "\n".join(records), answers


def load(*, config: str = "120", offset: int = 0, count: int = 1) -> list[Instance]:
    """One instance per `-n`, all the same size; `--config` is the size.

    Scaling is what the probe is for, so the size is the configuration and not
    the instance: two rows at 120 and 1200 are the measurement, and `-n 3` at
    one size is the variance.
    """
    records = int(config)
    corpus, answers = build(records)
    check = CHECK.format(output=OUTPUT, count=records)
    task = TASK_TEMPLATE.format(
        source=SOURCE,
        output=OUTPUT,
        count=records,
        check=check,
        source_size=f"{len(corpus):,}",
        output_size=f"{records * CARD_CHARS:,}",
    )
    return [
        Instance(
            benchmark=NAME,
            instance_id=f"cards-{records}-{offset + i}",
            task=task,
            files={SOURCE: corpus},
            truth={"records": records, "answers": answers, "output": OUTPUT, "check": check},
            # Generous, because running out of steps is a result here rather than
            # a mistake: the question is how much a run can produce, and a budget
            # that cannot fit the work would answer it in advance.
            max_steps=max(40, records // 4),
        )
        for i in range(count)
    ]


CARD = re.compile(r"^### (\S+)\s*$")


def _cards(text: str) -> list[dict[str, str]]:
    """Parse `cards.md` leniently: the grader is strict about fields, not layout.

    A run that got every field right and put eight lines in a card has not failed
    the Infinite Context Test, and grading it as though it had would hide the
    result this probe exists to produce.
    """
    cards: list[dict[str, str]] = []
    for line in text.splitlines():
        if match := CARD.match(line):
            cards.append({"key": match.group(1)})
        elif cards and ":" in line:
            name, _, value = line.partition(":")
            name = name.strip().lower()
            if name in CARD_FIELDS:
                cards[-1][name] = value.strip().removesuffix("kg").strip()
    return cards


def grade(
    response: dict[str, Any] | None,
    truth: dict[str, Any],
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Coverage and correctness separately, because they fail separately.

    A run that wrote 1,200 cards with the wrong fields has proved the writing
    claim and failed the task; a run that wrote 40 correct ones has proved
    nothing about volume. Reporting one number would lose whichever result
    happened.
    """
    answers: list[dict[str, str]] = truth["answers"]
    if workspace is None:
        return {"correct": False, "answer": None, "target": len(answers)}
    path = workspace / truth["output"]
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    cards = _cards(text)
    by_key = {card["key"]: card for card in cards}

    exact = present = 0
    first_wrong = None
    for expected in answers:
        card = by_key.get(expected["key"])
        if card is None:
            continue
        present += 1
        wrong = [
            field
            for field in CARD_FIELDS
            if card.get(field) != expected[field]
        ]
        if wrong:
            if first_wrong is None:
                first_wrong = {"key": expected["key"], "fields": wrong}
        else:
            exact += 1

    records = len(answers)
    return {
        "correct": exact == records,
        # The writing claim: bytes produced, and how far through the corpus the
        # run got. These are the numbers to compare across two `--config`s.
        "output_bytes": len(text),
        "cards_written": len(cards),
        "records": records,
        "coverage": round(present / records, 3) if records else 0.0,
        "exact": exact,
        "accuracy": round(exact / records, 3) if records else 0.0,
        "first_wrong": first_wrong,
        "duplicate_keys": len(cards) - len(by_key),
        "answer": (response or {}).get("answer"),
        "target": records,
    }
