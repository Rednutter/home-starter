// Household UI; server owns HA credentials, inventory rules and bounded writes.
export const PREPARATION = [
  "Turn on smart lights behind ordinary wall switches.",
  "Plug in smart plugs, powerboards and appliances you want to keep.",
  "Wake battery-powered devices where practical.",
  "Put robot vacuums on their docks or wake them.",
  "Turn on TVs, speakers, Chromecasts and hubs.",
  "Make sure cameras, doorbells and irrigation equipment are powered.",
  "Bring out old phones and tablets, charge them and connect them to Wi-Fi.",
  "Power Raspberry Pis, displays and similar household devices.",
  "Don't worry about devices you deliberately no longer use.",
];
export const EXTRA_THINGS = [
  ["Old phone / tablet", "Possible uses: bedside clock or alarm, SIP / intercom client, HA display, or Music Assistant controller / player."],
  ["Raspberry Pi / wall display", "Could become a dedicated HA display or controller."],
  ["Smart TV", "Check whether HA supports its controls."],
  ["Speaker / amplifier", "Could be useful for Music Assistant if its connection is supported."],
  ["Cameras / doorbells", "Revisit power, vendor access and HA compatibility."],
  ["Smoke alarms", "Check their own test instructions and batteries. HA isn't a substitute for working alarms."],
  ["Irrigation", "Revisit its controller, power and supported integration."],
  ["Robot vacuum", "Charge it, then check its supported integration."],
  ["HVAC / controller", "Identify the controller and check HA compatibility."],
  ["Calendars / ICS feeds", "Could be useful for a household calendar later."],
  ["Other smart appliances", "Note the manufacturer and model to revisit."],
  ["Other", "Keep it in mind for a future pass through the house."],
];
export const CATEGORIES = { needs_room: "Needs a room", duplicate: "Possible duplicates", attention: "Needs attention", offline: "Possibly offline" };

export function visibleDevices(inventory, filter, query) {
  const matching = new Set(inventory.findings.filter(f => f.category === filter).flatMap(f => f.device_ids));
  return inventory.devices.filter(d => (filter === "all" || (filter === "fine" ? d.status === "fine" : matching.has(d.id))) &&
    [d.name, d.manufacturer, d.model].filter(Boolean).join(" ").toLowerCase().includes(query.toLowerCase()));
}

