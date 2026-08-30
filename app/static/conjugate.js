/* The conjugate pane's rendering.
 *
 * Separate from app.js so neither becomes a grab-bag: that file renders token
 * rows for /analyze, this one renders conjugation tables. They share nothing
 * but the page.
 *
 * Every node here is built with createElement and textContent. Never
 * innerHTML: every string rendered below is a conjugated form that arrived
 * from upstream.
 */
const C_LABELS = JSON.parse(document.getElementById("labels").textContent);
const MOOD_GLOSSES = JSON.parse(document.getElementById("mood-glosses").textContent);

/* The API's sentinel for "this verb has no such form", used for the
 * impersonal and defective verbs. Rendering it literally would put a stray
 * hyphen in a table cell; a visitor typing `a ninge` ("to snow") meets six of
 * these in the conditional, and they should read as a deliberate absence. */
const NO_FORM = "-";

/* Open by default: what a visitor actually wants, plus the conditional, which
 * is LexicRo's own work rather than the underlying library's. */
const OPEN_BY_DEFAULT = new Set(["indicativ", "condițional", "imperativ"]);

/* The order moods are shown in. The API serialises its JSON with sorted keys,
 * so iterating the response puts `indicativ` fourth and `condițional` last --
 * alphabetical order is not an order anyone reads a paradigm in. This is the
 * grammatical order, and it is ours to choose because it is presentation.
 * Anything the API adds later that is not listed here still renders, after
 * these, rather than vanishing. */
const MOOD_ORDER = [
  "indicativ",
  "conjunctiv",
  "condițional",
  "imperativ",
  "infinitiv",
  "gerunziu",
  "participiu",
];

function orderedMoods(moods) {
  const names = Object.keys(moods);
  const known = MOOD_ORDER.filter((m) => names.includes(m));
  const rest = names.filter((m) => !MOOD_ORDER.includes(m)).sort();
  return known.concat(rest);
}

/* The order tenses are shown in, for the same reason as MOOD_ORDER above.
 * The API's sorted keys put `perfect` before `prezent` in `conjunctiv`, so the
 * subjunctive card read past-then-present while `condițional` -- which LexicRo
 * derives itself, and whose keys happen to sort the right way round -- read
 * present-then-past. Two moods side by side, disagreeing about where a
 * paradigm starts.
 *
 * This is the order a paradigm is taught in: present, then the past tenses by
 * increasing distance, then future. Anything the API adds later that is not
 * listed here still renders, after these, rather than vanishing. */
const TENSE_ORDER = [
  "prezent",
  "imperfect",
  "perfect-compus",
  "perfect-simplu",
  "mai-mult-ca-perfect",
  "perfect",
  "viitor-1",
  "viitor-1-popular",
  "viitor-2",
  "viitor-2-popular",
  "imperativ",
  "negativ",
  "afirmativ",
  "gerunziu",
  "participiu",
];

function orderedTenses(tenses) {
  const names = Object.keys(tenses);
  const known = TENSE_ORDER.filter((t) => names.includes(t));
  const rest = names.filter((t) => !TENSE_ORDER.includes(t)).sort();
  return known.concat(rest);
}

