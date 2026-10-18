import { connectionSetup } from "./connections.js";
// Relationship setup only. Google and provider credentials stay in their native apps.
export function initServices({ h, api, navigateHA }) {
  const root = document.getElementById("services-body"), status = document.getElementById("services-status");
  root.before(connectionSetup({ h, api, navigateHA }));
  let data, draft, busy = false, dirty = false;
  const opened = new Set();
  const changed = () => { dirty = true; root.dataset.dirty = "true"; status.textContent = "Unsaved service mappings. Save to keep them for later."; };
  const button = (label, action) => h("button", { type: "button", class: "btn ghost", onclick: action, disabled: busy }, label);
  const field = (label, control) => h("label", { class: "screen-field" }, h("span", {}, label), control);
  const select = (label, choices, value, change) => {
    const rows = [["", "Set up later"], ...choices];
    if (value && !rows.some(r => r[0] === value)) rows.push([value, "Saved selection · currently unavailable"]);
    return h("select", { "aria-label": label, onchange: e => { change(e.target.value || null); changed(); } },
      rows.map(([id, name]) => h("option", { value: id, selected: id === (value || "") }, name)));
  };
  const members = (label, row) => h("fieldset", {}, h("legend", {}, label), data.setup.people.map(person =>
    h("label", { class: "checklist-row" }, h("input", { type: "checkbox", checked: row.people.includes(person.id), onchange: e => {
      row.people = e.target.checked ? [...row.people, person.id] : row.people.filter(id => id !== person.id); changed();
    } }), person.name)));
  const disclosure = (id, title, ...children) => h("details", { open: opened.has(id), "data-service-section": id }, h("summary", {}, title), ...children);
  function musicButton() {
    return data.setup.music_path ? button("Open Music Assistant", () => navigateHA(data.setup.music_path))
      : h("p", {}, "Connect Music Assistant in Music below, then refresh these choices.");
  }
  function render() {
    if (!data) return;
    root.querySelectorAll("details[data-service-section]").forEach(node => {
      if (node.open) opened.add(node.dataset.serviceSection); else opened.delete(node.dataset.serviceSection);
    });
    const options = data.setup;
    const providerChoices = domains => options.providers.filter(p => domains.includes(p.domain)).map(p => [p.id, `${p.name} · ${p.status}`]);
    root.replaceChildren(
      h("p", {}, "Finish these connections whenever you’re ready. Saved mappings keep people, accounts and speakers separate; they do not verify playback."),
      disclosure("calendars", "Google calendar hub",
        h("p", {}, "Choose one Google account in Home Assistant. Share or subscribe your family, school, sport and work calendars into that account, then return here and refresh."),
        button("Set up Google in Home Assistant", () => navigateHA("/config/integrations/integration/google")),
        field("Google integration", select("Google integration", options.google.map(g => [g.id, `${g.name} · ${g.state}`]), draft.calendar_hub, v => draft.calendar_hub = v)),
        !options.google.length && h("p", { class: "small muted" }, "No Google integration found yet. You can leave this pending."),
        ...draft.calendars.map(row => h("fieldset", {}, h("legend", {}, options.calendars.find(c => c.id === row.entity_id)?.name || row.entity_id),
          field("Calendar purpose", select("Purpose for " + row.entity_id, ["household", "person", "school", "timetable", "sport", "work", "other"].map(v => [v, v === "timetable" ? "School timetable (ordered classes)" : v]), row.category, v => row.category = v || "other")),
          members("People this calendar belongs to", row),
          button("Remove calendar mapping", () => { draft.calendars = draft.calendars.filter(c => c !== row); changed(); render(); }))),
        field("Add a calendar", select("Add a calendar", options.calendars.filter(c => !draft.calendars.some(r => r.entity_id === c.id)).map(c => [c.id, c.name]), null, v => {
          if (v) { draft.calendars.push({ entity_id: v, category: "other", people: [] }); render(); }
        })),
        h("p", { class: "small muted" }, "For a school timetable, choose its child explicitly. Timetable subjects never imply equipment or uniforms. For personal events, select their people explicitly. After saving, choose and verify the calendar sources under Home Readiness; existing visibility permissions still apply.")),
      disclosure("spotify", "Spotify accounts",
        h("p", {}, "In Music Assistant Settings → Music providers, add and sign in to each Spotify account separately. Give each provider its household account name, then refresh and match it below. Children use the shared accounts."),
        musicButton(),
        ...draft.media_identities.map(row => field(`${row.name} · ${row.scope}`, select("Spotify provider for " + row.name, providerChoices(["spotify"]), row.provider_id, v => row.provider_id = v))),
        !draft.media_identities.length && h("p", {}, "No household Spotify identities have been planned yet."),
        h("p", { class: "small muted" }, "Each account needs its own provider. These labels record ownership; speaker routing and simultaneous playback still need verification.")),
      disclosure("books", "Audiobook library",
        h("p", {}, "In Music Assistant Settings → Music providers, add your supported audiobook service. Enter its server address, library location and login there. Return here to match the connected provider and record its intended users."),
        musicButton(),
        ...draft.libraries.map(row => h("fieldset", {}, h("legend", {}, row.name),
          field("Library name", h("input", { type: "text", value: row.name, maxlength: 80, oninput: e => { row.name = e.target.value; changed(); } })),
          field("Audiobook provider", select("Audiobook provider for " + row.name, providerChoices(["audiobookshelf", "audible", "storytel"]), row.provider_id, v => row.provider_id = v)),
          members("Intended library users", row),
          button("Remove library mapping", () => { draft.libraries = draft.libraries.filter(r => r !== row); changed(); render(); }))),
        button("Add audiobook library", () => { draft.libraries.push({ id: "library-" + Array.from(crypto.getRandomValues(new Uint8Array(12)), v => v.toString(16).padStart(2, "0")).join(""), name: "Audiobook library", provider_id: null, people: [], progress_mode: "listener_local" }); changed(); render(); }),
        h("p", { class: "small muted" }, "These mappings record the plan; they do not grant provider access. Children still use approved House favourites. Listening progress stays with the selected Home Starter person. Provider-wide progress is not imported. Audiobook resume needs a real-library test before it is verified.")),
      button("Save service mappings", save), button("Refresh connection choices", load),
      ...(dirty ? [button("Discard edits and load saved mappings", () => { dirty = false; root.dataset.dirty = "false"; load(); })] : []));
    root.querySelectorAll("input, select, button").forEach(node => { node.disabled = busy; });
  }
  async function load() {
    if (busy) return;
    if (dirty) { status.textContent = "Save your service mappings before refreshing. Your edits are retained."; return; }
    busy = true; render();
    try {
      data = await api("api/services"); draft = structuredClone(data.configuration);
      status.textContent = "Saved mappings loaded. Connections can be completed later.";
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; render(); }
  }
  async function save() {
    if (busy) return;
    busy = true; render();
    try {
      data = await api("api/services", { method: "POST", body: JSON.stringify(draft) });
      draft = structuredClone(data.configuration); dirty = false; root.dataset.dirty = "false";
      status.textContent = "Service mappings saved. Pending connections can be finished here later.";
      document.dispatchEvent(new CustomEvent("home-starter-services-saved"));
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; render(); }
  }
  document.getElementById("services-check").addEventListener("click", load);
  load();
}
