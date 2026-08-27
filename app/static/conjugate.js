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
  el.textContent = predicted ? C_LABELS.prov_predicted : C_LABELS.prov_template;
  if (predicted) el.setAttribute("role", "status");
  return el;
}

function formCell(entry, markSource = true) {
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
    mark.textContent = C_LABELS.derived_label;
    cell.appendChild(mark);
  }
  return cell;
}

function personRow(entry, markSource = true) {
  const row = document.createElement("div");
  row.className = "crow";
  const pronoun = document.createElement("span");
  pronoun.className = "cpronoun";
  pronoun.textContent = entry.pronoun || "";
  row.append(pronoun, formCell(entry, markSource));
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
function tenseBlock(name, entries) {
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
  const allDerived = present.every((e) => e.source === "derived");
  if (allDerived) {
    const badge = document.createElement("small");
    badge.className = "derived cderived-all";
    badge.textContent = C_LABELS.derived_label;
    heading.appendChild(badge);
  }

  for (const entry of present) block.appendChild(personRow(entry, !allDerived));
  return block;
}

function noteEl(note) {
  const el = document.createElement("p");
  el.className = "cnote";
  el.textContent = note.message;
  return el;
}

function moodBlock(name, tenses, scopedNotes) {
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
    for (const name of names) grid.appendChild(tenseBlock(name, tenses[name]));
    return grid;
  };

  const names = Object.keys(tenses);

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

function render(data) {
  const target = document.getElementById("conjugate-result");
  target.replaceChildren();

  const notes = data.notes || [];
  target.appendChild(provenanceBanner(data.verb || {}));

  const moods = data.moods || {};
  for (const mood of orderedMoods(moods)) {
    target.appendChild(moodBlock(mood, moods[mood], notes.filter((n) => n.scope === mood)));
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