async function conjugateVerb(verb) {
  const response = await fetch("/api/conjugate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ verb }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "");
  return body;
}

/** The provenance banner. ADR-0025 section 4: the predicted flag is what makes
 *  this tab worth showing at all -- "here is the conjugation, and we will tell
 *  you when we are guessing". So it is the headline, not a footnote. */
function provenanceBanner(verb) {
  const predicted = verb.provenance === "predicted";
  const el = document.createElement("p");
  el.className = "prov " + (predicted ? "prov-predicted" : "prov-template");

  // The lemma leads, because "which verb is this?" is the question a reader
  // has before "where did the forms come from?". Both messages are worded to
  // follow it as a sentence in either language.
  const lemma = document.createElement("strong");
  lemma.className = "clemma";
  lemma.textContent = infinitiveWithPrefix(verb.infinitive);

  const message = document.createElement("span");
  message.textContent = predicted ? C_LABELS.prov_predicted : C_LABELS.prov_template;

  el.append(lemma, document.createTextNode(" "), message);
  if (predicted) el.setAttribute("role", "status");
  return el;
}

/** Romanian cites an infinitive with its `a` particle, and the API returns it
 *  without one. Not translated: `a` is the Romanian marker, not English or
 *  Romanian UI copy. */
function infinitiveWithPrefix(infinitive) {
  return "a " + (infinitive || "");
}

/** Said out loud when the verb conjugated is not the one that was typed.
 *
 * The API's lookup folds diacritics, so `sari` finds the lemma `sări` the way
 * `canta` finds `cânta` -- a real convenience for anyone without a Romanian
 * keyboard. But the page previously showed a confident, correct table and
 * never said WHICH verb it had decided on, so someone typing `sari` could
 * reasonably conclude the infinitive is `a sari`. On a demo whose audience is
 * partly learning the language, that teaches a wrong lemma by omission --
 * which is worse than showing a wrong form, because nothing looks wrong.
 *
 * Compares case-insensitively and ignores a leading `a `, so citing the verb
 * properly is not reported as a correction. Diacritics are NOT folded here:
 * the difference they make is the entire point of the message.
 */
function resolvedNote(data) {
  const typed = (data.input || "").trim().replace(/^a\s+/i, "");
  const lemma = (data.verb || {}).infinitive || "";
  if (!typed || !lemma) return null;
  if (typed.toLocaleLowerCase("ro") === lemma.toLocaleLowerCase("ro")) return null;

  const el = document.createElement("p");
  el.className = "cresolved";
  el.textContent = C_LABELS.resolved_note
    .replace("{typed}", typed)
    .replace("{lemma}", infinitiveWithPrefix(lemma));
  return el;
}

function formCell(entry, markSource = true, derivedLabel = null, knownWrong = false) {
  const cell = document.createElement("div");
  cell.className = "cform";

  if (entry.form === NO_FORM) {
    cell.classList.add("is-absent");
    const dash = document.createElement("span");
    dash.className = "absent-mark";
    dash.textContent = "—";
    const why = document.createElement("small");
    why.textContent = C_LABELS.no_such_form;
    cell.append(dash, why);
    return cell;
  }

  const word = document.createElement("span");
  word.className = "cword";
  word.textContent = entry.form;

  // A form the API's own note names as wrong. Marked ON THE WORD, because a
  // caveat in a paragraph above the table loses to the word inside it -- the
  // visitor reads the form, not the prose.
  //
  // Symbol AND colour, never colour alone: a red word is invisible to a
  // red-green colourblind reader, and this is the one place the page says
  // "do not trust this".
  if (knownWrong) {
    word.classList.add("is-wrong");
    const flag = document.createElement("abbr");
    flag.className = "wrong-flag";
    flag.textContent = "*";
    flag.title = C_LABELS.known_wrong;
    word.appendChild(flag);
    cell.appendChild(word);
    const why = document.createElement("small");
    why.className = "wrong-why";
    why.textContent = C_LABELS.known_wrong;
    cell.appendChild(why);
    return cell;
  }

  cell.appendChild(word);

  // The whole conditional is derived by LexicRo rather than served by the
  // underlying library. Marking it is what stops this tab reading as a thin
  // wrapper -- and it is the same discipline /analyze's per-token source
  // already applies.
  //
  // markSource is false when the whole card shares one source and has said so
  // once in its heading. Repeating it under all sixteen conditional forms
  // doubled every row's height to restate a fact the card already carried.
  if (markSource && entry.source === "derived") {
    const mark = document.createElement("small");
    mark.className = "derived";
    mark.textContent = derivedLabel || C_LABELS.derived_label;
    cell.appendChild(mark);
  }
  return cell;
}

function personRow(entry, markSource = true, derivedLabel = null, knownWrong = false) {
  const row = document.createElement("div");
  row.className = "crow";
  const pronoun = document.createElement("span");
  pronoun.className = "cpronoun";
  pronoun.textContent = entry.pronoun || "";
  row.append(pronoun, formCell(entry, markSource, derivedLabel, knownWrong));
  return row;
}

/** One tense, as a card.
 *
 * Absent persons are DROPPED rather than printed. `a ninge` used to render
 * "no such form" forty-six times across the paradigm, which is noise a reader
 * skips rather than information they take in -- the same fact is stated once,
 * for the whole verb, by absenceSummary(). A tense with nothing left says so
 * in a single line rather than becoming an empty card.
 *
 * This shows LESS than the API returns, deliberately. It does not show
 * anything DIFFERENT: nothing is invented, and no form is presented as
 * existing when it does not.
 */
function tenseBlock(name, entries, mood, wrongPronouns = null) {
  const block = document.createElement("div");
  block.className = "ctense";
  const heading = document.createElement("h4");
  heading.textContent = name;
  block.appendChild(heading);

  const present = entries.filter((e) => e.form !== NO_FORM);
  if (!present.length) {
    const none = document.createElement("p");
    none.className = "ctense-empty";
    none.textContent = C_LABELS.no_such_form;
    block.appendChild(none);
    return block;
  }

  // When every form in the card comes from the same place, say so once on the
  // card instead of once per row. Mixed cards fall back to per-form marks --
  // the claim is about a form, so it may not be summarised away when the forms
  // disagree.
  // On the negative imperative, say what "derived" MEANS rather than who did
  // it. That form is composed as `nu` + the infinitive, and for verbs whose
  // infinitive and third person singular are homographs -- `a merge`,
  // `a trece` -- it renders identically to the affirmative sitting beside it.
  // The affirmative is wrong there (verbecc#50: `merge` where `mergi`
  // belongs), so a reader sees a form they know is broken, sees the same word
  // repeated below it, and concludes both are broken -- while only the second
  // carries our name. Naming the rule instead of the author says the form was
  // built from the infinitive rather than copied from the broken neighbour,
  // which is exactly the misreading to prevent.
  //
  // `derived by LexicRo` stays on the condițional, where it is a real
  // contribution and nothing around it is wrong.
  const derivedLabel =
    mood === "imperativ" && name === "negativ"
      ? C_LABELS.derived_rule_negative
      : C_LABELS.derived_label;

  const allDerived = present.every((e) => e.source === "derived");
  if (allDerived) {
    const badge = document.createElement("small");
    badge.className = "derived cderived-all";
    badge.textContent = derivedLabel;
    heading.appendChild(badge);
  }

  for (const entry of present) {
    const wrong = !!wrongPronouns && wrongPronouns.has(entry.pronoun);
    block.appendChild(personRow(entry, !allDerived, derivedLabel, wrong));
  }
  return block;
}

function noteEl(note) {
  const el = document.createElement("p");
  el.className = "cnote";
  el.textContent = note.message;
  return el;
}

/** Which pronouns' forms this response says are wrong, per mood and tense.
 *
 * Read from the API, never guessed. The `imperative_known_errors` note
 * carries a `verbs` field naming the lemmas it is about, precisely so a
 * caller can mark the form instead of hoping a visitor reads the paragraph
 * above the table.
 *
 * Deliberately NOT computed from the data. The defect's signature -- a 2sg
 * imperative equal to the 3sg present -- is equally true of `a cânta` and
 * `a găsi`, which are correct, so deriving the set would put a red mark on
 * regular verbs. And it is not hardcoded here either: a copy of the list in
 * this repo is a second place to remember, and it would go stale silently the
 * day upstream fixes it. The API owns the disclosure; this renders it.
 *
 * Returns a map of "mood/tense" -> Set of pronouns.
 */
function knownWrongForms(data) {
  const wrong = new Map();
  const lemma = (data.verb || {}).infinitive;
  if (!lemma) return wrong;

  for (const note of data.notes || []) {
    if (note.code !== "imperative_known_errors") continue;
    if (!Array.isArray(note.verbs) || !note.verbs.includes(lemma)) continue;
    // The defect is the affirmative second person singular. The negative is
    // composed from the infinitive and is correct.
    wrong.set("imperativ/imperativ", new Set(["tu"]));
  }
  return wrong;
}

/** The `mood/tense` pairs the response reports as self-contradicting.
 *
 * `a ninge` says it has no first person in the present and then supplies
 * `eu am nins` in the compound tenses. Read from the API's own
 * `paradigm_contradiction` note (ADR-0029), never computed here.
 *
 * Marked per CARD, not per form. `a ninge` would otherwise take upwards of
 * thirty individual marks across five tenses -- a wall of red, and the same
 * mistake as the forty-six repetitions of "no such form" removed earlier.
 */
function contradictingTenses(data) {
  for (const note of data.notes || []) {
    if (note.code === "paradigm_contradiction" && Array.isArray(note.tenses)) {
      return new Set(note.tenses);
    }
  }
  return new Set();
}

function moodBlock(name, tenses, scopedNotes, wrongForms, contradicting) {
  const details = document.createElement("details");
  details.className = "cmood";
  details.open = OPEN_BY_DEFAULT.has(name);

  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.className = "cmood-name";
  title.textContent = name;
  summary.appendChild(title);

  const gloss = MOOD_GLOSSES[name];
  if (gloss) {
    const g = document.createElement("small");
    g.textContent = gloss;
    summary.appendChild(g);
  }
  details.appendChild(summary);

  // A note scoped to this mood is rendered INSIDE it, next to the forms it is
  // about. A visitor conjugating `a merge` must meet the imperative caveat
  // beside `merge`, not in a footer they scrolled past.
  for (const note of scopedNotes) details.appendChild(noteEl(note));

  // The tenses of THIS mood, packed responsively. The grid is deliberately
  // scoped inside the mood and never spans the whole result: if cards flowed
  // across mood boundaries, `condițional prezent` could land beside
  // `indicativ imperfect` with nothing marking that they are different moods
  // -- tidy to look at and grammatical nonsense.
  const gridOf = (names) => {
    const grid = document.createElement("div");
    grid.className = "ctenses";
    for (const n of names) {
      const card = tenseBlock(n, tenses[n], name, wrongForms.get(name + "/" + n));
      if (contradicting.has(name + "/" + n)) markContradicting(card);
      grid.appendChild(card);
    }
    return grid;
  };

  const names = orderedTenses(tenses);

  // A mood with more than a couple of tenses shows its present tense and puts
  // the rest one click away. In practice this fires only on `indicativ`, which
  // has nine -- the others have two or one -- so the rule is targeted without
  // being hardcoded to a mood name.
  //
  // The grid alone was enough on a desktop (five columns at 1440px) and did
  // nothing on a phone, where it collapses to one column and the full paradigm
  // ran to nearly nine screens. Breadth is worth showing where it is free, and
  // on a narrow screen it is not.
  if (names.length > 2) {
    const primary = names.includes("prezent") ? "prezent" : names[0];
    const rest = names.filter((n) => n !== primary);
    details.appendChild(gridOf([primary]));

    const more = document.createElement("details");
    more.className = "cmore";
    const summary = document.createElement("summary");
    // The count comes from the data, not from a translated string -- copy in
    // this project may not contain digits.
    summary.textContent = C_LABELS.other_tenses + " (" + rest.length + ")";
    more.appendChild(summary);
    more.appendChild(gridOf(rest));
    details.appendChild(more);
  } else {
    details.appendChild(gridOf(names));
  }
  return details;
}

/** One line on the card, rather than a mark on each of its forms.
 *
 * Says the verb disagrees with itself and points at the note. It does NOT say
 * which side is wrong, because the API does not: among the affected verbs
 * both readings occur -- `a curge` is genuinely third-person-only so its
 * compound is the error, while `a aporta` is an ordinary transitive whose
 * PRESENT is the error. Asserting either here would be a correction wearing
 * a disclosure's clothes.
 */
function markContradicting(card) {
  card.classList.add("is-contradicting");
  const why = document.createElement("p");
  why.className = "ccontradiction";
  why.textContent = C_LABELS.contradiction_card;
  card.insertBefore(why, card.querySelector(".crow"));
}

function render(data) {
  const target = document.getElementById("conjugate-result");
  target.replaceChildren();

  const notes = data.notes || [];
  target.appendChild(provenanceBanner(data.verb || {}));

  const resolved = resolvedNote(data);
  if (resolved) target.appendChild(resolved);

  const moods = data.moods || {};
  const wrongForms = knownWrongForms(data);
  const contradicting = contradictingTenses(data);
  for (const mood of orderedMoods(moods)) {
    target.appendChild(
      moodBlock(
        mood, moods[mood], notes.filter((n) => n.scope === mood), wrongForms, contradicting
      )
    );
  }

  // The general disclosure. Always rendered, never suppressed: an API consumer
  // can filter a caveat, a visitor cannot, because the visitor chose the input.
  const general = notes.filter((n) => n.scope === "all");
  if (general.length) {
    const box = document.createElement("section");
    box.className = "cnotes";
    const heading = document.createElement("h3");
    heading.textContent = C_LABELS.notes_heading;
    box.appendChild(heading);
    for (const note of general) box.appendChild(noteEl(note));
    target.appendChild(box);
  }
}

function renderError(message) {
  const target = document.getElementById("conjugate-result");
  target.replaceChildren();
  const el = document.createElement("p");
  el.className = "cerror";
  el.textContent = message;
  target.appendChild(el);
}

const conjugateForm = document.getElementById("conjugate-form");
if (conjugateForm) {
  conjugateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const verb = document.getElementById("verb").value.trim();
    if (!verb) return;
    try {
      render(await conjugateVerb(verb));
    } catch (err) {
      renderError(err.message);
    }
  });
}
