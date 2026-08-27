/* Page chrome: tab selection, and collapsing the hero once the visitor
 * engages.
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


/* The hero is roughly two screens and used to be permanent, so a visitor
 * reached the thing they came to try only after scrolling past the argument
 * for it. It now collapses on the first submit of EITHER form.
 *
 * On submit, deliberately not on scroll. A scroll-triggered collapse moves
 * the page under someone who is reading and fights anyone who scrolled back
 * up on purpose; submitting is a moment the visitor caused, so the change
 * reads as a response rather than the page misbehaving.
 *
 * Never on load -- the hero is the argument for the product and a first-time
 * visitor has to meet it -- and never persisted across page loads, for the
 * same reason.
 *
 * The listeners live here rather than in app.js and conjugate.js so that
 * neither of those has to know the hero exists.
 */
const HERO = document.getElementById("hero");
const HERO_TOGGLE = document.getElementById("hero-toggle");

function setHeroCollapsed(collapsed) {
  if (!HERO || !HERO_TOGGLE) return;
  HERO.hidden = collapsed;
  HERO_TOGGLE.hidden = !collapsed;
  HERO_TOGGLE.setAttribute("aria-expanded", collapsed ? "false" : "true");
  HERO_TOGGLE.textContent = collapsed
    ? HERO_TOGGLE.dataset.show
    : HERO_TOGGLE.dataset.hide;
}

if (HERO_TOGGLE) {
  HERO_TOGGLE.addEventListener("click", () => setHeroCollapsed(HERO.hidden === false));
}

for (const id of ["analyse-form", "conjugate-form"]) {
  const f = document.getElementById(id);
  // Collapse BEFORE the result renders, so the visitor sees one layout change
  // rather than two. Fires on intent, not on success: a failed request still
  // means they came here to use the thing.
  //
  // once: true is what makes the toggle theirs afterwards. Without it, a
  // visitor who deliberately reopened the examples would have them yanked
  // away again on their next submit, which is the page arguing with them.
  if (f) f.addEventListener("submit", () => setHeroCollapsed(true), { once: true });
}
