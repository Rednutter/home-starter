// HA owns the people and registries. This view stores only reviewed intent.
export function devicesFor(view, filter, query = "") {
  return view.devices.filter(d => (filter === "all" || (filter === "room" ? d.needs_room : filter === "attention" ? d.attention : (d.placed || d.shared || d.portable) && !d.attention)) &&
    [d.name, d.manufacturer, d.model].filter(Boolean).join(" ").toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => Number(a.attention) - Number(b.attention) || a.name.localeCompare(b.name));
}

export function pendingHouse(view) {
  const c = view.counts, pending = [];
  if (!view.complete) pending.push("Some HA records could not be read");
  if (!view.expectation) pending.push("Confirm household size");
  else if (!c.expectation_matches) pending.push(`Confirm ${view.expectation.people} household members and ${view.expectation.adults} adults`);
  if (c.people_needing_review) pending.push(`${c.people_needing_review} person records need review`);
  if (!view.structure_confirmed) pending.push("Compare floors and rooms with the physical house");
  if (c.needs_room) pending.push(`${c.needs_room} equipment records need a room`);
  if (c.attention) pending.push(`${c.attention} equipment records need attention`);
  return pending;
}

export function initThisHouse({ h, api, navigateHA }) {
  const root = document.getElementById("this-house-body"), status = document.getElementById("this-house-status");
  const refreshButton = document.getElementById("this-house-refresh");
  let data = null, busy = false, reading = false, dirty = false, filter = "room", query = "", notice = "";
  const button = (label, click, primary = false) => h("button", { type: "button", class: `btn ${primary ? "primary" : "ghost"}`, disabled: busy || !data?.complete, onclick: click }, label);
  const field = (label, control) => h("label", { class: "screen-field" }, h("span", {}, label), control);
  const input = (value, attrs = {}) => h("input", { value: value ?? "", disabled: busy, ...attrs, oninput: () => { dirty = true; } });
  const select = (options, value, label) => h("select", { "aria-label": label, disabled: busy, onchange: () => { dirty = true; } },
    options.map(([id, text]) => h("option", { value: id, selected: id === (value ?? "") }, text)));
  const roomName = id => data.areas.find(a => a.area_id === id)?.name || "No room";
  const floorName = id => data.floors.find(f => f.floor_id === id)?.name || "No floor";
  const nativeButton = (label, path) => h("button", { type: "button", class: "btn ghost", disabled: busy, onclick: () => navigateHA(path) }, label);

  async function save(action, payload, success) {
    if (busy || !data?.complete) return;
    busy = true;
    refreshButton.disabled = true;
    root.querySelectorAll("button,input,select,textarea").forEach(el => { el.disabled = true; });
    status.textContent = "Saving the reviewed change and checking the result…";
    try {
      await api("api/house/" + action, { method: "POST", body: JSON.stringify({ confirm: true, revision: data.revision, ...payload }) });
      notice = success; dirty = false;
      document.dispatchEvent(new CustomEvent("home-starter-saved"));
    } catch (error) { notice = error.message; dirty = false; }
    finally { busy = false; await refresh(true); status.focus(); }
  }

  function review(container, description, action, payload, success) {
    container.replaceChildren(h("p", {}, description), h("div", { class: "actions" },
      button("Confirm " + (action === "placement" ? "placement" : action === "relationship" ? "physical note" : action === "person" ? "person" : action === "structure" ? "house structure" : action === "area_intent" ? "area purpose" : action === "expectation" ? "household size" : action + " change"),
        () => save(action, payload, success), true), button("Cancel", () => { container.replaceChildren(); dirty = false; })));
  }

  function peopleView() {
    const section = h("section", { id: "this-house-people", class: "house-part", "aria-labelledby": "this-house-people-h" }, h("h3", { id: "this-house-people-h" }, "People"));
    if (data.people_error) section.append(h("p", { class: "error" }, data.people_error));
    section.append(h("p", { class: "small muted" }, "These are Home Assistant's Person records. Household roles here do not change anyone's login or permissions."));
    const expectation = h("details", {}, h("summary", {}, data.expectation ? `Expected household: ${data.expectation.people} people, ${data.expectation.adults} adults` : "Confirm household size"));
    const count = input(data.expectation?.people, { type: "number", min: "1", max: "50", "aria-label": "Household members" });
    const adults = input(data.expectation?.adults, { type: "number", min: "0", max: "50", "aria-label": "Adults" });
    const countReview = h("div", { class: "house-review" });
    expectation.append(h("div", { class: "house-fields" }, field("Household members", count), field("Adults", adults)), button("Review household size", () =>
      review(countReview, `Confirm ${count.value} people and ${adults.value} adults?`, "expectation", { people: Number(count.value), adults: Number(adults.value) }, "Household size saved.")), countReview);
    section.append(expectation);
    for (const person of [...data.people].sort((a, b) => Number(a.confirmed) - Number(b.confirmed) || a.name.localeCompare(b.name))) {
      const trackerNames = person.trackers.map(id => data.trackers.find(t => t.entity_id === id)?.name || id);
      const row = h("details", { class: "house-row" }, h("summary", {}, h("strong", {}, person.name), h("span", { class: "small muted" },
      `${person.confirmed ? person.role === "other" ? "Display / other account" : `${person.role === "adult" ? "Adult" : "Child"} · confirmed` : person.changed ? "Changed since confirmation" : "Confirm household member"}${person.role === "other" ? "" : !person.trackers.length ? " · no tracker assigned" : !person.usable_tracker ? " · tracker not reporting" : " · tracker reporting"}`)));
      row.append(h("p", {}, trackerNames.length ? `HA assigns: ${trackerNames.join(", ")}.` : "No presence tracker assigned in HA."),
        ...(person.trackers.length && !person.usable_tracker ? [h("p", { class: "warn" }, "No assigned tracker currently reports a usable state. Presence is not verified.")] : []));
      const role = select([["", "Choose household role"], ["adult", "Adult"], ["child", "Child"], ["other", "Display / other account"]], person.role, "Household role for " + person.name);
      const panel = h("div", { class: "house-review" });
      row.append(field("Household role", role), button("Review person", () => review(panel,
        `Confirm ${person.name} as ${role.value === "other" ? "a display or other account, outside the household member count" : role.value || "unresolved"}? Their HA record and trackers stay as shown.`,
        "person", { person_id: person.id, role: role.value, expected: person.signature }, "Person confirmation saved.")), panel,
      nativeButton("Manage person and trackers in HA", "/config/person"));
      section.append(row);
    }
    section.append(h("details", {}, h("summary", {}, `Available device trackers (${data.trackers.length})`),
      h("ul", { class: "plain" }, data.trackers.map(t => h("li", {}, `${t.name} — ${t.disabled ? "disabled" : t.available ? "reporting" : "not reporting"}${t.people.length ? " · already assigned" : " · no person assigned"}`))),
      h("p", { class: "small muted" }, "Reporting does not establish ownership. Assign or correct trackers in the native Person settings, then refresh here.")));
    return section;
  }

  function registryForm(kind, current = null) {
    const isFloor = kind === "floor", itemName = current?.name || `Add ${isFloor ? "a floor" : "a room"}`;
    const row = h("details", { class: "house-row" }, h("summary", {}, itemName,
      ...(current && !isFloor ? [h("span", { class: "small muted" }, `${floorName(current.floor_id)} · ${data.devices.filter(d => d.area_id === current.area_id).length} equipment records${current.kind === "group" ? " · group / whole level" : ""}`)] : [])));
    const name = input(current?.name, { maxlength: "80", "aria-label": `${isFloor ? "Floor" : "Room"} name` });
    const extra = isFloor ? input(current?.level, { type: "number", min: "-100", max: "200", "aria-label": "Floor level (optional)" }) :
      select([["", "No floor"], ...data.floors.map(f => [f.floor_id, f.name])], current?.floor_id, "Floor for " + itemName);
    const panel = h("div", { class: "house-review" });
    row.append(h("div", { class: "house-fields" }, field(isFloor ? "Floor name" : "Room name", name), field(isFloor ? "Floor level (optional)" : "Floor", extra)),
      button(`Review ${kind} change`, () => {
        const payload = { id: current?.[isFloor ? "floor_id" : "area_id"] || null, name: name.value.trim(), expected: data.structure_signature,
          ...(isFloor ? { level: extra.value === "" ? null : Number(extra.value) } : { floor_id: extra.value || null }) };
        review(panel, `${current ? `Update ${current.name} to` : "Create"} ${payload.name || "an unnamed " + kind}${isFloor ? extra.value === "" ? " (level unspecified)" : ` at level ${extra.value}` : ` on ${floorName(payload.floor_id)}`}? Existing IDs and device assignments are preserved.`,
          kind, payload, `${isFloor ? "Floor" : "Room"} saved and read back from Home Assistant.`);
      }), panel);
    if (current && !isFloor) {
      const purpose = select([["", "Not reviewed"], ["room", "Individual room / physical area"], ["group", "Group of rooms / whole level"]], current.kind, "Area purpose for " + itemName);
      const purposeReview = h("div", { class: "house-review" });
      row.append(field("What this HA area represents", purpose), button("Review area purpose", () => review(purposeReview,
        `Confirm ${current.name} represents ${purpose.value === "group" ? "a group of rooms or whole level, rather than an individual equipment location" : "an individual room or physical area"}? HA's record and existing assignments stay unchanged.`,
        "area_intent", { area_id: current.area_id, kind: purpose.value, expected: current.signature }, "Area purpose confirmed.")), purposeReview);
    }
    return row;
  }

  function structureView() {
    const section = h("section", { class: "house-part", "aria-labelledby": "this-house-structure-h" }, h("h3", { id: "this-house-structure-h" }, "Floors & rooms"),
      h("p", {}, data.structure_confirmed ? "You confirmed the current floors and rooms. Live HA changes will reopen this check." : "Compare HA's rooms with the physical house. Correct existing records before creating a second version of the same room."),
      h("p", { class: "small muted" }, "If an existing area represents several rooms or a whole level, mark its purpose below. Keep it for existing controls; place physical equipment in individual rooms."));
    const floors = h("details", {}, h("summary", {}, `Floors (${data.floors.length})`), data.floors.map(f => registryForm("floor", f)), registryForm("floor"));
    const areas = h("details", { open: data.counts.areas_without_floor > 0 }, h("summary", {}, `Rooms / areas (${data.areas.length}) · ${data.counts.areas_without_floor} without a floor`),
      [...data.areas].sort((a, b) => Number(Boolean(a.floor_id)) - Number(Boolean(b.floor_id)) || a.name.localeCompare(b.name)).map(a => registryForm("area", a)), registryForm("area"));
    const panel = h("div", { class: "house-review" });
    section.append(floors, areas, button("Floors and rooms match the house", () => review(panel, "Confirm the full current list of floors and rooms matches the physical house? Missing rooms should be added first.",
      "structure", { expected: data.structure_signature }, "House structure confirmed.")), panel, nativeButton("Open HA floors and areas", "/config/areas"));
    return section;
  }

  function deviceView(device) {
    const row = h("details", { class: "house-row", id: "placement-" + device.id }, h("summary", {}, h("strong", {}, device.name),
      h("span", { class: "small muted" }, `${device.shared ? "Shared media group" : device.portable ? "Portable · no fixed room" : roomName(device.area_id)}${device.confirmed ? " · confirmed" : device.changed ? " · changed since confirmation" : ""}${device.attention ? " · needs attention" : ""}`)));
    row.addEventListener("toggle", () => {
      if (!row.open || row.dataset.built) return;
      row.dataset.built = "true";
      row.append(h("p", { class: "small muted" }, [device.manufacturer, device.model, ...(device.integrations || []), `${device.entity_count} entities`].filter(Boolean).join(" · ")),
        h("p", {}, device.shared ? "HA identifies this as a shared media group, which has no single physical room." : device.portable ? "You confirmed this equipment has no fixed room." : `HA says this is in ${roomName(device.area_id)}. Is that right?`),
        ...(device.reasons.length ? [h("ul", { class: "plain" }, device.reasons.map(reason => h("li", {}, reason)))] : []));
      const area = select([["", "Choose a room"], ...data.areas.filter(a => a.kind !== "group").map(a => [a.area_id, `${floorName(a.floor_id)} / ${a.name}`])], device.area_id, "Room for " + device.name);
      const panel = h("div", { class: "house-review" });
      if (!device.shared) row.append(field("Physical room", area), button("Review placement", () => review(panel,
        area.value === device.area_id ? `Confirm ${device.name} is physically in ${roomName(area.value)}?` : `Move ${device.name} from ${roomName(device.area_id)} to ${roomName(area.value)} in HA? Names, entity IDs and entity room overrides stay unchanged.`,
        "placement", { device_id: device.id, area_id: area.value, expected: device.signature }, "Device placement confirmed and read back from HA.")), panel);
      if (!device.shared && !device.portable) row.append(button("No fixed room (portable equipment)", () => review(panel,
        `Confirm ${device.name} moves around and should not need a fixed room? Its HA area stays unchanged.`, "portable", { device_id: device.id, expected: device.signature }, "Portable equipment confirmed.")));
      const notes = h("details", {}, h("summary", {}, "Physical connection or function"));
      const note = input(device.relationship, { maxlength: "240", "aria-label": "Physical note for " + device.name });
      const noteReview = h("div", { class: "house-review" });
      notes.append(h("p", { class: "small muted" }, "Record only a useful physical fact, such as which speaker system this player feeds or which circuit this switch operates. No passwords."), field("Physical connection or function", note),
        button("Review physical note", () => review(noteReview, note.value ? `Save this physical fact for ${device.name}: ${note.value}` : `Clear the physical note for ${device.name}?`,
          "relationship", { device_id: device.id, text: note.value.trim(), expected: device.signature }, "Physical note saved.")), noteReview);
      row.append(notes, nativeButton("Open device in HA", device.path));
    });
    return row;
  }

  function render() {
    const c = data.counts, pending = pendingHouse(data);
    root.replaceChildren(h("p", { class: "inventory-summary" }, `${c.members} confirmed household members${data.expectation ? ` / ${data.expectation.people} expected` : ""} · ${c.floors} floors · ${c.areas} rooms / areas`),
      h("p", {}, `${c.devices} equipment records · ${c.placed} already placed · ${c.needs_room} need a room · ${c.attention} need attention`),
      h("p", { class: "small muted" }, `${c.shared} shared media groups · ${c.portable} confirmed portable records · ${c.members_without_tracker} household members without a usable tracker`),
      h("p", { class: "small muted" }, `HA contains ${c.people} Person records and ${c.registry_devices} device records in total. Service-only records are kept out of placement work. Attention and missing-room counts can overlap.`));
    if (notice) root.append(h("p", { class: "notice", role: "status" }, notice));
    if (!data.complete) root.append(h("p", { class: "error" }, "The house view is incomplete. Changes are disabled until its HA sources can be read."));
    root.append(h("details", { open: pending.length > 0, class: "house-pending" }, h("summary", {}, pending.length ? "Still needs commissioning" : "House model reviewed"),
      pending.length ? h("ul", {}, pending.map(p => h("li", {}, p))) : h("p", {}, "Physical function checks remain separate from the house model.")), peopleView(), structureView());
    const devices = h("section", { class: "house-part", "aria-labelledby": "this-house-devices-h" }, h("h3", { id: "this-house-devices-h" }, "Physical equipment"));
    const filters = h("div", { class: "house-filters", "aria-label": "House equipment filters" },
      [["room", `Needs a room (${c.needs_room})`], ["attention", `Needs attention (${c.attention})`], ["placed", "Already placed / fine"], ["all", "All equipment"]].map(([key, label]) =>
        h("button", { id: "house-filter-" + key, type: "button", class: "btn ghost", "aria-pressed": String(filter === key), disabled: busy, onclick: () => {
          if (dirty) { status.textContent = "Review or cancel your current edit before changing the view."; return; }
          filter = key; render(); document.getElementById("house-filter-" + key).focus();
        } }, label)));
    const search = h("input", { type: "search", value: query, "aria-label": "Find household equipment", placeholder: "Name, maker or model", onchange: event => {
      if (dirty) { status.textContent = "Review or cancel your current edit before searching."; return; }
      query = event.target.value; render(); root.querySelector('input[type="search"]').focus();
    } });
    devices.append(filters, field("Find household equipment", search));
    const rows = devicesFor(data, filter, query);
    if (!rows.length) devices.append(h("p", {}, "No equipment matches this view."));
    if (filter === "placed") devices.append(h("p", { class: "small muted" }, "These records already have a room and no current inventory warnings. Review only discrepancies; an available entity is not proof of correct physical placement."));
    devices.append(...rows.map(deviceView));
    root.append(devices, h("details", {}, h("summary", {}, "Recent confirmed changes"), data.changes.length ?
      h("ul", { class: "plain" }, data.changes.slice().reverse().map(change => h("li", {}, `${change.action} · ${new Date(change.at).toLocaleString()}`))) : h("p", {}, "No house confirmations saved yet.")),
    h("p", { class: "small muted" }, "Capability planning comes after the house model. Music and existing dashboards retain their own checks and saved settings."));
  }

  async function refresh(force = false) {
    if (busy || reading) return;
    if (dirty && !force) { status.textContent = "Review or cancel your current edit before refreshing. Reloading this page discards unsaved edits."; return; }
    refreshButton.disabled = true;
    reading = true;
    status.textContent = "Reading live HA people, floors, rooms and equipment…";
    try { data = await api("api/house"); render(); status.textContent = "Live HA records · confirmations checked against current names, trackers and placement"; }
    catch (error) { data = null; root.replaceChildren(); status.textContent = `This House could not be read: ${error.message}. Existing settings are preserved. Refresh to retry.`; }
    finally { reading = false; refreshButton.disabled = false; }
  }
  refreshButton.addEventListener("click", () => refresh());
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !dirty) refresh(); });
  refresh();
  return refresh;
}
