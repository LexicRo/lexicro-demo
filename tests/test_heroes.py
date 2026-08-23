import json
from pathlib import Path

import pytest
from app.heroes import Heroes, load, lookup, normalise

FIXTURE = {
    "model_version": "phase2-baseline-0.1",
    "generated_at": "2026-08-23",
    "pairs": [
        {
            "form": "sare",
            "a": {"text": "Pune sare în mâncare.", "analysis": {"sentences": ["A"]}},
            "b": {"text": "Pisica sare pe masă.", "analysis": {"sentences": ["B"]}},
        }
    ],
}


@pytest.fixture
def fixture_path(tmp_path):
    p = tmp_path / "heroes.json"
    p.write_text(json.dumps(FIXTURE, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_reads_model_version_and_pairs(fixture_path):
    h = load(fixture_path)
    assert isinstance(h, Heroes)
    assert h.model_version == "phase2-baseline-0.1"
    assert len(h.pairs) == 1


def test_lookup_hits_on_exact_text(fixture_path):
    h = load(fixture_path)
    assert lookup(h, "Pune sare în mâncare.") == {"sentences": ["A"]}
    assert lookup(h, "Pisica sare pe masă.") == {"sentences": ["B"]}


def test_lookup_hits_despite_whitespace_and_case(fixture_path):
    h = load(fixture_path)
    assert lookup(h, "  pune SARE în mâncare.  ") == {"sentences": ["A"]}


def test_lookup_misses_on_anything_else(fixture_path):
    assert lookup(load(fixture_path), "Un text oarecare.") is None


def test_normalise_collapses_internal_whitespace():
    assert normalise("  Pune   sare  ") == normalise("pune sare")


def test_diacritics_are_not_stripped_by_normalise():
    """Case-folding must not turn 'mâncare' into 'mancare' -- a cache hit on a
    different string would serve the wrong analysis."""
    assert normalise("mâncare") != normalise("mancare")
