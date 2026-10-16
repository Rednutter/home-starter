const cfg = variables.panel;
const displayViewer = !!cfg.kiosk_user_name && hass.user?.name === cfg.kiosk_user_name && !hass.user?.is_admin;
const escapedKiosk = displayViewer && new URLSearchParams(window.location.search).has("disable_km");
const kioskActive = displayViewer && !escapedKiosk;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const get = id => id ? hass.states[id] : undefined;
const usable = state => state && !["unknown", "unavailable"].includes(state.state);
const icon = name => `<ha-icon icon="${name}" aria-hidden="true"></ha-icon>`;
const now = new Date();
const locale = hass.locale?.language || undefined;
const date = options => new Intl.DateTimeFormat(locale, {timeZone:hass.config.time_zone, ...options}).format(now);
const temperature = value => typeof value === "number" && Number.isFinite(value) ? `${esc(value)}°` : "—";
const climate = get(cfg.climate), online = usable(climate);
const mode = online ? ({off:"Off",idle:"Idle",cooling:"Cooling",heating:"Heating",fan:"Fan only",drying:"Drying",defrosting:"Defrosting",preheating:"Preheating"}[climate.attributes.hvac_action] || {off:"Off",cool:"Cool mode",heat:"Heat mode",fan_only:"Fan mode",auto:"Auto mode",dry:"Dry mode"}[climate.state] || climate.state) : "Connection unavailable";
const zones = cfg.zones.map(get).filter(usable);
const activeZones = zones.filter(s=>s.state !== "off").length;
const zoneText = cfg.zones.length ? `${activeZones} of ${cfg.zones.length} zones on${zones.length < cfg.zones.length ? " · some unavailable" : ""}` : "";
const weather = get(cfg.weather);
const weatherText = usable(weather) ? temperature(weather.attributes.temperature) : "";
const binSource = cfg.bins ? get("sensor.home_starter_bin_source") : undefined;
const binFresh = binSource && new Date(binSource.attributes.valid_until) > now;
const binText = cfg.bins && !binFresh ? "Bin schedule needs checking" : binFresh && binSource.attributes.attention !== "quiet" ? binSource.attributes.summary : "";
const event = cfg.calendars.map(get).find(s=>usable(s) && s.attributes.message && s.attributes.start_time);
const todayText = binText || (event ? event.attributes.message : "No verified commitments to show");
const media = cfg.media.map(get).find(s=>usable(s) && s.state === "playing") || cfg.media.map(get).find(usable);
const lightStates = cfg.lights.map(get), lightsOn = lightStates.filter(s=>s?.state === "on").length;
const homeText = cfg.lights.length ? `${lightsOn} of ${cfg.lights.length} lights on` : "Rooms and household controls";
const tile = (kind,title,ico,body,detail,target) => {
  const tag = target ? "a" : "section";
  return `<${tag} class="hs-tile hs-${kind}${target ? " hs-link" : ""}"${target ? ` href="${esc(target)}"` : ""} aria-label="${esc(title)}">
    <h2>${icon(ico)}${esc(title)}</h2><div class="hs-tile-copy"><div class="hs-body">${esc(body)}</div>${detail ? `<div class="hs-detail">${esc(detail)}</div>` : ""}</div>
    ${target ? `<span class="hs-open" aria-hidden="true">${icon("mdi:arrow-top-right")}</span>` : ""}</${tag}>`;
};
const alert = cfg.alerts.map(get).find(s=>s?.state === "on");
const climateTag = cfg.targets.climate ? "a" : "section";
const body = `<main class="hs-panel" style="--hs-chrome-height:${kioskActive ? 0 : 56}px" aria-label="${esc(cfg.title)}">
  <header class="hs-header"><div><time class="hs-time">${esc(date({hour:"numeric",minute:"2-digit"}))}</time><span class="hs-date">${esc(date({weekday:"short",day:"numeric",month:"short"}))}</span></div>${weatherText ? `<span class="hs-weather">${icon("mdi:weather-partly-cloudy")}${weatherText}</span>` : ""}</header>
  ${alert ? `<aside class="hs-alert" role="alert">${icon("mdi:alert")} ${esc(alert.attributes.friendly_name)} needs attention</aside>` : ""}
  <div class="hs-board">
    <${climateTag} class="hs-tile hs-climate${cfg.targets.climate ? " hs-link" : ""}"${cfg.targets.climate ? ` href="${esc(cfg.targets.climate)}" aria-label="Open climate controls"` : ' aria-label="Climate not configured"'}>
      <h2>${icon("mdi:snowflake")}Climate</h2><div class="hs-temperature">${online ? temperature(climate.attributes.temperature) : "—"}</div>
      <div class="hs-mode">${esc(mode)}</div><div class="hs-climate-detail">${online && typeof climate.attributes.current_temperature === "number" ? `Currently ${temperature(climate.attributes.current_temperature)}` : "Live temperature not reporting"}${zoneText ? `<br>${esc(zoneText)}` : ""}</div>
      <span class="hs-climate-action">${cfg.targets.climate ? `Climate controls ${icon("mdi:arrow-right")}` : "Climate setup still needed"}</span>
    </${climateTag}>
    ${tile("today", binText?.startsWith("Bins tonight") ? "Bins tonight" : binText?.startsWith("Bins out") ? "Bins this morning" : "Today", "mdi:calendar-blank-outline",todayText,event && !binText ? "Household calendar" : binText ? "Household collection service" : "Selected household sources",cfg.targets.today || cfg.targets.context)}
    ${tile("call","Call","mdi:phone-outline","Not commissioned","Calling setup still needed",cfg.targets.call)}
    ${tile("cameras","Cameras","mdi:cctv","Not selected","Camera setup still needed",cfg.targets.cameras)}
    ${tile("media","Media","mdi:music",media ? media.attributes.friendly_name : "No speaker selected",media ? media.attributes.media_title || ({playing:"Playing",paused:"Paused",idle:"Ready",off:"Off"}[media.state] || media.state) : "Choose a room speaker in setup",cfg.targets.music)}
    ${tile("home","Home","mdi:home-outline",homeText,lightStates.some(s=>!usable(s)) ? "Some lights are unavailable" : "Open rooms and controls",cfg.targets.rooms || cfg.targets.context)}
  </div>
  <nav class="hs-nav" aria-label="Household">${cfg.people.map(p=>`<a href="${esc(p.path)}"${p.path === cfg.path ? ' aria-current="page"' : ""}>${icon(p.icon)}<span>${esc(p.name)}</span></a>`).join("")}<a class="hs-display" href="${esc(cfg.base)}/ambient">${icon("mdi:weather-night")}<span>Ambient</span></a>${cfg.kiosk_user_name ? `<a class="hs-display" href="${esc(cfg.base)}/${displayViewer && escapedKiosk ? "home" : "settings"}">${icon(displayViewer && escapedKiosk ? "mdi:fullscreen" : "mdi:cog-outline")}<span>${displayViewer && escapedKiosk ? "Panel mode" : "Settings"}</span></a>` : ""}</nav>
</main>`;
// Use HA navigation: ordinary anchor loads can leave the Android companion app.
const stop = event => event.stopPropagation();
const navigate = event => {
  stop(event);
  const path = event.target.closest?.("a[href]")?.getAttribute("href");
  if (!path?.startsWith(cfg.base + "/") || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  helpers.runAction({action:"navigate", navigation_path:path});
};
return html`<div class="hs-wrapper" @click=${navigate} @mousedown=${stop} @touchstart=${stop} @touchend=${stop} .innerHTML=${body}></div>`;
