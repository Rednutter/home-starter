import { apiUrl, navigateHA } from "./routes.js";

const OUTCOMES = [
  { id: "music", title: "Music around the house", text: "Whole-home music, radio and podcasts with Music Assistant.", available: true },
  { id: "tidy", title: "Fix / tidy my Home Assistant", text: "Clean up problems the scan finds.", available: false },
  { id: "audiobooks", title: "Audiobooks & podcasts", text: "A family audiobook library.", available: false },
  { id: "display", title: "Wall tablet / display", text: "A dashboard on the wall.", available: false },
  { id: "intercom", title: "Calling / intercom", text: "Talk between rooms.", available: false },
  { id: "remote", title: "Remote access", text: "Reach Home Assistant away from home.", available: false },
];
const STORE_KEY = "homeStarter.outcome";
const POLL_OPERATION_MS = 2000;
const POLL_SETTLING_MS = 5000;
const SETTLING_STATES = new Set(["installing", "starting", "needs_integration", "integration_starting"]);

const state = { scan: null, music: null, selected: null, confirming: false, busy: false, lastRefresh: 0, settleUntil: 0, timer: null };

// ---------------------------------------------------------------- utilities
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, options = {}) {
  const resp = await fetch(apiUrl(path, document.baseURI), {
    credentials: "same-origin",
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });
  const text = await resp.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_e) { data = null; }
  if (!resp.ok) {
    const err = new Error((data && data.error) || text || `HTTP ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  return data;
}

function remember(id) {
  try { localStorage.setItem(STORE_KEY, id); } catch (_e) { /* storage may be unavailable */ }
}
function recall() {
  try { return localStorage.getItem(STORE_KEY); } catch (_e) { return null; }
}

const sec = (name) => {
  const s = state.scan && state.scan[name];
  return s && s.status === "ok" ? s.data : null;
};
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// ---------------------------------------------------------------- system
function tile(label, value, detail, level) {
  return h("div", { class: `tile ${level || ""}` },
    h("div", { class: "tile-label" }, label),
    h("div", { class: "tile-value" }, value ?? "—"),
    detail ? h("div", { class: "tile-detail" }, detail) : null);
}
const unavailable = (label) => tile(label, "Unavailable", "Couldn't read this", "dim");

function renderSystem() {
  const body = document.getElementById("system-body");
  const status = document.getElementById("scan-status");
  body.replaceChildren();
  if (!state.scan) return;
  const when = new Date(state.scan.scanned_at * 1000).toLocaleTimeString();
  status.textContent = `Read-only scan · ${when}`;

  const system = sec("system"), core = sec("core"), host = sec("host"), apps = sec("apps");
  const integrations = sec("integrations"), areas = sec("areas"), entities = sec("entities"), repairs = sec("repairs");

  const tiles = [];
  tiles.push(core || system
    ? tile("Home Assistant", (core && core.version) || (system && system.homeassistant),
      core && core.update_available ? `Update to ${core.version_latest} available` : (system && system.supervisor ? `Supervisor ${system.supervisor}` : null),
      core && core.update_available ? "info" : "")
    : unavailable("Home Assistant"));
  tiles.push(system
    ? tile("System", system.operating_system || "Unknown OS",
      [system.machine, system.arch].filter(Boolean).join(" · "))
    : unavailable("System"));
  tiles.push(host
    ? tile("Storage", host.disk_free_gb != null ? `${host.disk_free_gb} GB free` : "—",
      host.disk_total_gb != null ? `of ${host.disk_total_gb} GB` : null,
      host.disk_free_gb != null && host.disk_free_gb < 3 ? "warn" : "")
    : unavailable("Storage"));
  tiles.push(apps
    ? tile("Apps", plural(apps.count, "installed", "installed"), `${apps.running} running${apps.updates ? ` · ${apps.updates} update${apps.updates > 1 ? "s" : ""}` : ""}`)
    : unavailable("Apps"));
  tiles.push(integrations
    ? tile("Integrations", String(integrations.integrations),
      integrations.unhealthy_count ? `${integrations.unhealthy_count} failed to set up` : `${integrations.loaded} entries loaded`,
      integrations.unhealthy_count ? "warn" : "")
    : unavailable("Integrations"));
  tiles.push(areas ? tile("Areas", String(areas.count), areas.count ? areas.names.slice(0, 4).join(", ") + (areas.count > 4 ? "…" : "") : "None yet") : unavailable("Areas"));
  tiles.push(entities
    ? tile("Entities", String(entities.count), entities.unavailable_count ? `${entities.unavailable_count} unavailable` : "None unavailable",
      entities.unavailable_count ? "warn" : "")
    : unavailable("Entities"));
  tiles.push(repairs ? tile("Repairs", String(repairs.count), repairs.count ? "Waiting in Settings" : "Nothing to fix", repairs.count ? "info" : "") : unavailable("Repairs"));
  body.append(h("div", { class: "tiles" }, tiles));

  const notes = state.scan.notes || [];
  if (notes.length) {
    body.append(h("ul", { class: "notes" }, notes.map((n) => h("li", { class: n.level }, n.text))));
  }

  const details = [];
  if (integrations && integrations.unhealthy.length) {
    details.push(h("details", {}, h("summary", {}, `Integrations that failed to set up (${integrations.unhealthy_count})`),
      h("ul", { class: "plain" }, integrations.unhealthy.map((e) =>
        h("li", {}, h("strong", {}, e.title || e.domain), ` — ${e.domain}: ${e.state}${e.reason ? ` (${e.reason})` : ""}`)))));
  }
  if (entities && entities.unavailable.length) {
    details.push(h("details", {}, h("summary", {}, `Unavailable entities (${entities.unavailable_count})`),
      h("ul", { class: "plain" }, entities.unavailable.map((e) =>
        h("li", {}, h("strong", {}, e.name), ` — ${e.entity_id}${e.platform ? ` (${e.platform})` : ""}`))),
      entities.unavailable_count > entities.unavailable.length ? h("p", { class: "muted" }, `Showing the first ${entities.unavailable.length}.`) : null));
  }
  if (apps && apps.items.length) {
    details.push(h("details", {}, h("summary", {}, `Installed apps (${apps.count})`),
      h("ul", { class: "plain" }, apps.items.map((a) =>
        h("li", {}, h("strong", {}, a.name), ` — ${a.version || "?"} · ${a.state || "unknown"}${a.update_available ? " · update available" : ""}`)))));
  }
  const missing = ["system", "core", "host", "resolution", "apps", "integrations", "areas", "entities", "repairs"]
    .filter((n) => state.scan[n] && state.scan[n].status !== "ok");
  if (missing.length) {
    details.push(h("details", {}, h("summary", {}, `Parts of the scan that weren't available (${missing.length})`),
      h("ul", { class: "plain" }, missing.map((n) => h("li", {}, h("strong", {}, n), ` — ${state.scan[n].error?.message || "unavailable"}`)))));
  }
  if (details.length) body.append(h("div", { class: "details" }, details));
}

