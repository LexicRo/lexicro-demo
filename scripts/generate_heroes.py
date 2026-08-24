"""Regenerate fixtures/heroes.json against production.

Run this whenever `model_version` changes -- `/healthz` returns 503 until you
do, because a fixture generated under different weights is not what the live
model would produce and the page would show stale output beside a live
analyser.

    python scripts/generate_heroes.py

Reads the demo key from the environment, or from a local .env if one exists.
`.env` is gitignored and dockerignored, so the key never reaches the repo or
an image layer -- it is the right place to keep it.

Note the .env load happens HERE and not in app.config.load_settings(): the
test suite deliberately unsets LEXICRO_DEMO_KEY to prove the failure message
names the missing variable, and a .env that load_settings() picked up would
silently defeat that test on any machine where the file exists.
"""
import json
import sys
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.config import load_settings  # noqa: E402

# Each entry is (form, sentence where it is a NOUN, sentence where it is a VERB).
# These were chosen by measurement, not by intuition: the project's original
# hero example (`era` / `eră`) was falsified against production on 2026-08-21 --
# the model resolved it to lemma `fi` in five of five contexts, including one
# where Romanian syntax forbids a finite verb. See
# lexicro-docs/docs/_evidence/2026-08-21-hero-example-probe/.
#
# The rule that came out of that: pick BALANCED ambiguities, never famous ones.
# A famous ambiguity is famous because one reading dominates, which is exactly
# the case this model gets wrong.
PAIRS = [
    ("sare", "Pune sare în mâncare.", "Pisica sare pe masă."),
    ("port", "Constanța are un port mare.", "Eu port o cămașă albă."),
]

OUT = ROOT / "fixtures" / "heroes.json"


def lemma_for(analysis: dict, form: str) -> str | None:
    """The lemma the model chose for `form` in this analysis."""
    for sentence in analysis.get("sentences", []):
        for token in sentence.get("tokens", []):
            if token.get("form", "").casefold() == form.casefold():
                return token.get("lemma")
    return None


def main() -> int:
    settings = load_settings()
    headers = {"X-API-Key": settings.api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=30.0) as client:
        version = client.get(f"{settings.api_base}/analyze/info").json()["model_version"]

        pairs, failures = [], []
        for form, text_a, text_b in PAIRS:
            sides = {}
            for side, text in (("a", text_a), ("b", text_b)):
                response = client.post(
                    f"{settings.api_base}/analyze",
                    json={"text": text},
                    headers=headers,
                )
                response.raise_for_status()
                sides[side] = {"text": text, "analysis": response.json()}

            lemma_a = lemma_for(sides["a"]["analysis"], form)
            lemma_b = lemma_for(sides["b"]["analysis"], form)
            print(f"  {form}: {lemma_a!r} vs {lemma_b!r}")

            # THE STOP CONDITION, enforced here rather than left to whoever runs
            # this. If both sentences give the same lemma, the model is not
            # disambiguating this form and the hero panel would be a page-sized
            # demonstration of the product failing to do the one thing it claims.
            # That is precisely how `era` was caught, and only because someone
            # checked before building the page around it.
            if lemma_a is None or lemma_b is None:
                failures.append(f"{form}: form not found in one of the analyses")
            elif lemma_a == lemma_b:
                failures.append(
                    f"{form}: both sentences resolved to {lemma_a!r} -- "
                    f"no disambiguation, this pair is falsified"
                )

            pairs.append({"form": form, **sides})

    if failures:
        print("\nREFUSING TO WRITE THE FIXTURE:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nThe existing fixture is untouched. Find a replacement pair using the "
            "method in lexicro-docs/docs/_evidence/2026-08-21-hero-example-probe/ "
            "before building anything on this.",
            file=sys.stderr,
        )
        return 1

    OUT.write_text(
        json.dumps(
            {
                "model_version": version,
                "generated_at": date.today().isoformat(),
                "pairs": pairs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUT} at model_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