export function initHouse({ h, api, navigateHA, scan }) {
  let inventory = null, filter = "all", query = "", reading = false, writing = false, notice = "";
  const body = document.getElementById("inventory-body"), status = document.getElementById("inventory-status");
  const button = (text, onclick, primary = false) => h("button", { type: "button", class: `btn ${primary ? "primary" : "ghost"}`, onclick }, text);
  const roomName = id => inventory.areas.find(a => a.area_id === id)?.name || (id ? "Unknown room" : "No room");
  const technical = (title, value) => h("details", { class: "technical" }, h("summary", {}, title), h("pre", {}, JSON.stringify(value, null, 2)));
  document.getElementById("fresh-checklist").replaceChildren(...PREPARATION.map((text, i) =>
    h("label", { class: "checklist-row", for: `prep-${i}` }, h("input", { id: `prep-${i}`, type: "checkbox" }), h("span", {}, text))));
  document.getElementById("forgotten-body").replaceChildren(...EXTRA_THINGS.map(([label, text], i) => {
    const possibility = h("p", { class: "small muted", hidden: true }, text);
    return h("div", { class: "extra-row" }, h("label", { class: "checklist-row", for: `extra-${i}` },
      h("input", { id: `extra-${i}`, type: "checkbox", onchange: event => { possibility.hidden = !event.target.checked; } }), label), possibility);
  }));

  function findingView(f) {
    return h("details", { class: "finding" }, h("summary", {}, `${f.title} — ${CATEGORIES[f.category]} · ${f.confidence}`),
      h("p", { class: "small" }, "Why?"), h("ul", { class: "plain" }, f.reasons.map(r => h("li", {}, r))),
      f.suggestion ? h("div", {}, h("p", {}, `Suggested room: ${f.suggestion.name} · ${f.suggestion.confidence}`),
        h("ul", { class: "plain" }, f.suggestion.reasons.map(r => h("li", {}, r))), h("p", { class: "small muted" }, "Review the device below before assigning its room.")) : null,
      f.path ? button("Review in Home Assistant", () => navigateHA(f.path)) : null);
  }

  function deviceView(d) {
    const detail = h("details", { class: "device", id: `device-${d.id}` });
    const counts = `${d.entities.length} entities${d.unavailable_count ? ` · ${d.unavailable_count} unavailable` : ""}${d.disabled_count ? ` · ${d.disabled_count} disabled` : ""}`;
    detail.append(h("summary", {}, h("strong", {}, d.name), h("span", { class: "muted small" }, `${counts} · ${d.status === "fine" ? "Already fine" : d.status === "unknown" ? "Not fully observed" : d.status}`)));
    detail.append(h("p", { class: "small muted" }, [d.manufacturer, d.model, ...d.integrations.map(e => e.domain)].filter(Boolean).join(" · ")));
    const related = [...d.linked_ids, ...d.children_ids, ...d.sibling_ids, d.parent_device_id, d.via_device_id].filter(Boolean);
    if (related.length) detail.append(h("p", {}, "Related in HA: ", [...new Set(related)].map(id => inventory.devices.find(x => x.id === id)?.name || id).join(", ")));
    const room = h("select", { id: `area-${d.id}`, disabled: writing || inventory.sources.areas?.status !== "ok" },
      h("option", { value: "", selected: !d.area_id }, "No room"), inventory.areas.map(a => h("option", { value: a.area_id, selected: a.area_id === d.area_id }, a.name)));
    const review = h("div", { class: "room-review" });
    const showReview = () => {
      const target = room.value || null;
      if (target === d.area_id) { review.replaceChildren(h("p", {}, "Choose a different room first.")); return; }
      review.replaceChildren(h("p", {}, `Change only ${d.name}'s room from ${roomName(d.area_id)} to ${roomName(target)}?`),
        h("p", { class: "small muted" }, "Names, entity IDs and any entity-specific room overrides stay unchanged."),
        button("Confirm room change", async event => {
          if (writing) return;
          writing = true;
          event.currentTarget.disabled = true;
          room.disabled = true;
          try {
            const result = await api("api/inventory/area", { method: "POST", body: JSON.stringify({ device_id: d.id, area_id: target, expected_area_id: d.area_id, confirm: true }) });
            notice = result.verified ? `Verified: ${d.name} is now in ${roomName(target)}.` : "The change wasn't verified. Check again.";
          } catch (err) { notice = `Room change not verified: ${err.message}`; }
          finally { writing = false; await refresh(); (body.querySelector(".notice") || status).focus(); }
        }, true), button("Cancel", () => { review.replaceChildren(); reviewButton.focus(); }));
    };
    const reviewButton = button("Review room change", showReview);
    room.addEventListener("change", () => review.replaceChildren());
    detail.append(h("div", { class: "room-controls" }, h("label", { for: `area-${d.id}` }, "Room"), room,
      reviewButton), review, button("Open device in Home Assistant", () => navigateHA(d.path)));
    detail.append(h("details", { class: "technical" }, h("summary", {}, "Entities"), h("ul", { class: "plain" }, d.entities.map(e =>
      h("li", {}, `${e.name} — ${e.disabled_by ? `Disabled (${e.disabled_by})` : e.state ?? "Not observed"}${e.area_id ? ` · Room override: ${roomName(e.area_id)}` : ""}`, h("code", {}, ` ${e.entity_id}`))))));
    detail.append(technical("Technical identity and relationships", { id: d.id, identifiers: d.identifiers, connections: d.connections,
      parent_device_id: d.parent_device_id, via_device_id: d.via_device_id, linked_ids: d.linked_ids, sibling_ids: d.sibling_ids, config_entries: d.config_entries }));
    return detail;
  }

  function render() {
    if (!inventory) return;
    const counts = inventory.counts;
    body.replaceChildren(h("p", { class: "inventory-summary" }, `${counts.devices} devices · ${counts.areas} rooms · ${counts.integrations} integrations`),
      h("p", {}, `${counts.findings} findings worth reviewing · ${counts.fine} devices already fine`));
    if (notice) body.append(h("p", { role: "status", class: "notice", tabindex: "-1" }, notice));
    const missing = Object.entries(inventory.sources).filter(([, s]) => s.status !== "ok");
    if (missing.length) body.append(h("p", { class: "error" }, "This inventory is incomplete. Missing information isn't evidence of missing hardware."),
      technical("What couldn't be read", Object.fromEntries(missing)));
    body.append(h("p", { class: "small muted" }, "A scan is a snapshot. Sleeping or powered-off devices may look unavailable. 'Already fine' means enabled entities had usable states during this scan."));
    const filters = h("div", { class: "house-filters", "aria-label": "Inventory filters" }, [
      ["all", "All devices"], ...Object.entries(CATEGORIES), ["fine", "Already fine"],
    ].map(([key, text]) => h("button", { id: `filter-${key}`, type: "button", class: "btn ghost", "aria-pressed": String(filter === key), onclick: () => { filter = key; render(); document.getElementById(`filter-${key}`).focus(); } }, text,
      key in CATEGORIES ? ` (${inventory.findings.filter(f => f.category === key).length})` : "")));
    const search = h("input", { id: "device-search", type: "search", value: query, placeholder: "Find a device" });
    search.addEventListener("change", event => { query = event.target.value; render(); document.getElementById("device-search").focus(); });
    body.append(filters, h("label", { class: "search-label", for: "device-search" }, "Find a device by name, maker or model"), search);
    const findings = inventory.findings.filter(f => filter === "all" || f.category === filter);
    if (filter !== "fine" && findings.length) body.append(h("details", { class: "findings-list", open: filter !== "all" }, h("summary", {}, `Findings (${findings.length})`), findings.map(findingView)));
    const visible = visibleDevices(inventory, filter, query);
    const floorNames = new Map(inventory.floors.map(f => [f.floor_id, f.name]));
    const rooms = [...inventory.areas].sort((a, b) => `${floorNames.get(a.floor_id) || ""} ${a.name}`.localeCompare(`${floorNames.get(b.floor_id) || ""} ${b.name}`));
    for (const room of [...rooms, { area_id: null, name: "Needs a room" }]) {
      const devices = visible.filter(d => room.area_id === null ? !d.area_id || !inventory.areas.some(a => a.area_id === d.area_id) : d.area_id === room.area_id);
      if (!devices.length) continue;
      const issues = devices.filter(d => d.status === "attention" || d.status === "disabled").length;
      body.append(h("details", { class: "room", open: room.area_id === null && filter === "needs_room" },
        h("summary", {}, `${floorNames.get(room.floor_id) ? floorNames.get(room.floor_id) + ' / ' : ''}${room.name} — ${devices.length} devices`,
          h("span", { class: "small muted" }, issues ? ` · ${issues} need attention` : devices.every(d => d.status === "fine") ? " · OK" : " · Some not fully observed")), devices.map(deviceView)));
    }
    if (!visible.length) body.append(h("p", { class: "muted" }, "No devices match this view."));
    body.append(technical("Entities without a known device", inventory.unattached_entities),
      h("p", { class: "small muted" }, `${counts.ignored_entries} ignored integration entries. Ignored discoveries aren't treated as broken devices.`));
  }

  async function refresh() {
    if (reading) return;
    reading = true;
    document.getElementById("inventory-check").disabled = true;
    status.textContent = "Reading your house inventory…";
    try {
      inventory = await api("api/inventory");
      render();
      status.textContent = `Read-only inventory · ${new Date().toLocaleTimeString()}`;
    } catch (err) {
      inventory = null;
      body.replaceChildren();
      status.textContent = `Inventory couldn't be read: ${err.message}. Check again.`;
    } finally { reading = false; document.getElementById("inventory-check").disabled = false; }
  }
  document.getElementById("inventory-check").addEventListener("click", refresh);
  document.getElementById("scan-now").addEventListener("click", async event => {
    event.currentTarget.disabled = true;
    try { await Promise.all([scan(true), refresh()]); document.querySelector("#fresh-batteries details").open = false;
      document.getElementById("your-home").scrollIntoView({ block: "start" }); }
    finally { document.getElementById("scan-now").disabled = false; }
  });
  refresh();
  return refresh;
}
