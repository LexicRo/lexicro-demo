"""Page copy, EN and RO.

Two rules, both enforced by tests:
  1. The key sets must be identical -- a missing translation fails the suite
     rather than rendering an empty element in production.
  2. No string contains a digit. The demo demonstrates; /guide claims. Every
     figure in this project's history drifted at least once (see the figures
     register in 30-api-spec.md), and a second language would double the
     surface. The only exception is the character cap, which is our own
     constant rather than a claim about the model.

UD vocabulary -- UPOS, FEATS, lemma -- is NOT translated. It is Universal
Dependencies notation, not English prose.
"""
from .session import normalise_lang

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "LexicRo — Romanian morphological analysis",
        "tagline": "Every word, in context: its lemma, part of speech and features.",
        "hero_heading": "The same word, two readings",
        "hero_explain": "A dictionary lists both readings. Only the sentence says which one you are looking at.",
        "analyser_heading": "Try a sentence",
        "placeholder": "Paste a Romanian sentence…",
        "submit": "Analyse",
        "col_form": "form",
        "col_lemma": "lemma",
        "col_upos": "UPOS",
        "col_feats": "FEATS",
        "col_source": "source",
        "candidates_label": "Readings the dictionary offered",
        "json_toggle": "Show raw JSON",
        "max_chars_hint": "500 characters max",
        "err_too_long": "That is longer than the demo accepts. Shorten it, or get a key and call the API directly.",
        "err_no_session": "Your session expired. Reload the page and try again.",
        "err_throttled": "You have reached the demo limit — get your own free key.",
        "err_quota": "The demo's budget for today is spent — get your own free key.",
        "err_timeout": "That took too long. Try a shorter sentence.",
        "err_unavailable": "Analysis is unavailable right now. Please try again shortly.",
        "cta": "Get a free API key",
        "truncated_note": "This text was truncated before analysis.",
        "about": "This demo calls the public LexicRo API. Full endpoint documentation, accuracy figures and licensing are in the guide.",
        "guide_link": "Read the guide",
        "attribution_link": "Attribution and licences",
        "lang_switch": "Română",
    },
    "ro": {
        "title": "LexicRo — analiză morfologică pentru limba română",
        "tagline": "Fiecare cuvânt, în context: lema, partea de vorbire și trăsăturile.",
        "hero_heading": "Același cuvânt, două citiri",
        "hero_explain": "Dicționarul le listează pe amândouă. Doar propoziția spune la care dintre ele te uiți.",
        "analyser_heading": "Încearcă o propoziție",
        "placeholder": "Scrie o propoziție în română…",
        "submit": "Analizează",
        "col_form": "formă",
        "col_lemma": "lemma",
        "col_upos": "UPOS",
        "col_feats": "FEATS",
        "col_source": "sursă",
        "candidates_label": "Citirile oferite de dicționar",
        "json_toggle": "Arată JSON brut",
        "max_chars_hint": "maximum 500 de caractere",
        "err_too_long": "Textul depășește limita demonstrației. Scurtează-l sau folosește o cheie proprie și apelează API-ul direct.",
        "err_no_session": "Sesiunea a expirat. Reîncarcă pagina și încearcă din nou.",
        "err_throttled": "Ai atins limita demonstrației — obține propria cheie gratuită.",
        "err_quota": "Bugetul demonstrației pe ziua de azi s-a epuizat — obține propria cheie gratuită.",
        "err_timeout": "A durat prea mult. Încearcă o propoziție mai scurtă.",
        "err_unavailable": "Analiza nu este disponibilă momentan. Încearcă din nou în scurt timp.",
        "cta": "Obține o cheie API gratuită",
        "truncated_note": "Textul a fost trunchiat înainte de analiză.",
        "about": "Această demonstrație apelează API-ul public LexicRo. Documentația completă, cifrele de acuratețe și licențierea se află în ghid.",
        "guide_link": "Citește ghidul",
        "attribution_link": "Atribuire și licențe",
        "lang_switch": "English",
    },
}


def t(lang: str, key: str) -> str:
    table = STRINGS[normalise_lang(lang)]
    if key not in table:
        raise KeyError(key)
    return table[key]
