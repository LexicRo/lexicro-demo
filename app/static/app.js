const LABELS = JSON.parse(document.getElementById("labels").textContent);

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

function renderTokens(container, data) {
  const table = document.createElement("table");
  const head = table.insertRow();
  for (const key of ["form", "lemma", "upos", "feats", "source"]) {
    const th = document.createElement("th");
    th.textContent = LABELS[key];
    head.appendChild(th);
  }
  for (const sentence of data.sentences || []) {
    for (const token of sentence.tokens || []) {
      const row = table.insertRow();
      row.insertCell().textContent = token.form;
      row.insertCell().textContent = token.lemma;
      row.insertCell().textContent = token.upos;
      row.insertCell().textContent = Object.entries(token.feats || {})
        .map(([k, v]) => `${k}=${v}`).join("|");
      row.insertCell().textContent = token.source || "";
      if (token.candidates && token.candidates.length > 1) {
        const note = table.insertRow().insertCell();
        note.colSpan = 5;
        note.className = "candidates";
        note.textContent = LABELS.candidates + ": " +
          token.candidates.map((c) => `${c.lemma} (${c.upos})`).join(", ");
      }
    }
  }
  container.replaceChildren(table);
  if (data.truncated) {
    const note = document.createElement("p");
    note.className = "truncated";
    note.textContent = LABELS.truncated;
    container.appendChild(note);
  }
}

for (const panel of document.querySelectorAll(".tokens")) {
  analyse(panel.dataset.text)
    .then((data) => renderTokens(panel, data))
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

toggle.addEventListener("click", () => { raw.hidden = !raw.hidden; });

const counter = document.getElementById("counter");
input.addEventListener("input", () => {
  counter.textContent = `${input.value.length} / ${counter.dataset.max}`;
});
