// Administrator controls; household playback stays in the shared media actions.
export function mediaSetup({ h, api }) {
  const root = h("details", {}, h("summary", {}, "Music discovery, radio and ambient"));
  const body = h("div", {}), notice = h("p", { role: "status", class: "muted" }, "Prepare catalogue discovery and household playback policy.");
  let busy = false, data, selected = new Set(), cleanup;
  const button = (label, action) => h("button", { type: "button", class: "btn ghost", disabled: busy, onclick: action }, label);
  async function request(action, values = {}) {
    if (busy) return;
    busy = true; render();
    try {
      const value = await api("api/media", action ? { method: "POST", body: JSON.stringify({ action, epoch: data?.catalogue.epoch, ...values }) } : undefined);
      if (action === "cleanup_preview") cleanup = value;
      else if (action === "cleanup") { cleanup = null; notice.textContent = `${value.removed} imported mappings removed from Music Assistant. Spotify saved music was not changed.`; }
      else { data = value; selected = new Set(value.catalogue.items.filter(r => r.selected).map(r => r.id)); notice.textContent = `${value.catalogue.ready} of ${value.catalogue.selected} selected stations ready. ${value.catalogue.discovered} stations discovered.`; }
    } catch (error) { notice.textContent = error.message; }
    finally { busy = false; render(); }
  }
  function render() {
    body.replaceChildren(notice, h("div", { class: "actions" }, button("Check media", () => request()), button("Prepare media", () => request("prepare"))));
    if (data) {
      body.append(h("p", {}, `Local station lookup: ${(data.catalogue.local_lookup_state || "ready_for_consent").replaceAll("_", " ")}.`), h("p", { class: "muted" }, "Local station lookup sends an approximate postcode to LiSTNR. Your home address and precise coordinates stay local."), button(data.catalogue.local_lookup_allowed ? "Disable postcode lookup":"Allow local radio lookup", () => request(data.catalogue.local_lookup_allowed ? "disable_local_lookup":"allow_local_lookup")), h("p", { class: "muted" }, "Approximate postal regions: ", h("a", { href: "https://www.geonames.org/", target: "_blank", rel: "noopener noreferrer" }, "GeoNames")));
      body.append(h("p", {}, "Spotify library mirroring is disabled while catalogue search, playback and playlists remain available. Continuation uses related provider tracks."));
      if (data.engine.issue) body.append(h("p", { role: "status" }, data.engine.issue));
      for (const [category, label] of [["radio", "Radio"], ["music", "Music stations"], ["ambient", "Ambient"]]) {
        const rows = data.catalogue.items.filter(r => r.category === category);
        body.append(h("details", {}, h("summary", {}, `${label} · ${rows.filter(r => selected.has(r.id)).length} selected`), rows.map(row => h("label", { class: "field" }, h("input", { type: "checkbox", checked: selected.has(row.id), disabled: busy, onchange: event => { event.target.checked ? selected.add(row.id) : selected.delete(row.id); } }), row.name, row.issue ? ` · ${row.issue}` : ""))));
      }
      body.append(button("Save selected stations", () => request("select", { selected: [...selected] })), button("Review old Spotify imports", () => request("cleanup_preview")));
    }
    if (cleanup) body.append(h("p", {}, `${cleanup.imported_mappings} imported Spotify mappings are in the MA track library. Cleanup removes these local mappings; mappings from other sources are preserved. Spotify saved music is unchanged.`), button("Remove these MA imports", () => request("cleanup")));
  }
  root.append(body); render();
  return root;
}