// ---------------------------------------------------------------- outcomes
function renderOutcomes() {
  const box = document.getElementById("outcomes");
  box.replaceChildren(...OUTCOMES.map((o) => h("button", {
    type: "button",
    class: `outcome ${o.available ? "" : "later"} ${state.selected === o.id ? "selected" : ""}`,
    disabled: !o.available,
    "aria-pressed": o.available ? String(state.selected === o.id) : false,
    onclick: () => select(o.id),
  },
  h("span", { class: "outcome-head" },
    h("span", { class: "outcome-title" }, o.title),
    o.available ? null : h("span", { class: "badge" }, "Later")),
  h("span", { class: "outcome-text" }, o.text))));
}

function select(id) {
  state.selected = id;
  remember(id);
  renderOutcomes();
  const panel = document.getElementById("music");
  panel.hidden = id !== "music";
  if (id === "music") {
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    refreshMusic();
  }
}

// ---------------------------------------------------------------- music
const CHECK_ICON = { pass: "✓", fail: "✕", pending: "…", unknown: "?" };

function renderMusic() {
  const body = document.getElementById("music-body");
  const m = state.music;
  if (!m) return;
  const parts = [];
  parts.push(h("div", { class: `status status-${m.verified ? "ready" : m.state}` },
    h("h3", {}, m.title),
    h("p", {}, m.detail)));

  if (m.app) {
    const bits = [m.app.name, m.app.version ? `v${m.app.version}` : (m.app.version_latest ? `latest v${m.app.version_latest}` : null),
      m.app.variant && m.app.variant !== "music_assistant" ? `(${m.app.variant.replace("music_assistant_", "")} channel)` : null];
    parts.push(h("p", { class: "muted app-line" }, bits.filter(Boolean).join(" ")));
  }

  const op = m.operation;
  const running = op && !op.finished;
  const failedOp = op && op.finished && !op.success && !m.verified;
  if (op && (running || (!op.success && !m.verified))) {
    const pct = op.step === "installing" && op.progress ? Math.round(op.progress) : null;
    parts.push(h("div", { class: `operation ${op.finished ? (op.success ? "ok" : "failed") : "running"}` },
      h("p", { class: "op-message" }, op.message),
      !op.finished ? h("div", { class: "bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": pct ?? false },
        h("span", { style: false, class: pct == null ? "indeterminate" : "" })) : null,
      op.finished && !op.success && op.fallback_path ? h("div", { class: "actions" },
        h("button", { type: "button", class: "btn primary", onclick: () => navigateHA(op.fallback_path) }, "Continue in Home Assistant instead"),
        h("button", { type: "button", class: "btn", onclick: () => runAction({ kind: "setup" }) }, "Try again")) : null,
      op.log && op.log.length ? h("details", {}, h("summary", {}, "Details"), h("ol", { class: "plain log" }, op.log.map((l) => h("li", {}, l)))) : null));
    if (pct != null) {
      const fill = parts.at(-1).querySelector(".bar span");
      if (fill) fill.style.width = `${pct}%`;
    }
  }

  if (!running) parts.push(h("ul", { class: "checks" }, m.checks.map((c) =>
    h("li", { class: `check ${c.status}` },
      h("span", { class: "check-icon", "aria-hidden": "true" }, CHECK_ICON[c.status] || "?"),
      h("span", { class: "check-label" }, c.label),
      c.detail ? h("span", { class: "check-detail" }, c.detail) : null))));

  if (state.confirming) {
    parts.push(h("div", { class: "confirm" },
      h("p", {}, h("strong", {}, "Install Music Assistant?"), " Home Starter will add the official Music Assistant repository if it's missing, install the app (a download of a few hundred MB) and start it. Nothing else is changed."),
      h("div", { class: "actions" },
        h("button", { type: "button", class: "btn primary", onclick: () => startSetup() }, "Yes, install it"),
        h("button", { type: "button", class: "btn", onclick: () => { state.confirming = false; renderMusic(); } }, "Cancel"))));
  } else if (failedOp) {
    // The failure box already offers "Continue in Home Assistant" / "Try again".
    parts.push(h("div", { class: "actions" }, h("button", { type: "button", class: "btn", onclick: () => refreshMusic(true) }, "Check again")));
  } else if (m.actions.length) {
    parts.push(h("div", { class: "actions" }, m.actions.map((a) => h("button", {
      type: "button",
      class: `btn ${a.style === "primary" ? "primary" : ""}`,
      disabled: state.busy,
      title: a.hint || false,
      onclick: () => runAction(a),
    }, a.label))));
    const hint = m.actions.find((a) => a.style === "primary" && a.hint);
    if (hint) parts.push(h("p", { class: "muted small" }, hint.hint));
  }

  if (!m.direct_install.available && m.direct_install.reason && ["available", "not_in_store", "stopped"].includes(m.state)) {
    parts.push(h("p", { class: "muted small" }, `${m.direct_install.reason} You'll finish this step in Home Assistant, then come back and press Check again.`));
  }
  body.replaceChildren(...parts);
}

