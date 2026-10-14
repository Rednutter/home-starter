// Subsequent visits inspect persisted setup. No launch action creates HA resources.
export function launchMode(data) {
  if (!data || typeof data.first_run !== "boolean") return "unknown";
  return data.first_run ? "first-run" : "existing";
}

export async function initInstallation({ h, api, navigateHA }) {
  const root = document.getElementById("installation-body");
  const status = document.getElementById("installation-status");
  const changes = document.getElementById("changes-body");
  const setup = document.getElementById("review-setup");
  for (const id of ["home-readiness", "fresh-batteries", "useful-things", "forgotten", "your-home"]) {
    const section = document.getElementById(id); section.hidden = false; setup.append(section);
  }
  let data = null, busy = false;
  const replace = (node, ...children) => node.replaceChildren(...children.filter(child => child != null && child !== false));
  const button = (label, action, disabled = false) => h("button", { type: "button", class: "btn ghost", onclick: action, disabled }, label);
  const labels = { published: "Published · matches saved version", unpublished: "Not published", missing: "Published dashboard missing",
    external_edits: "Edited in HA · protected", untracked: "Address already in use · protected", unavailable: "Readback unavailable" };
  const explanations = { new: "New source; review before extending your screens.", missing: "Missing from a complete scan; nothing was removed.",
    renamed: "Registry identity retained. Review old names/references in setup; controls were not retargeted.",
    capability: "Advertised capabilities changed; review a new preview when ready.", connection: "Connection metadata changed; inspect the existing integration.",
    changed: "Availability or configuration changed; review the current inventory." };
  function render() {
    const mode = launchMode(data);
    if (mode === "unknown") return;
    const previous = document.body.dataset.setupState;
    document.body.dataset.setupState = mode;
    setup.hidden = false;
    if (previous !== mode) setup.open = mode === "first-run";
    document.querySelector(".house-nav").replaceChildren(...[
      ["this-house", "This House"], ["house-status", "House status"], ["home-readiness", "Home Readiness"], ["house-changes", "New / changed things"], ["surfaces", "Screens"],
      ["this-house-people", "People"], ["music", "Music"], ["house-climate", "Climate"],
      ["household-activities", "Activities"], ["review-setup", "Review setup"],
    ].map(([id, label]) => h("a", { href: "#" + id, onclick: () => {
      const target = document.getElementById(id);
      for (let node = target; node; node = node.parentElement) if (node.tagName === "DETAILS") node.open = true;
      if (id === "music") document.dispatchEvent(new CustomEvent("home-starter-music"));
    } }, label)));
    const problem = !data.inventory_complete || data.unavailable.length || data.changes.length ||
      data.screens.some(s => s.status !== "published") || !data.music.verified;
    status.textContent = mode === "first-run" ? "No saved setup yet. Review the existing house, then finish initial review when ready."
      : problem ? "Saved setup loaded. Review the checks below; nothing was rebuilt." : "Saved setup loaded. Current checks are healthy.";
    const climate = data.screens.find(s => s.profile === "specialist" && s.status === "published") ||
      data.screens.find(s => ["phone", "tablet"].includes(s.profile) && s.status === "published");
    replace(root,
      h("p", {}, `${data.counts.people} saved screen profiles · ${data.counts.screens} screens · ${data.counts.activities} activity rules`),
      !data.inventory_complete && h("p", { class: "warn" }, "Inventory is incomplete. The last complete baseline is preserved."),
      data.baseline_created && h("p", { class: "small muted" }, "First comparison baseline recorded. Future launches show differences without rebuilding setup."),
      h("h3", {}, "Screens"),
      ...data.screens.map(s => h("div", { class: "screen-row" }, h("strong", {}, s.name), h("span", {}, labels[s.status]),
        ["published", "external_edits"].includes(s.status) && button("Open " + s.name, () => navigateHA("/" + s.url_path + "/home")))),
      !data.screens.length && h("p", { class: "muted" }, "No screens configured. Add one when useful; existing HA dashboards stay in place."),
      h("h3", {}, "Music"), h("p", {}, data.music.title || "Music check unavailable"),
      h("h3", { id: "house-climate" }, "Climate"),
      h("p", {}, data.climate_available ? "Existing climate capabilities are available for screen previews." : "No available climate source in this scan."),
      climate && button("Open Climate", () => navigateHA("/" + climate.url_path + "/climate")),
      h("h3", {}, "Activities"), h("p", {}, data.counts.activities ? "Saved explicit completion rules are retained." : "No completion rules configured. Add only documented source transitions."),
      data.unavailable.length > 0 && h("details", {}, h("summary", {}, `Unavailable or failing sources (${data.unavailable.length})`),
        h("ul", {}, data.unavailable.map(s => h("li", {}, `${s.label} · ${s.kind}`)))),
      mode === "first-run" && button("Finish initial review", () => action("complete", data.revision), busy),
    );
    replace(changes,
      !data.changes.length ? h("p", {}, "No pending differences from the previous complete inventory.") :
        h("ul", { class: "plain" }, data.changes.map(c => h("li", {}, h("strong", {}, `${c.label} · ${c.category}`),
          h("p", { class: "small muted" }, explanations[c.category]), c.category === "renamed" && c.before?.entity_id && c.after?.entity_id &&
          h("p", { class: "small" }, `${c.before.entity_id} → ${c.after.entity_id}`)))),
      data.changes.length > 0 && button("Mark these differences reviewed", () => action("review", data.observation_revision), busy || !data.inventory_complete),
    );
    document.getElementById("reset-setup")?.remove();
    const confirmation = h("input", { "aria-label": "Reset confirmation", autocomplete: "off", placeholder: "RESET HOME STARTER" });
    const reset = button("Reset Home Starter setup", () => action("reset", data.revision, confirmation.value), true);
    confirmation.addEventListener("input", () => { reset.disabled = busy || confirmation.value !== "RESET HOME STARTER"; });
    setup.append(h("details", { id: "reset-setup" }, h("summary", {}, "Reset Home Starter setup"),
      h("p", {}, "Clears saved screen profiles, preferences, names, activity rules, Home Readiness decisions and the comparison baseline. A local recovery copy is retained. " +
        "HA dashboards, people, devices, entities and integrations stay in place. This House confirmations, publication ownership and activity history are retained for protection and recovery."),
      h("label", { class: "screen-field" }, h("span", {}, "Type RESET HOME STARTER to confirm"), confirmation), reset));
  }
  async function action(name, revision, acknowledgement) {
    if (busy) return;
    if (name === "complete" && document.getElementById("surfaces-body").dataset.dirty === "true") {
      status.textContent = "Save your household changes before finishing initial review."; return;
    }
    busy = true; render();
    try {
      await api("api/installation/" + name, { method: "POST", body: JSON.stringify({ confirm: true, revision,
        ...(name === "reset" ? { acknowledgement } : {}) }) });
      if (name === "reset" || name === "complete") { location.reload(); return; }
      busy = false;
      await refresh();
    } catch (error) { busy = false; render(); status.textContent = error.message; }
    finally { busy = false; }
  }
  async function refresh() {
    try { data = await api("api/installation"); render(); }
    catch (_error) { status.textContent = "Could not safely read existing setup. Onboarding was not restarted. Check access or restore runtime data, then refresh."; }
  }
  document.getElementById("installation-check").addEventListener("click", refresh);
  document.addEventListener("home-starter-saved", refresh);
  await refresh();
  return refresh;
}
