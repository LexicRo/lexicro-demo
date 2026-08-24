const LABELS = JSON.parse(document.getElementById("labels").textContent);
const GLOSSES = JSON.parse(document.getElementById("glosses").textContent);
const FAMILIES = JSON.parse(document.getElementById("families").textContent);

async function analyse(text) {
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "");
  return body;
}

/** Distinct readings only. The lexicon holds several entries sharing a lemma
 *  and UPOS but differing in features, and rendering only "lemma (UPOS)" makes
 *  those look like a duplication bug. */
function distinctCandidates(candidates) {
  const seen = new Set();
  const out = [];
  for (const c of candidates || []) {
    const key = c.lemma + String.fromCharCode(31) + c.upos;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(c);
  }
  return out;
}

function chip(name, value) {
  const el = document.createElement("span");
  el.className = "chip fam-" + (FAMILIES[name] || "other");
  const k = document.createElement("b");
  k.textContent = name;
  const v = document.createElement("i");
  v.textContent = value;
  el.append(k, v);

  // Plain-language gloss. Rendered as a real element rather than a title
  // attribute so it can be revealed on tap as well as hover -- a tooltip that
  // only answers to a mouse is invisible to half the people who open this page.
  const gloss = GLOSSES[name + "=" + value];
  if (gloss) {
    const g = document.createElement("small");
    g.textContent = gloss;
    el.appendChild(g);
    el.tabIndex = 0;
    el.classList.add("has-gloss");
  }
  return el;
}

function renderToken(token, focusForm) {
  const row = document.createElement("div");
  row.className = "token";
  if (focusForm && token.form.toLowerCase() === focusForm.toLowerCase()) {
    row.classList.add("is-focus");
  }

  const head = document.createElement("div");
  head.className = "token-head";

  const form = document.createElement("span");
  form.className = "t-form";
  form.textContent = token.form;

  const arrow = document.createElement("span");
  arrow.className = "t-arrow";
  arrow.textContent = "→";
  arrow.setAttribute("aria-hidden", "true");

  const lemma = document.createElement("span");
  lemma.className = "t-lemma";
  lemma.textContent = token.lemma;

  const upos = document.createElement("span");
  upos.className = "t-upos";
  upos.textContent = token.upos;

  head.append(form, arrow, lemma, upos);

  if (token.source) {
    const src = document.createElement("span");
    src.className = "t-source";
    src.textContent = token.source;
    head.appendChild(src);
  }
  row.appendChild(head);

  const feats = Object.entries(token.feats || {});
  if (feats.length) {
    const chips = document.createElement("div");
    chips.className = "chips";
    for (const [k, v] of feats) chips.appendChild(chip(k, v));
    row.appendChild(chips);
  }

  const candidates = distinctCandidates(token.candidates);
  if (candidates.length > 1) {
    const note = document.createElement("p");
    note.className = "candidates";
    note.textContent =
      LABELS.candidates + ": " +
      candidates.map((c) => `${c.lemma} (${c.upos})`).join(", ");
    row.appendChild(note);
  }
  return row;
}

function renderTokens(container, data, focusForm) {
  const list = document.createElement("div");
  list.className = "token-list";
  for (const sentence of data.sentences || []) {
    for (const token of sentence.tokens || []) {
      list.appendChild(renderToken(token, focusForm));
    }
  }
  container.replaceChildren(list);
  if (data.truncated) {
    const note = document.createElement("p");
    note.className = "truncated";
    note.textContent = LABELS.truncated;
    container.appendChild(note);
  }
}

for (const panel of document.querySelectorAll(".tokens")) {
  analyse(panel.dataset.text)
    .then((data) => {
      renderTokens(panel, data, panel.dataset.focus);
      panel.closest(".panel").classList.add("is-ready");
    })
    .catch(() => { panel.textContent = ""; });
}

const form = document.getElementById("analyse-form");
const input = document.getElementById("text");
const result = document.getElementById("result");
const toggle = document.getElementById("json-toggle");
const raw = document.getElementById("raw-json");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.textContent = "…";
  toggle.hidden = true;
  toggle.setAttribute("aria-pressed", "false");
  raw.hidden = true;
  try {
    const data = await analyse(input.value);
    renderTokens(result, data);
    raw.textContent = JSON.stringify(data, null, 2);
    toggle.hidden = false;
  } catch (error) {
    result.textContent = error.message;
  }
});

const toggleLabel = toggle.textContent;
toggle.addEventListener("click", () => {
  raw.hidden = !raw.hidden;
  toggle.setAttribute("aria-pressed", String(!raw.hidden));
  toggle.textContent = toggleLabel;
});

const counter = document.getElementById("counter");
input.addEventListener("input", () => {
  counter.textContent = `${input.value.length} / ${counter.dataset.max}`;
});

// Tap-to-reveal for the glosses. Hover handles pointers; this handles touch,
// where :hover either never fires or sticks after the tap.
document.addEventListener("click", (event) => {
  const el = event.target.closest(".has-gloss");
  document.querySelectorAll(".chip.is-open").forEach((c) => {
    if (c !== el) c.classList.remove("is-open");
  });
  if (el) el.classList.toggle("is-open");
});