function runAction(a) {
  if (a.kind === "recheck") return refreshMusic(true);
  if (a.kind === "navigate") return navigateHA(a.path);
  if (a.kind === "setup") {
    if (state.music && state.music.state === "stopped") return startSetup();
    state.confirming = true;
    return renderMusic();
  }
}

async function startSetup() {
  state.confirming = false;
  state.busy = true;
  try {
    const res = await api("api/music/setup", { method: "POST", body: JSON.stringify({ confirm: true }) });
    state.music = {
      ...(state.music || {}),
      state: "installing",
      operation: res.operation,
      actions: [],
      verified: false,
      title: "Setting up Music Assistant…",
      detail: "Home Starter is installing and starting Music Assistant. This carries on even if you leave this page.",
      checks: [],
      direct_install: state.music?.direct_install || { available: true },
    };
    renderMusic();
    pollOperation();
  } catch (err) {
    state.busy = false;
    showMusicError(`Couldn't start setup: ${err.message}`);
  }
}

async function pollOperation() {
  clearTimeout(state.timer);
  try {
    const { operation } = await api("api/music/operation");
    if (operation && !operation.finished) {
      state.music.operation = operation;
      renderMusic();
      state.timer = setTimeout(pollOperation, POLL_OPERATION_MS);
      return;
    }
  } catch (_err) { /* fall through to a full refresh */ }
  state.busy = false;
  state.settleUntil = Date.now() + 3 * 60 * 1000;
  await refreshMusic(true);
}

