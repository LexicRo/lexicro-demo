/* Tab selection, and nothing else.
 *
 * Conjugate is never the landing state: an absent or unrecognised hash
 * selects Analyse. That is ADR-0025 section 4's subordination expressed in
 * behaviour rather than in styling -- placement is what implies importance,
 * so this file is where the decision actually lives.
 */
const TABS = Array.from(document.querySelectorAll(".tab"));
const PANES = { analyse: "pane-analyse", conjugate: "pane-conjugate" };

function select(name) {
  if (!Object.prototype.hasOwnProperty.call(PANES, name)) name = "analyse";
  for (const tab of TABS) {
    const chosen = tab.dataset.pane === name;
    tab.classList.toggle("is-selected", chosen);
    tab.setAttribute("aria-selected", chosen ? "true" : "false");
  }
  for (const [pane, id] of Object.entries(PANES)) {
    const el = document.getElementById(id);
    if (el) el.hidden = pane !== name;
  }
}

for (const tab of TABS) {
  tab.addEventListener("click", () => {
    const name = tab.dataset.pane;
    // replaceState, not a hash assignment: pushing a history entry per tab
    // click makes Back walk the visitor through their own clicking instead of
    // leaving the page.
    history.replaceState(null, "", name === "analyse" ? "#" : "#" + name);
    select(name);
  });
}

select(location.hash.replace("#", ""));
