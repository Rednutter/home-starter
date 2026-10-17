// One resumable connection view for commissioning and maintenance. No credentials.
import { mediaSetup } from "./media-setup.js";
export function connectionSetup({ h, api, navigateHA }) {
  const root = h("div", { class: "connection-setup" });
  const media = mediaSetup({ h, api });
  let data, busy = false, dirty = false, choices = {}, disposed = false, timer;
  const labels = { review: "Needs review", show: "Show at home", context: "Use for context", ignore: "Ignore" };
  const button = (label, action) => h("button", { class: "btn ghost", type: "button", disabled: busy, onclick: action }, label);
  const notice = h("p", { role: "status", class: "muted" }, "Checking household connections…");
  const previews = new Map();
  async function preview(row) {
    const content = h("div", { role: "status" }, "Reading this calendar…");
    previews.set(row.id, content); render();
    try {
      const result = await api("api/connections/preview", { method: "POST", body: JSON.stringify({ source: row.id }) });
      const date = value => {
        const raw = typeof value === "object" && value ? value.dateTime || value.date : value;
        if (!raw) return "Date unavailable";
        const parsed = new Date(raw);
        return Number.isNaN(parsed.valueOf()) ? "Date unavailable" : parsed.toLocaleString(undefined, { dateStyle: "medium", ...(String(raw).includes("T") ? { timeStyle: "short" } : {}) });
      };
      content.replaceChildren(h("p", { class: "small muted" }, result.detail), h("ul", {}, result.events.map(event => h("li", {}, h("strong", {}, event.title), " · " + date(event.start)))));
    } catch (error) { content.textContent = error.message; }
  }
  async function previewDuplicateFeeds() {
    const names = new Map();
    for (const row of data?.calendars.rows || []) names.set(row.name, (names.get(row.name) || 0) + 1);
    for (const row of data?.calendars.rows || []) {
      if (disposed || !root.isConnected || (root.contains(document.activeElement) && document.activeElement.tagName === "SELECT")) return;
      if (names.get(row.name) > 1 && !previews.has(row.id)) await preview(row);
    }
  }
  async function refresh(prepare = false) {
    if (busy || dirty || disposed || (root.contains(document.activeElement) && document.activeElement.tagName === "SELECT")) return;
    busy = true;
    try {
      data = await api(prepare ? "api/connections/prepare" : "api/connections", prepare ? { method: "POST", body: "{}" } : undefined);
      choices = { ...data.calendars.calendars };
      notice.textContent = "Connections checked. Sign-in stays with the service; checks resume here automatically.";
      if (["needs_review", "connected_but_incomplete"].includes(data.verification?.state)) {
        notice.textContent = data.verification.detail + " " + (data.verification.screens || []).join(". ");
      }
      document.dispatchEvent(new CustomEvent("home-starter-connections-checked", { detail: data }));
      render();
    } catch (error) { notice.textContent = error.message; }
    finally { busy = false; render(); }
    if (data) void previewDuplicateFeeds();
  }
  async function save() {
    if (busy) return;
    busy = true;
    try {
      const { version, epoch, revision } = data.calendars;
      data = await api("api/connections/calendars", { method: "POST", body: JSON.stringify({ version, epoch, revision, calendars: choices }) });
      dirty = false; choices = { ...data.calendars.calendars };
      notice.textContent = data.verification?.detail || "Calendar choices saved and connection checked. You can change them here without signing in again.";
      if (data.verification?.screens?.length) notice.textContent += " " + data.verification.screens.join(". ");
      document.dispatchEvent(new CustomEvent("home-starter-services-saved"));
      document.dispatchEvent(new CustomEvent("home-starter-connections-checked", { detail: data }));
    } catch (error) { notice.textContent = error.message; }
    finally { busy = false; render(); }
  }
  function render() {
    if (!data) { root.replaceChildren(notice); return; }
    const music = data.music, google = data.google, counts = data.calendars.counts;
    const duplicates = new Map();
    for (const row of data.calendars.rows) duplicates.set(row.name, (duplicates.get(row.name) || 0) + 1);
    const seen = new Map();
    root.replaceChildren(h("div", {}, notice,
      h("h3", {}, "Household connections"),
      h("p", {}, music.summary),
      music.connected !== undefined && h("p", {}, `Spotify: ${music.connected} connected · ${music.pending} pending`),
      music.allocator && h("p", {}, music.allocator.detail),
      ...(music.playback_checks || []).filter(row => row.state !== "connected").map(row => h("div", {},
        h("p", {}, `Spotify — ${row.name} is connected, but audio could not start.`),
        row.issue === "audio_key_unavailable" && h("p", {}, "Spotify rejected this account’s audio key. Complete Spotify Soloist playback setup for this existing account. The upstream download terms, API key and Spotify-app pairing require your consent."),
        button("Repair Spotify — " + row.name, () => {
          notice.textContent = row.issue === "audio_key_unavailable"
            ? `Music Assistant → Settings → Music Sources → open ${row.name} → run setup again → Spotify Soloist (official). Review the terms yourself, enter the API key in Music Assistant and pair your Spotify app as ${row.name}. Return here; existing household mappings are retained.`
            : `Music Assistant → Settings → Music Sources → open the existing ${row.name} account → check playback setup. Return here afterwards; the account and calendar mappings are retained.`;
          navigateHA(music.route || "/config/integrations/integration/music_assistant");
        }))),
      music.unmapped > 0 && h("p", {}, "Additional Spotify accounts need administrator review. Existing accounts are preserved."),
      ...music.spotify.filter(row => ["ready_for_authentication", "reauth_required"].includes(row.state)).map(row => button((row.state === "reauth_required" ? "Reconnect Spotify — " : "Connect Spotify — ") + row.name, async () => {
        try {
          if (row.state === "reauth_required") {
            notice.textContent = `Music Assistant → Settings → Music Sources → open the existing ${row.name} account → run setup again. Sign in as ${row.name}; your mappings are retained.`;
          } else {
            await api("api/connections/music", { method: "POST", body: JSON.stringify({ identity: row.name }) });
            notice.textContent = `Music Assistant → Settings → Music Sources → Add a music source → Spotify. Sign in as ${row.name}; we will complete the mapping when you return.`;
          }
          navigateHA(music.route || "/config/integrations/integration/music_assistant");
        } catch (error) { notice.textContent = error.message; }
      })),
      h("h3", {}, "Google Calendar"), h("p", {}, google.detail),
      google.state !== "connected" && button("Continue Google Calendar setup", () => navigateHA(google.route)),
      h("details", {}, h("summary", {}, "Google setup and connection recovery"),
        h("ol", {}, google.guide.map(text => h("li", {}, text))),
        h("p", {}, "A saved client is checked by a successful connection. Home Starter cannot inspect Google Cloud publication or Branding without your authorization."),
        h("label", {}, "What does the sign-in page say?", h("select", { "aria-label": "Google sign-in issue", onchange: e => {
          const messages = {
            invalid_client: "401 invalid_client: replace bad, missing or stale Google Application credentials in HA, using your current Web application client.",
            testing: "403 access_denied / Testing: Google Auth Platform → Audience → Publish app → In production. Complete required Branding first. Reconnect for durable authorization.",
            branding: "Complete the fields marked required under Google Auth Platform → Branding, then publish under Audience.",
            redirect: "redirect_uri_mismatch: use the exact redirect shown by HA. Standard value: " + google.redirect_uri,
            api: "Enable Google Calendar API under APIs & Services → Library in the client's project.",
            revoked: "Expired or revoked authorization: re-authenticate the existing Google integration. Calendar choices will be retained."
          };
          notice.textContent = messages[e.target.value] || google.detail;
        } }, h("option", { value: "" }, "Choose the error shown"), ...[["invalid_client", "Invalid client (401)"], ["testing", "Access denied / app in Testing (403)"], ["branding", "Cannot publish: Branding incomplete"], ["redirect", "Redirect URI mismatch"], ["api", "Calendar API disabled"], ["revoked", "Expired or revoked sign-in"]].map(([value, text]) => h("option", { value }, text))))),
      h("h3", {}, counts.review ? "Review calendars" : "Calendar visibility"),
      h("p", {}, `${counts.show} calendars shown at home · ${counts.context} context-only · ${counts.ignore} ignored` + (counts.review ? ` · ${counts.review} need review` : "")),
      h("p", {}, "Show at home appears on shared screens. Context stays hidden from shared screens. Ignore excludes the calendar. New calendars always need review."),
      counts.review > 0 && button("Use suggested choices for review", () => {
        for (const row of data.calendars.rows) if ((choices[row.id] || "review") === "review") choices[row.id] = row.suggested;
        dirty = true; notice.textContent = "Suggestions are ready to review below. Save calendar choices to confirm them."; render();
      }),
      ...data.calendars.rows.map(row => {
        const index = (seen.get(row.name) || 0) + 1; seen.set(row.name, index);
        const name = row.name + (duplicates.get(row.name) > 1 ? ` (${index} of ${duplicates.get(row.name)})` : "");
        return h("div", { class: "screen-field" }, h("label", {}, h("span", {}, name),
          h("select", { "aria-label": "Visibility for " + name, onchange: e => { choices[row.id] = e.target.value; dirty = true; notice.textContent = "Save calendar choices to confirm these changes."; } },
            Object.entries(labels).map(([value, text]) => h("option", { value, selected: (choices[row.id] || "review") === value }, text)))),
          row.source && h("p", { class: "small muted" }, [row.source.integration, row.source.account].filter(Boolean).join(" · ")),
          row.mode === "review" && h("p", { class: "small muted" }, "Suggested: " + labels[row.suggested] + ". " + row.reason),
          button("Preview upcoming events for " + name, () => preview(row)), previews.get(row.id),
          duplicates.get(row.name) > 1 && h("details", {}, h("summary", {}, "Identify this calendar"), h("p", {}, row.id)));
      }),
      data.calendars.rows.length > 0 && button("Save calendar choices", save), media,
      button("Check connections again", () => { if (dirty) { notice.textContent = "Save calendar choices before refreshing. Your edits are retained."; return; } refresh(true); }),
      h("details", {}, h("summary", {}, "Other readiness checks"), h("ul", {}, data.checks.map(row => h("li", {}, `${row.name}: ${row.state.replaceAll("_", " ")} · ${row.detail}`))))));
  }
  function resume() { if (!document.hidden && root.isConnected) refresh(true); }
  document.addEventListener("visibilitychange", resume);
  window.addEventListener("focus", resume);
  render(); refresh(true);
  timer = setInterval(() => {
    if (!root.isConnected) {
      disposed = true; clearInterval(timer); document.removeEventListener("visibilitychange", resume); window.removeEventListener("focus", resume); return;
    }
    if (!document.hidden && root.isConnected) refresh(true);
  }, 15000);
  return root;
}