function showMusicError(text) {
  const body = document.getElementById("music-body");
  body.prepend(h("p", { class: "error" }, text));
}

async function refreshMusic(force = false) {
  if (state.selected !== "music") return;
  const now = Date.now();
  if (!force && now - state.lastRefresh < 4000) return;
  state.lastRefresh = now;
  clearTimeout(state.timer);
  try {
    state.music = await api("api/music");
    state.busy = Boolean(state.music.operation && !state.music.operation.finished);
    renderMusic();
    if (state.music.operation && !state.music.operation.finished) {
      state.busy = true;
      state.timer = setTimeout(pollOperation, POLL_OPERATION_MS);
    } else if (SETTLING_STATES.has(state.music.state) && Date.now() < state.settleUntil) {
      // Gentle follow-up right after an install/start while things settle.
      state.timer = setTimeout(() => refreshMusic(true), POLL_SETTLING_MS);
    }
  } catch (err) {
    if (state.music) {
      state.music.verified = false;
      state.music.title = "Couldn't verify Music Assistant";
      state.music.detail = "The last check failed. Check again to get the current status.";
      renderMusic();
    }
    showMusicError(`Couldn't check Music Assistant: ${err.message}`);
  }
}

// ---------------------------------------------------------------- scan
async function scan(refresh = false) {
  const btn = document.getElementById("rescan");
  btn.disabled = true;
  document.getElementById("scan-status").textContent = "Scanning…";
  try {
    state.scan = await api(refresh ? "api/scan?refresh=1" : "api/scan");
    renderSystem();
  } catch (err) {
    document.getElementById("scan-status").textContent = `Scan failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

function init() {
  renderOutcomes();
  document.getElementById("rescan").addEventListener("click", async () => {
    await scan(true);
    refreshMusic(true);
  });
  // When the user comes back (e.g. from a Home Assistant setup screen opened
  // in another tab), re-check quietly; throttled, no background polling.
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refreshMusic(); });
  window.addEventListener("focus", () => refreshMusic());
  scan();
  const remembered = recall();
  if (remembered && OUTCOMES.some((o) => o.id === remembered && o.available)) select(remembered);
}

init();
