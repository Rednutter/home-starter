// The MA API connection is separate from provider accounts; never persist it in the browser.
export function musicRuntime({ h, api, navigateHA }, openPath = "/config/apps") {
  const root = h("div", { class: "music-runtime" });
  const notice = h("p", { role: "status", tabindex: "-1" }, "Reading music sources and speakers…");
  let data, busy = false, providerId = "", playerId = "";
  const button = (text, run) => h("button", { type: "button", class: "btn", disabled: busy, onclick: run }, text);
  const field = (label, input) => h("label", { class: "screen-field" }, h("span", {}, label), input);
  const choice = (label, items, value, change) => {
    const input = h("select", { "aria-label": label, disabled: busy, onchange: e => change(e.target.value) },
      h("option", { value: "" }, "Choose"), items.map(p => h("option", { value: p.id }, p.name)));
    input.value = value;
    return field(label, input);
  };
  async function load() {
    busy = true; render(); notice.textContent = "Reading music sources and speakers…";
    try {
      data = await api("api/music/runtime");
      notice.textContent = data.connected ? "Music sources and speakers checked. Review playback verification below." : "Connect Music Assistant to inspect its sources and speakers.";
    }
    catch (error) { data = { connected: false }; render(); notice.textContent = error.message; }
    finally { busy = false; render(); }
  }
  async function act(action, body) {
    busy = true; render(); notice.textContent = action === "observe" ? "Watching this speaker for fresh playback progress…" : "Checking Music Assistant…";
    try {
      const result = await api("api/music/runtime/" + action, { method: "POST", body: JSON.stringify(body) });
      if (action === "observe") { await load(); notice.textContent = result.detail; }
      else { data = result; render(); notice.textContent = action === "heard" ? "Playback verified for this source and speaker. Other paths remain untested." : action === "decline" ? "Audible playback remains unverified. Check the speaker in Music Assistant, then retry." : "Music Assistant connected. Review the sources below."; }
    } catch (error) { notice.textContent = error.message; }
    finally { busy = false; render(); notice.focus(); }
  }
  function render() {
    const providers = data?.providers || [], players = data?.players || [];
    const proof = data?.proof, pending = data?.pending;
    const providerName = id => providers.find(p => p.id === id)?.name || "the selected source";
    const playerName = id => players.find(p => p.id === id)?.name || "the selected speaker";
    const token = h("input", { type: "password", autocomplete: "off", spellcheck: "false", "aria-label": "Music Assistant API token", disabled: busy });
    const connection = h("details", { open: !data?.connected }, h("summary", {}, data?.connected ? "Music Assistant connection" : "Connect to Music Assistant"),
      h("p", {}, "In Music Assistant, open Settings → Profile and create an API token. Paste that token here. Home Starter stores it privately on this device and uses read commands to inspect sources, speakers and playback. Keep provider passwords in Music Assistant."),
      field("Music Assistant API token", token),
      button(data?.connected ? "Replace API connection" : "Connect Music Assistant", () => { const value = token.value; token.value = ""; return act("connect", { token: value }); }));
    const desired = h("select", { "aria-label": "Source to set up" }, ["Choose a source", "Spotify", "Apple Music", "Local music", "Radio", "Podcasts", "Other"].map(name => h("option", {}, name)));
    const guide = h("p", {}, "Select the source you want to add or repair. Existing providers are preserved.");
    desired.addEventListener("change", () => {
      guide.textContent = desired.selectedIndex === 0 ? "Select the source you want to add or repair. Existing providers are preserved."
        : `For ${desired.value}, open Music Assistant → Settings → Music sources → Add a music source. If it is already listed, inspect that source instead of adding a duplicate. Availability and sign-in requirements depend on MA support. Complete sign-in there, then return and refresh sources here.`;
    });
    root.replaceChildren(...[h("h3", {}, "Sources and speaker playback"), notice,
      proof ? h("p", {}, h("strong", {}, `Playback verified: ${providerName(proof.provider_id)} on ${playerName(proof.player_id)}. `), proof.progress_verified === false ? "You confirmed hearing it; automatic progress is unverified. " : "Device progress and hearing confirmed. ", `Checked ${new Date(proof.at).toLocaleString()}. This check expires after 24 hours; other sources and speakers remain untested.`)
        : h("p", {}, "Music is incomplete until a connected source plays on your chosen speaker and you confirm you heard it."),
      connection,
      h("h4", {}, "Connected music sources"),
      !data?.connected && h("p", {}, "Connect the API above to inspect actual providers. An installed app or Spotify Connect label does not establish a connected music library."),
      data?.connected && h("div", {},
        h("ul", { class: "plain" }, providers.map(p => h("li", {}, `${p.name} · ${p.status}${p.builtin ? " · built-in URL source; account setup unverified" : ""}`))),
        !providers.length && h("p", {}, "No loaded music providers found."),
        !data.configuration_known && h("p", {}, "Only loaded providers could be inspected. Disabled or failed provider configurations are unknown with this API token.")),
      h("details", {}, h("summary", {}, "Add or repair a music source"), field("Source to set up", desired), guide,
        button("Open Music Assistant", () => navigateHA(data?.open_path || openPath))),
      button("Refresh sources and speakers", load),
      data?.connected && h("div", {}, h("h4", {}, "Check one speaker"),
        choice("Music source to test", providers.filter(p => p.available && p.enabled && !p.builtin), providerId, value => providerId = value),
        choice("Speaker to test", players.filter(p => p.available && p.single), playerId, value => playerId = value),
        h("p", {}, "Open Music Assistant and play an item from the selected source on this speaker. Keep one item playing, then check it here. This observer leaves volume, queues, groups and provider settings unchanged. Grouped or unavailable speakers are excluded."),
        button("Open Music Assistant to play", () => navigateHA(data?.open_path || openPath)),
        button("Check selected speaker playback", () => {
          if (!providerId || !playerId) { notice.textContent = "Choose a connected music source and an available speaker first."; notice.focus(); return; }
          return act("observe", { provider_id: providerId, player_id: playerId });
        }),
        pending && h("div", {}, h("p", {}, `${pending.progress_verified === false ? "MA reports playback; automatic progress is unverified" : "Fresh playback progress observed"} from ${providerName(pending.provider_id)} on ${playerName(pending.player_id)}. Did you hear it?`),
          button("I heard it on this speaker", () => act("heard", { id: pending.id, confirm: true })),
          button("I could not hear it", () => act("decline", { id: pending.id, confirm: true }))))].filter(child => child != null && child !== false));
  }
  render();
  load();
  return root;
}
