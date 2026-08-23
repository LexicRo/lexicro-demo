import re

from app.session import LANGUAGES
from app.strings import STRINGS, t


def test_every_language_has_identical_keys():
    """A missing translation must fail here, not render an empty div on
    announcement day."""
    key_sets = {lang: set(STRINGS[lang]) for lang in LANGUAGES}
    reference = key_sets["en"]
    for lang, keys in key_sets.items():
        assert keys == reference, f"{lang} differs: {keys ^ reference}"


def test_all_languages_are_present():
    assert set(STRINGS) == set(LANGUAGES)


def test_no_string_contains_a_hardcoded_figure():
    """Spec section 4: the demo demonstrates, the guide claims. Every number
    that circulated in this project drifted at least once -- see the figures
    register in 30-api-spec.md. Digits are the obvious vector; spelled-out
    numbers are the one that would actually get past review."""
    allowed = {"max_chars_hint"}  # renders the 500 cap, which is OUR constant
    digit = re.compile(r"\d|%")
    # Magnitude and measurement words only. Small cardinals are deliberately
    # absent: "two readings" describes this page's own structure and cannot
    # drift, whereas every accuracy or latency claim this project has ever
    # made needs a magnitude word or a digit to express.
    number_words = (
        "hundred", "thousand", "million", "percent",
        "sută", "sute", "mie", "mii", "milion", "milioane", "procent", "procente",
    )
    for lang, table in STRINGS.items():
        for key, value in table.items():
            if key in allowed:
                continue
            assert not digit.search(value), f"{lang}.{key} contains a digit or %: {value!r}"
            lowered = value.casefold()
            for word in number_words:
                assert word not in lowered.split() and word not in lowered.replace(",", " ").split(), (
                    f"{lang}.{key} contains the number word {word!r}: {value!r}"
                )


def test_ud_terms_are_not_translated():
    for lang in LANGUAGES:
        assert STRINGS[lang]["col_upos"] == "UPOS"
        assert STRINGS[lang]["col_feats"] == "FEATS"
        assert STRINGS[lang]["col_lemma"] == "lemma"


def test_t_falls_back_to_english_for_unknown_language():
    assert t("de", "col_upos") == STRINGS["en"]["col_upos"]


def test_t_raises_on_an_unknown_key():
    try:
        t("en", "no_such_key")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
