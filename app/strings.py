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
        "err_bad_input": "That sentence could not be analysed. Try rephrasing it.",
        "err_unavailable": "Analysis is unavailable right now. Please try again shortly.",
        "cta": "Get a free API key",
        "truncated_note": "This text was truncated before analysis.",
        "about": "This demo calls the public LexicRo API. Full endpoint documentation, accuracy figures and licensing are in the guide.",
        "guide_link": "Read the guide",
        "attribution_link": "Attribution and licences",
        "lang_switch": "Română",
        "hero_form_label": "one form, two readings",
        "theme_label": "Appearance",
        "theme_auto": "Match system",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "lang_en": "English",
        "lang_ro": "Română",
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
        "err_bad_input": "Propoziția nu a putut fi analizată. Încearcă să o reformulezi.",
        "err_unavailable": "Analiza nu este disponibilă momentan. Încearcă din nou în scurt timp.",
        "cta": "Obține o cheie API gratuită",
        "truncated_note": "Textul a fost trunchiat înainte de analiză.",
        "about": "Această demonstrație apelează API-ul public LexicRo. Documentația completă, cifrele de acuratețe și licențierea se află în ghid.",
        "guide_link": "Citește ghidul",
        "attribution_link": "Atribuire și licențe",
        "lang_switch": "English",
        "hero_form_label": "o formă, două citiri",
        "theme_label": "Aspect",
        "theme_auto": "Ca sistemul",
        "theme_light": "Luminos",
        "theme_dark": "Întunecat",
        "lang_en": "English",
        "lang_ro": "Română",
    },
}


def t(lang: str, key: str) -> str:
    table = STRINGS[normalise_lang(lang)]
    if key not in table:
        raise KeyError(key)
    return table[key]


# Plain-language glosses for UD feature values, shown on hover and on tap.
# Deliberately NOT part of STRINGS: these are a lookup table rather than page
# copy, and holding them here keeps the key-parity test focused on the copy a
# translator actually has to maintain.
#
# Partial by design. A value with no gloss simply shows no tooltip -- better
# than inventing a translation for a term whose Romanian equivalent is not
# obvious. Keyed by the raw "Feature=Value" the API returns.
GLOSSES: dict[str, dict[str, str]] = {
    "en": {
        "Number=Sing": "singular", "Number=Plur": "plural",
        "Person=1": "first person", "Person=2": "second person", "Person=3": "third person",
        "Gender=Masc": "masculine", "Gender=Fem": "feminine", "Gender=Neut": "neuter",
        "Case=Nom": "nominative", "Case=Acc": "accusative",
        "Case=Acc,Nom": "accusative or nominative — the form does not distinguish them",
        "Case=Dat,Gen": "dative or genitive — the form does not distinguish them",
        "Case=Voc": "vocative",
        "Definite=Def": "definite — carries the article",
        "Definite=Ind": "indefinite",
        "Tense=Pres": "present", "Tense=Past": "past", "Tense=Imp": "imperfect",
        "Tense=Fut": "future", "Tense=Pqp": "pluperfect",
        "Mood=Ind": "indicative", "Mood=Sub": "subjunctive",
        "Mood=Imp": "imperative", "Mood=Cnd": "conditional",
        "VerbForm=Fin": "finite verb", "VerbForm=Inf": "infinitive",
        "VerbForm=Part": "participle", "VerbForm=Ger": "gerund",
        "Degree=Pos": "positive degree", "Degree=Cmp": "comparative", "Degree=Sup": "superlative",
        "PronType=Prs": "personal pronoun", "PronType=Ind": "indefinite",
        "PronType=Int,Rel": "interrogative or relative", "PronType=Dem": "demonstrative",
        "AdpType=Prep": "preposition",
        "Strength=Strong": "strong form", "Strength=Weak": "weak (clitic) form",
        "Poss=Yes": "possessive", "Reflex=Yes": "reflexive",
        "NumType=Card": "cardinal number", "NumType=Ord": "ordinal number",
        "NumForm=Word": "written as a word", "NumForm=Digit": "written as digits",
        "Polarity=Pos": "affirmative", "Polarity=Neg": "negative",
    },
    "ro": {
        "Number=Sing": "singular", "Number=Plur": "plural",
        "Person=1": "persoana întâi", "Person=2": "persoana a doua", "Person=3": "persoana a treia",
        "Gender=Masc": "masculin", "Gender=Fem": "feminin", "Gender=Neut": "neutru",
        "Case=Nom": "nominativ", "Case=Acc": "acuzativ",
        "Case=Acc,Nom": "acuzativ sau nominativ — forma nu le distinge",
        "Case=Dat,Gen": "dativ sau genitiv — forma nu le distinge",
        "Case=Voc": "vocativ",
        "Definite=Def": "articulat hotărât",
        "Definite=Ind": "nearticulat",
        "Tense=Pres": "prezent", "Tense=Past": "perfect", "Tense=Imp": "imperfect",
        "Tense=Fut": "viitor", "Tense=Pqp": "mai mult ca perfect",
        "Mood=Ind": "indicativ", "Mood=Sub": "conjunctiv",
        "Mood=Imp": "imperativ", "Mood=Cnd": "condițional",
        "VerbForm=Fin": "verb predicativ", "VerbForm=Inf": "infinitiv",
        "VerbForm=Part": "participiu", "VerbForm=Ger": "gerunziu",
        "Degree=Pos": "grad pozitiv", "Degree=Cmp": "comparativ", "Degree=Sup": "superlativ",
        "PronType=Prs": "pronume personal", "PronType=Ind": "nehotărât",
        "PronType=Int,Rel": "interogativ sau relativ", "PronType=Dem": "demonstrativ",
        "AdpType=Prep": "prepoziție",
        "Strength=Strong": "formă accentuată", "Strength=Weak": "formă neaccentuată",
        "Poss=Yes": "posesiv", "Reflex=Yes": "reflexiv",
        "NumType=Card": "numeral cardinal", "NumType=Ord": "numeral ordinal",
        "NumForm=Word": "scris în litere", "NumForm=Digit": "scris cu cifre",
        "Polarity=Pos": "afirmativ", "Polarity=Neg": "negativ",
    },
}

# Which family a feature belongs to, driving chip colour. Encodes something true
# about the grammar rather than decorating: verbal features describe the event,
# agreement features describe how the word agrees with its neighbours, and
# lexical features describe the word's own type.
FEATURE_FAMILY: dict[str, str] = {
    "Mood": "verbal", "Tense": "verbal", "VerbForm": "verbal", "Person": "verbal",
    "Aspect": "verbal", "Voice": "verbal",
    "Case": "agreement", "Gender": "agreement", "Number": "agreement",
    "Definite": "agreement", "Degree": "agreement",
    "PronType": "lexical", "AdpType": "lexical", "NumType": "lexical",
    "NumForm": "lexical", "Poss": "lexical", "Reflex": "lexical",
    "Strength": "lexical", "Polarity": "lexical", "Variant": "lexical",
}
