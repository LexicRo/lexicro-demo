"""Pre-baked hero analyses, served without touching the API.

FR-027: the examples most visitors click must never consume quota and never
wait on a cold model. The fixture also stores the model_version it was
generated under -- ADR-0013 guarantees that same input plus same model_version
gives identical output, so a version change silently invalidates this file.
/healthz compares the two (Task 9).
"""
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Heroes:
    model_version: str
    by_text: dict[str, dict]
    pairs: list[dict]


def normalise(text: str) -> str:
    """Case-fold and collapse whitespace. Diacritics are PRESERVED --
    stripping them would let 'mancare' hit the cached 'mâncare' analysis and
    serve output for a word the visitor did not type."""
    folded = unicodedata.normalize("NFC", text).casefold()
    return " ".join(folded.split())


def load(path: Path) -> Heroes:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    by_text: dict[str, dict] = {}
    for pair in data["pairs"]:
        for side in ("a", "b"):
            by_text[normalise(pair[side]["text"])] = pair[side]["analysis"]
    return Heroes(
        model_version=data["model_version"],
        by_text=by_text,
        pairs=data["pairs"],
    )


def lookup(heroes: Heroes, text: str) -> dict | None:
    return heroes.by_text.get(normalise(text))
