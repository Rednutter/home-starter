// Screen setup is administration. Generated household screens live in native HA.
export function newItemId(prefix, random = crypto) {
  // getRandomValues works on ordinary HTTP HA ingress; randomUUID requires HTTPS.
  const bytes = random.getRandomValues(new Uint8Array(8));
  return `${prefix}-${[...bytes].map(value => value.toString(16).padStart(2, "0")).join("")}`;
}

export function moveItem(order, id, direction) {
  const result = [...order], at = result.indexOf(id), next = at + direction;
  if (at < 0 || next < 0 || next >= result.length) return result;
  [result[at], result[next]] = [result[next], result[at]];
  return result;
}

export function initSurfaces({ h, api, navigateHA }) {
  const root = document.getElementById("surfaces-body"), status = document.getElementById("surfaces-status");
  let data = null, draft = null, dirty = false, busy = false, preview = null, selected = "", owner = "", search = "", reloadRequested = false, editingPeople = false;
  const button = (label, action, primary = false, disabled = false) => h("button", { type: "button", class: `btn ${primary ? "primary" : "ghost"}`, disabled, onclick: action }, label);
  const field = (label, control) => h("label", { class: "screen-field" }, h("span", {}, label), control);
  const input = (label, value = "", attrs = {}) => h("input", { "aria-label": label, value, maxlength: 80, ...attrs });
  const select = (label, options, value, onchange) => h("select", { "aria-label": label, onchange }, options.map(([id, name]) => h("option", { value: id, selected: id === value }, name)));
  const id = newItemId;
  const changed = () => {
    root.dataset.dirty = "true";
    dirty = true; preview = null; status.textContent = "Unsaved changes. Save before generating a screen.";
    root.querySelectorAll('button').forEach(el => {
      if (el.textContent === "Save household settings") el.disabled = busy || !data.inventory_complete;
      if (el.textContent === "Generate screen") el.disabled = true;
    });
    root.querySelector('#screen-preview')?.remove();
  };
  const setStatus = (message, error = false) => { status.textContent = message; status.className = error ? "error" : "muted"; };
  function fail(error) { setStatus(error.message || String(error), true); status.focus(); }
  async function load() {
    if (busy) return;
    busy = true;
    try {
      data = await api("api/household"); draft = structuredClone(data.household); dirty = false; preview = null;
      root.dataset.dirty = "false";
      if (!draft.surfaces.some(s => s.id === selected)) selected = draft.surfaces[0]?.id || "";
      setStatus(data.inventory_complete ? (draft.configured ? "Saved household loaded. Review or extend the existing screens." : "Choose who uses the house and where each screen lives.") : "The house scan is incomplete. Refresh before saving or publishing screens.");
      render();
    } catch (error) { fail(error); } finally { busy = false; render(); if (reloadRequested) { reloadRequested = false; load(); } }
  }
  async function save() {
    if (busy) return;
    busy = true; render();
    try { const saved = await api("api/household", { method: "POST", body: JSON.stringify(draft) }); draft = saved.household; dirty = false; root.dataset.dirty = "false"; preview = null; setStatus("Household settings saved on this Home Assistant."); document.dispatchEvent(new CustomEvent("home-starter-saved")); }
    catch (error) { fail(error); } finally { busy = false; render(); }
  }
  async function generate() {
    if (busy || dirty || !selected) return;
    if (document.getElementById("readiness-body").dataset.dirty === "true") { setStatus("Save your Home Readiness choices before generating a screen.", true); return; }
    busy = true; preview = null; render(); setStatus("Assembling this screen from your house…");
    try { preview = await api(`api/surfaces/${encodeURIComponent(selected)}/preview`); setStatus("Preview ready. Review it before adding or updating the dashboard."); }
    catch (error) { fail(error); } finally { busy = false; render(); document.getElementById("screen-preview")?.focus(); }
  }
  async function publish() {
    if (busy || !preview || dirty) return;
    busy = true; render();
    try {
      const result = await api(`api/surfaces/${encodeURIComponent(selected)}/publish`, { method: "POST", body: JSON.stringify({ preview_token: preview.preview_token, confirm: true }) });
      preview.published = result; preview.preview_token = null; setStatus("Dashboard saved and read back successfully. Open it to check the controls in Home Assistant.");
    } catch (error) { fail(error); } finally { busy = false; render(); status.focus(); }
  }
  function renderPeople() {
    const name = input("Person name", "", { placeholder: "Name" });
    const audience = select("Person audience", [["everyone", "Everyone"], ["adult", "Adult"]], "everyone");
    return h("details", { id: "household-people", open: editingPeople || !draft.people.length }, h("summary", {}, "Screen profiles"),
      h("p", { class: "small muted" }, "Saved screen preferences. Household members and presence trackers are reviewed in This House; account access stays in Home Assistant."),
      draft.people.map(p => h("div", { class: "screen-row" }, h("strong", {}, p.name), h("span", { class: "muted" }, p.audience === "adult" ? "Adult" : "Everyone"))),
      h("div", { class: "screen-fields" }, field("Name", name), field("Audience", audience)),
      button("Add screen profile", () => { if (!name.value.trim()) { name.focus(); return; } editingPeople = true; draft.people.push({ id: id("person"), name: name.value.trim(), audience: audience.value }); changed(); render(); }));
  }
  function renderAddScreen() {
    const name = input("Screen name", "", { placeholder: "e.g. Kitchen tablet" });
    const profile = select("Screen type", Object.entries(data.profiles), "phone");
    const person = select("Screen person", [["", "Shared — no personal preferences"], ...draft.people.map(p => [p.id, p.name])], "");
    const area = select("Screen room", [["", "Whole house"], ...data.areas.map(a => [a.area_id, a.name])], "");
    const audience = select("Screen audience", [["everyone", "Everyone"], ["adult", "Adults"]], "everyone");
    return h("details", { open: !draft.surfaces.length }, h("summary", {}, "Add a screen"),
      h("div", { class: "screen-fields" }, field("Name", name), field("Type", profile), field("Person", person), field("Room", area), field("Audience for shared screens", audience)),
      h("p", { class: "small muted" }, "Choose a room for a specialist, kitchen or bedside screen. Its local controls take priority."),
      button("Add screen", () => { if (!name.value.trim()) { name.focus(); return; } const s = { id: id("screen"), name: name.value.trim(), profile: profile.value, person_id: person.value || null, area_id: area.value || null, audience: audience.value }; draft.surfaces.push(s); selected = s.id; changed(); render(); }));
  }
  function renderScreenSettings(surface) {
    if (!surface) return null;
    const set = (key, value) => { surface[key] = value || null; changed(); };
    return h("details", {}, h("summary", {}, "Screen settings"), h("div", { class: "screen-fields" },
      field("Name", input("Saved screen name", surface.name, { onchange: e => { if (e.target.value.trim()) set("name", e.target.value.trim()); } })),
      field("Type", select("Saved screen type", Object.entries(data.profiles), surface.profile, e => set("profile", e.target.value))),
      field("Person", select("Saved screen person", [["", "Shared"], ...draft.people.map(p => [p.id, p.name])], surface.person_id || "", e => set("person_id", e.target.value))),
      field("Room", select("Saved screen room", [["", "Whole house"], ...data.areas.map(a => [a.area_id, a.name])], surface.area_id || "", e => set("area_id", e.target.value))),
      field("Audience", select("Saved screen audience", [["everyone", "Everyone"], ["adult", "Adults"]], surface.audience, e => set("audience", e.target.value))),
      surface.profile === "specialist" && field("Panel presentation", select("Panel presentation", [["normal","Standard HA navigation"],["kiosk","Kiosk — Settings restores navigation"]], surface.kiosk ? "kiosk" : "normal", e => { if(e.target.value === "kiosk") surface.kiosk=true; else delete surface.kiosk; changed(); }))));
  }
  function renderPreferences(surface) {
    if (!surface) return null;
    const owners = [[`surface:${surface.id}`, `This screen: ${surface.name}`], ...draft.people.map(p => [p.id, `Person: ${p.name}`])];
    if (!owners.some(([key]) => key === owner)) owner = owners[0][0];
    const pref = draft.preferences[owner] || { pin: [], hide: [], order: [] };
    let items = [
      ...data.areas.map(a => ({ id: `room:${a.area_id}`, name: a.name, reason: "Room", level: 2 })),
      ...data.items.filter(i => i.level < 5 && i.usable),
    ];
    const allIds = items.map(i => i.id);
    const ordered = [...pref.order.filter(i => allIds.includes(i)), ...allIds.filter(i => !pref.order.includes(i))];
    items.sort((a, b) => ordered.indexOf(a.id) - ordered.indexOf(b.id));
    items = items.filter(i => i.name.toLowerCase().includes(search.toLowerCase()));
    const mutate = (item, key, checked) => {
      const current = draft.preferences[owner] ||= { pin: [], hide: [], order: [] };
      current[key] = checked ? [...new Set([...current[key], item.id])] : current[key].filter(i => i !== item.id);
      changed();
    };
    const reorder = (item, direction) => {
      const latest = draft.preferences[owner] || pref;
      draft.preferences[owner] = { ...latest, order: moveItem(ordered, item.id, direction) };
      changed(); render(); document.querySelector('.screen-preferences').open = true;
      const label = `Move ${item.name} ${direction === -1 ? "up" : "down"}`;
      const opposite = `Move ${item.name} ${direction === -1 ? "down" : "up"}`;
      const buttons = [...root.querySelectorAll('button')];
      (buttons.find(b => b.textContent === label && !b.disabled) || buttons.find(b => b.textContent === opposite && !b.disabled))?.focus();
    };
    const query = input("Find a room or control", search, { type: "search", placeholder: "Find a room or control", oninput: event => { search = event.target.value; const start = event.target.selectionStart; render(); const next = document.getElementById("screen-item-search"); next.focus(); next.setSelectionRange(start, start); } });
    query.id = "screen-item-search";
    return h("details", { class: "screen-preferences" }, h("summary", {}, "Pin, hide and reorder"),
      h("p", { class: "small muted" }, "Person choices follow that person across screens. Screen choices stay with this display. Safety alerts cannot be hidden; preferences never override screen suitability or account permissions."),
      field("Preferences for", select("Preferences for", owners, owner, event => { owner = event.target.value; render(); document.querySelector('.screen-preferences').open = true; })), query,
      h("div", { class: "preference-list" }, items.map(item => h("div", { class: "screen-item" },
        h("span", {}, h("strong", {}, item.name), h("span", { class: "small muted screen-reason" }, item.reason)),
        h("label", {}, h("input", { type: "checkbox", checked: pref.pin.includes(item.id), "aria-label": `Pin ${item.name}`, onchange: e => mutate(item, "pin", e.target.checked) }), " Pin"),
        h("label", {}, h("input", { type: "checkbox", checked: pref.hide.includes(item.id), disabled: item.level === 0, "aria-label": `Hide ${item.name}`, onchange: e => mutate(item, "hide", e.target.checked) }), " Hide"),
        button(`Move ${item.name} up`, () => reorder(item, -1), false, ordered.indexOf(item.id) === 0),
        button(`Move ${item.name} down`, () => reorder(item, 1), false, ordered.indexOf(item.id) === ordered.length - 1)))),
      h("p", { class: "small muted" }, "Save, then generate again to apply these choices."));
  }
  function renderNames() {
    const candidates = data.items.filter(i => i.level < 5 || ["scene", "script", "switch", "input_boolean"].includes(i.domain));
    const choice = select("Household control to name", candidates.map(i => [i.id, i.name]), candidates[0]?.id || "", () => {
      const current = candidates.find(i => i.id === choice.value);
      const override = draft.overrides[current?.id] || {};
      name.value = override.name || current?.name || "";
      include.checked = current?.level === 0 || (override.include ?? (current?.level < 5));
      include.disabled = current?.level === 0;
    });
    const name = input("Household control name", "", { placeholder: "e.g. Goodnight" });
    const first = candidates[0];
    const include = h("input", { type: "checkbox", "aria-label": "Include this control",
      checked: first?.level === 0 || (draft.overrides[first?.id]?.include ?? (first?.level < 5)), disabled: first?.level === 0 });
    return h("details", {}, h("summary", {}, "Household names and additional actions"),
      h("p", { class: "small muted" }, "Use names people recognise. Renaming keeps included controls included. Safety alerts stay included. Additional switches and actions stay out until you choose them; review their effect in Home Assistant first."),
      h("div", { class: "screen-fields" }, field("Existing control", choice), field("Household name", name)),
      h("label", {}, include, " Include this control"),
      button("Apply household name", () => { if (!choice.value || !name.value.trim()) { name.focus(); return; } draft.overrides[choice.value] = { ...draft.overrides[choice.value], name: name.value.trim(), include: include.checked }; changed(); setStatus("Name change staged. Save it, then refresh to see the updated list."); }));
  }
  function renderActivity() {
    const candidates = data.items.filter(i => ["sensor", "binary_sensor", "vacuum", "switch"].includes(i.domain));
    const choice = select("Appliance status", candidates.map(i => [i.id, i.name]), candidates[0]?.id || "");
    const name = input("Activity name", "", { placeholder: "e.g. Dishwasher" });
    const from = input("Running state", "", { maxlength: 60 }), to = input("Completed state", "", { maxlength: 60 });
    return h("details", { id: "household-activities" }, h("summary", {}, "Appliance activity today"),
      h("p", { class: "small muted" }, "Only add a transition your appliance reports as a completed cycle. Tracking starts when saved; counts reflect recorded transitions, not household chores."),
      draft.activities.map(a => h("p", {}, `${a.name}: ${a.from_state} → ${a.to_state}`)),
      h("div", { class: "screen-fields" }, field("Appliance name", name), field("Appliance status", choice), field("Running state", from), field("Completed state", to)),
      button("Add activity tracking", () => { if (![name, from, to].every(el => el.value.trim()) || !choice.value) { name.focus(); return; } draft.activities.push({ id: id("activity"), name: name.value.trim(), entity_id: choice.value, from_state: from.value.trim(), to_state: to.value.trim() }); changed(); render(); }));
  }
  function previewCard(card) {
    if (card.type === "heading") return h("h4", {}, card.heading);
    if (card.type === "conditional") {
      const active = card.conditions.every(c => { const state = preview.admitted.find(i => i.id === c.entity)?.state; return Array.isArray(c.state) ? c.state.includes(state) : state === c.state; });
      return active ? previewCard(card.card) : null;
    }
    if (card.type === "clock") return h("p", { class: "preview-clock" }, new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date()));
    if (card.type === "button" && card.tap_action?.action === "navigate") return h("div", { class: "preview-room" }, h("strong", {}, card.name), h("span", { class: "small muted" }, "Opens a contextual view in Home Assistant"));
    if (card.type === "area") return h("div", { class: "preview-room" }, h("strong", {}, data.areas.find(a => a.area_id === card.area)?.name || "Room"), h("span", { class: "small muted" }, "Room controls open in Home Assistant"));
    if (card.type === "vertical-stack") return h("div", { class: "preview-room" }, h("strong", {}, card.cards[0].name), h("span", { class: "small muted" }, "Room summary and controls in Home Assistant"));
    const item = preview.admitted.find(i => i.id === card.entity || card.entities?.includes(i.id));
    if (card.type === "markdown") {
      // Templates are evaluated by HA, never executed in this preview.
      return card.content.includes("{{") ? null : h("p", { class: "muted" }, card.content);
    }
    return h("div", { class: `preview-item ${card.type === "thermostat" ? "preview-climate" : ""}` }, h("strong", {}, card.name || card.title || item?.name || "Activity today"),
      h("span", { class: "muted" }, item?.state || "Updates in Home Assistant"));
  }
  function renderPreview() {
    if (!preview) return null;
    const home = preview.config.views[0];
    return h("section", { id: "screen-preview", class: "screen-preview", tabindex: "-1", "aria-label": "Generated screen preview" },
      h("h3", {}, preview.surface.name), h("p", { class: "small muted" }, `${data.profiles[preview.surface.profile]} · ${preview.admitted.length} admitted household items`),
      preview.context_preview && h("div",{},h("h4",{},"Household context now"),h("pre",{},preview.context_preview.near+"\n\n"+preview.context_preview.ahead),h("p",{class:"small muted"},"This is current data, not a native dashboard render. Wall context adapts after publication.")),
      h("p", { class: "small muted" }, "Layout preview; controls become live in the native Home Assistant dashboard. Conditional items appear only when active. Templates and calendar contents are checked there."),
      h("div", { class: "preview-nav" }, preview.config.views.filter(v => !v.subview).map(v => h("span", {}, v.title))),
      home.type === "panel" ? h("p",{},"Landscape panel: climate on the left; Today, Call, Cameras, Media and Home alongside; household navigation below. Open the native dashboard after publication to verify its actual layout and live states.") : h("div", { class: `preview-sections preview-${preview.surface.profile}` }, home.sections.map(s => { const cards = s.cards.map(previewCard).filter(Boolean); return cards.length > 1 ? h("div", { class: "preview-section" }, cards) : null; })),
      h("p", { class: "small muted" }, "Names and audience choices arrange screens; Home Assistant account permissions still govern access."),
      preview.warnings && h("p", { class: "small muted" }, preview.warnings.filter(w => w.includes("Ambient") || w.includes("inactivity") || w.includes("Wall context")).join(" ")),
      h("details", {}, h("summary", {}, "Review publication"),
        h("p", {}, preview.published ? "Update this Home Starter dashboard. If it was edited in Home Assistant, publication will stop." : "Add a new Home Assistant dashboard. Your current dashboards stay in place."),
        h("p", { class: "small muted" }, "Saving is verified by reading the dashboard back. Check important controls on its intended screen after opening it."),
        button(preview.published ? "Confirm dashboard update" : "Confirm add dashboard", publish, true, busy || !preview.preview_token)),
      preview.published && button("Open dashboard in Home Assistant", () => navigateHA(`/${preview.url_path}/home`), true),
      h("details", {}, h("summary", {}, "Generation details"), h("p", { class: "small muted" }, preview.warnings.join(" ")),
        h("h4", {}, "Why these items?"), h("ul", {}, preview.admitted.map(item => h("li", {}, `${item.name}: ${item.reason}`))),
        h("pre", {}, JSON.stringify(preview.config, null, 2))));
  }
  function render() {
    if (!data) return;
    const preferencesOpen = root.querySelector('.screen-preferences')?.open;
    const surface = draft.surfaces.find(s => s.id === selected);
    root.replaceChildren(...[renderPeople(), renderAddScreen(),
      draft.surfaces.length && field("Screen", select("Selected screen", draft.surfaces.map(s => [s.id, s.name]), selected, event => { selected = event.target.value; preview = null; owner = ""; render(); })),
      surface && h("p", { class: "muted" }, `${data.profiles[surface.profile]} · ${data.areas.find(a => a.area_id === surface.area_id)?.name || "Whole house"} · ${draft.people.find(p => p.id === surface.person_id)?.name || "Shared"}`),
      renderScreenSettings(surface), renderPreferences(surface), renderNames(), renderActivity(),
      h("div", { class: "actions" }, button("Save household settings", save, true, busy || !dirty || !data.inventory_complete), button("Generate screen", generate, false, busy || dirty || !selected || !data.inventory_complete)),
      renderPreview()].filter(Boolean));
    if (preferencesOpen) root.querySelector('.screen-preferences').open = true;
    root.querySelectorAll('input, select, button').forEach(el => { if (busy) el.disabled = true; });
  }
  document.getElementById("surfaces-check").addEventListener("click", () => { if (dirty) { setStatus("Save your changes before refreshing.", true); return; } load(); });
  document.addEventListener("home-starter-refresh-screens", () => {
    if (dirty) { setStatus("Setup changed. Your unsaved choices are retained; review the save precondition before continuing.", true); return; }
    if (busy) reloadRequested = true; else load();
  });
  document.addEventListener("home-starter-readiness-saved", () => { preview = null; render(); setStatus("Readiness choices saved. Generate a fresh preview before publication."); });
  load();
  return load;
}
