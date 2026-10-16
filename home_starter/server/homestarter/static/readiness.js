// Conditional interviews persist plans. Credentials and configuration stay in HA/MA.
export function blankChoice() { return { intent: "", sources: [], screens: [], answers: {}, permissions: {} }; }

export function initReadiness({ h, api, navigateHA }) {
  const root = document.getElementById("readiness-body"), status = document.getElementById("readiness-status");
  let data, draft, dirty = false, busy = false, reading = 0;
  const opened = new Set();
  const button = (label, action, disabled = false) => h("button", { type: "button", class: "btn ghost", onclick: action, disabled }, label);
  const changed = () => { dirty = true; root.dataset.dirty = "true"; status.textContent = "Unsaved readiness choices. Save before verifying or generating a screen."; root.querySelectorAll("button").forEach(node => { if (node.textContent.startsWith("Verify ")) node.disabled = true; }); };
  const field = (label, control) => h("label", { class: "screen-field" }, h("span", {}, label), control);
  const select = (label, options, value, change) => h("select", { "aria-label": label, onchange: e => { change(e.target.value); changed(); } }, options.map(([id, title]) => h("option", { value: id, selected: value === id }, title)));
  function checks(label, options, values, change) {
    let selected = values;
    return h("fieldset", {}, h("legend", {}, label), options.map(([id, title]) => h("label", { class: "checklist-row" },
      h("input", { type: "checkbox", checked: selected.includes(id), onchange: e => { selected = e.target.checked ? [...new Set([...selected, id])] : selected.filter(v => v !== id); change(selected); changed(); } }), title)));
  }
  function route(path) {
    if (!path.startsWith("#")) { navigateHA(path); return; }
    const node = document.querySelector(path);
    for (let parent = node; parent; parent = parent.parentElement) if (parent.tagName === "DETAILS") parent.open = true;
    if (path === "#music") document.dispatchEvent(new CustomEvent("home-starter-music"));
    node?.scrollIntoView({ block: "start" });
  }
  function memberForm() {
    return data.people.map(person => {
      const current = draft.members[person.id] || { kind: person.audience === "adult" ? "adult" : "", rooms: [], devices: [], presence: [], access: "later" };
      const update = (key, value) => { current[key] = value; draft.members[person.id] = current; };
      return h("fieldset", {}, h("legend", {}, person.name),
        field("Household role", select("Household role for " + person.name, [["", "Choose adult or child"], ["adult", "Adult"], ["child", "Child"]], current.kind, v => update("kind", v))),
        field("Home Assistant access", select("HA access for " + person.name, [["later", "Review later"], ["yes", "Needs access — manage in HA"], ["no", "No HA account needed"]], current.access, v => update("access", v))),
        checks("Rooms for " + person.name, data.areas.map(a => [a.area_id, a.name]), current.rooms, v => update("rooms", v)),
        checks("Personal devices for " + person.name, data.devices.map(d => [d.id, d.name]), current.devices, v => update("devices", v)),
        checks("Presence sources for " + person.name, data.rows.find(r => r.id === "presence").sources.map(s => [s.id, s.name]), current.presence, v => update("presence", v)));
    });
  }
  function capabilityForm(row) {
    if(row.provider_service && row.provider_configured)return h("p",{},"The Council waste service is confirmed. Manage it in Waste collection. Previous calendar-source decisions remain saved separately.");
    const choice = draft.choices[row.id] || blankChoice();
    const update = (key, value) => { choice[key] = value; draft.choices[row.id] = choice; };
    return h("div", {},
      field("Your decision", select("Decision for " + row.title, [["", "Choose when relevant"], ["wanted", "Wanted — set up and verify"], ["later", "Not now"], ["not_wanted", "Not wanted"]], choice.intent, v => { if (v) update("intent", v); else delete draft.choices[row.id]; render(); })),
      row.provider_service ? h("p",{},"Check and confirm the Council service in Waste collection. Previous calendar-source choices are preserved; no synthetic calendar events are created.") : choice.intent === "wanted" && h("div", {},
        h("p", { class: "small muted" }, "Sources and displays are choices, not proof of working configuration. Existing dashboards change only after a reviewed publication."),
        checks("Sources for " + row.title, row.sources.map(s => [s.id, s.name + (s.available ? "" : " · unavailable")]), choice.sources, v => update("sources", v)),
        row.id === "waste" && h("p", {}, "Choose one source with a dated collection event; a calendar name alone is insufficient."),
        row.id === "calendars" && h("p", {}, "Choose the individual calendars beneath your consolidated account. Map their household/person purposes in service setup."),
        checks("Displays for " + row.title, data.screens.map(s => [s.id, s.name]), choice.screens, v => update("screens", v)),
        Object.entries(data.answer_options[row.id] || {}).map(([key, options]) => {
          const label = key.replaceAll("_", " ") + " for " + row.title;
          const set = v => { choice.answers[key] = v; update("answers", choice.answers); };
          return ["accounts", "groups", "service", "plan"].includes(key)
            ? field(label, select(label, [["", "Choose"], ...options.map(v => [v, v.replaceAll("_", " ")])], choice.answers[key]?.[0] || "", v => set(v ? [v] : [])))
            : checks(label, options.map(v => [v, v.replaceAll("_", " ")]), choice.answers[key] || [], set);
        }),
        row.id === "communications" && h("div", {}, h("p", {}, "These are a call plan only. Configure and verify permissions in the calling service; no extension or calling permission is enabled here."),
          data.people.map(person => checks("Allowed internal destinations for " + person.name, data.people.filter(p => p.id !== person.id).map(p => [p.id, p.name]), choice.permissions[person.id] || [], v => { choice.permissions[person.id] = v; update("permissions", choice.permissions); }))),
        ["calendars", "waste"].includes(row.id) && button("Verify " + row.title + " source", () => verify(row.id), busy || dirty),
        !["calendars", "waste"].includes(row.id) && h("p", { class: "small muted" }, "End-to-end testing is not automated here. Use the linked service; this item remains incomplete until supported verification exists.")));
  }
  function detail(row) {
    const content = h("div", {});
    const intent = draft.choices[row.id]?.intent;
    const questions = intent ? (intent === "wanted" ? row.guide : []) : row.questions;
    const fill = () => content.replaceChildren(h("div", {},
        questions.map(q => h("p", {}, q)),
        button("Continue " + row.title + " in " + (row.route.startsWith("#") ? "Home Starter" : "Home Assistant"), () => route(row.route)),
        row.id === "household" ? memberForm() : row.id === "rooms" ? data.room_devices.map(device => field(device.name,
          select("Unassigned device " + device.name, [["", "Unresolved — assign a room in Your home"], ["hidden", "Hide from household screens"], ["ignored", "Explicitly ignore"]], draft.devices[device.id] || "", v => { if (v) draft.devices[device.id] = v; else delete draft.devices[device.id]; }))) : row.id === "displays" ? h("p", {}, "Wall is display-only. Other profiles are interactive. Membership must be saved before choosing a personal screen.") : capabilityForm(row)));
    const node = h("details", { id: "readiness-" + row.id, open: opened.has(row.id), ontoggle: e => {
      if (e.target.open) { opened.add(row.id); if (!content.childElementCount) fill(); }
      else opened.delete(row.id);
    } }, h("summary", {}, row.title + " — " + row.status), content);
    if (opened.has(row.id)) fill();
    return node;
  }
  function render() {
    if (!data) return;
    root.replaceChildren(
      h("p", { class: "small muted" }, "Only relevant questions are offered. Open another item to express interest. Not wanted and Not now are saved decisions. No credentials belong in this page."),
      ...data.rows.map(detail),
      data.service_checks?.length ? h("section", {}, h("h3", {}, "Household services"),
        button("Set up accounts and libraries", () => route("#household-services")),
        ...data.service_checks.map(row => h("p", {}, h("strong", {}, row.name + " — " + row.status),
          h("span", {class:"small muted"}, " · " + row.detail), " ", button("Review " + row.name, () => route(row.route))))) : null,
      button("Save readiness choices", save, busy),
    );
    root.querySelectorAll("input, select, button").forEach(node => { if (busy) node.disabled = true; });
  }
  async function refresh() {
    if (dirty) { status.textContent = "Save readiness choices before refreshing. Your unsaved choices are retained."; return; }
    const request = ++reading;
    try { const result = await api("api/readiness"); if (request !== reading || dirty) return; data = result; draft = structuredClone(data.state); status.textContent = data.inventory_complete ? "Saved decisions loaded. Review incomplete items when useful." : "Inventory incomplete. Previous decisions are preserved; verification is paused."; render(); }
    catch (error) { status.textContent = error.message; }
  }
  async function save() {
    if (busy) return;
    busy = true; render();
    try {
      const { revision, epoch, choices, members, devices } = draft;
      await api("api/readiness/save", { method: "POST", body: JSON.stringify({ revision, epoch, choices, members, devices }) });
      dirty = false; root.dataset.dirty = "false"; busy = false; await refresh();
      document.dispatchEvent(new CustomEvent("home-starter-readiness-saved"));
      document.dispatchEvent(new CustomEvent("home-starter-saved"));
      document.dispatchEvent(new CustomEvent("home-starter-refresh-screens"));
    } catch (error) { busy = false; render(); status.textContent = error.message; }
  }
  async function verify(capability) {
    if (busy || dirty) return;
    busy = true; render();
    try { await api("api/readiness/verify", { method: "POST", body: JSON.stringify({ revision: draft.revision, epoch: draft.epoch, capability, confirm: true }) }); busy = false; await refresh(); }
    catch (error) { busy = false; render(); status.textContent = error.message; }
  }
  document.getElementById("readiness-check").addEventListener("click", refresh);
  document.addEventListener("home-starter-saved", refresh);
  document.addEventListener("home-starter-services-saved", refresh);
  refresh();
}
