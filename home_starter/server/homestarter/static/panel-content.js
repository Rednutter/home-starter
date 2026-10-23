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
const operating = online && climate.state !== "off" && ["cooling","heating","fan","drying","defrosting","preheating"].includes(climate.attributes.hvac_action);
const mode = online ? (climate.state === "off" ? "Off" : {off:"Off",idle:"Idle",cooling:"Cooling",heating:"Heating",fan:"Fan only",drying:"Drying",defrosting:"Defrosting",preheating:"Preheating"}[climate.attributes.hvac_action] || {cool:"Cool mode",heat:"Heat mode",fan_only:"Fan mode",auto:"Auto mode",dry:"Dry mode"}[climate.state] || climate.state) : "Connection unavailable";
const zones = cfg.zones.map(get).filter(usable);
const enabledZones = zones.filter(s=>s.state !== "off").length;
const zoneText = !cfg.zones.length ? "" : !zones.length ? "Zone status unavailable" : zones.length === cfg.zones.length ? `${enabledZones} of ${cfg.zones.length} zones enabled` : `${enabledZones} enabled · ${zones.length} of ${cfg.zones.length} zones reporting`;
const weather = get(cfg.weather);
const weatherText = usable(weather) ? temperature(weather.attributes.temperature) : "";
const binSource = cfg.bins ? get("sensor.home_starter_bin_source") : undefined;
const binFresh = binSource && new Date(binSource.attributes.valid_until) > now;
const binText = cfg.bins && !binFresh ? "Bin schedule needs checking" : binFresh && binSource.attributes.attention !== "quiet" ? binSource.attributes.summary : "";
let overview={};try{const value=cfg.summary_json ? JSON.parse(cfg.summary_json):{};if(value && typeof value==="object" && !Array.isArray(value))overview=value;}catch{ /* A broken summary must not break climate or navigation. */ }
const contextSource=get(overview.context_entity), contextAttrs=contextSource?.attributes || {}, contextProof=contextAttrs.home_starter_context;
const freshContext=usable(contextSource) && contextProof?.surface===overview.surface_id && contextProof.epoch===overview.epoch && contextProof.person_id==null && now<Date.parse(contextAttrs.valid_until) && Date.now()-Date.parse(contextAttrs.checked_at)>=0 && Date.now()-Date.parse(contextAttrs.checked_at)<180000;
const lead=freshContext && Array.isArray(contextAttrs.briefing) ? contextAttrs.briefing[0]:null;
const event = !overview.context_entity ? cfg.calendars.map(get).filter(s=>usable(s) && s.attributes.message && Number.isFinite(Date.parse(s.attributes.start_time)) && Date.parse(s.attributes.end_time)>now).sort((a,b)=>Date.parse(a.attributes.start_time)-Date.parse(b.attributes.start_time))[0]:null;
const projected = feature => {
 const binding=overview.bindings?.[feature], source=get(binding?.entity_id), a=source?.attributes || {}, proof=a.home_starter_capability;
 return binding && usable(source) && proof?.surface===overview.surface_id && proof.epoch===overview.epoch && proof.person_id==null && proof.feature===feature && proof.revision===binding.revision && now<Date.parse(a.valid_until) && Date.now()-Date.parse(a.checked_at)>=0 && Date.now()-Date.parse(a.checked_at)<180000 && a.value && typeof a.value==="object" && !Array.isArray(a.value) ? a.value:null;
};
const cameraState=projected("camera"), selectedCameras=Array.isArray(overview.bindings?.camera?.cameras) ? overview.bindings.camera.cameras.filter(c=>c && typeof c.entity_id==="string"):[];
const reportingCameras=selectedCameras.filter(c=>usable(get(c.entity_id))).length;
const cameraText=!overview.bindings?.camera ? "Not selected":!cameraState ? "Camera status unavailable":`${selectedCameras.length} ${selectedCameras.length===1 ? "camera":"cameras"} selected`;
const cameraDetail=cameraState ? `${reportingCameras} reporting · Open cameras to view`:overview.bindings?.camera ? "Open cameras to check":"Camera setup still needed";
const callState=projected("call");
const callText=!overview.bindings?.call ? "Not commissioned":!callState ? "Calling unavailable":({incoming:"Incoming call",active:"In call",dialing:"Calling"}[callState.state] || (Array.isArray(callState.destinations) && callState.destinations.length ? "Ready":"No destinations"));
const callDetail=callState ? callState.label || "Open calling":overview.bindings?.call ? "Open calling to check":"Calling setup still needed";

const todayText = binText || (lead?.title || (event ? event.attributes.message : freshContext && contextSource.state==="current" ? "Nothing upcoming in selected sources" : freshContext && contextSource.state==="attention" ? "Today sources need checking" : "No verified commitments to show"));
const media = cfg.media.map(get).find(s=>usable(s) && s.state === "playing") || cfg.media.map(get).find(usable);
const lightStates = cfg.lights.map(get), lightsOn = lightStates.filter(s=>s?.state === "on").length;
const missingLights=lightStates.filter(s=>!usable(s)).length;
const homeText = !cfg.lights.length ? "Rooms and household controls":missingLights===cfg.lights.length ? "Lighting status unavailable":missingLights ? `${lightsOn} lights on · ${missingLights} unavailable`:`${lightsOn} of ${cfg.lights.length} lights on`;
const safeMediaText=value=>typeof value==="string" && !/^(?:asset\s+(?:stop|start|end|link)\b[\s:|_-]*(?:\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}T)|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$|Home Starter source:)/i.test(value.trim()) && !value.includes("://") ? value.trim():"";
const mediaText=media ? safeMediaText(media.attributes.media_title) || safeMediaText(media.attributes.media_channel) || ({playing:"Playing audio",paused:"Paused",idle:"Ready",off:"Off"}[media.state] || media.state):"Choose a room speaker";
const tile = (kind,title,ico,body,detail,target,setup=false) => {
  const tag = target ? "a" : "section";
  return `<${tag} class="hs-tile hs-${kind}${setup ? " hs-setup" : ""}${target ? " hs-link" : ""}"${target ? ` href="${esc(target)}"` : ""} aria-label="${esc(title)}">
    <h2>${icon(ico)}${esc(title)}</h2><div class="hs-tile-copy"><div class="hs-body">${esc(body)}</div>${detail ? `<div class="hs-detail">${esc(detail)}</div>` : ""}</div>
    ${target ? `<span class="hs-open" aria-hidden="true">${icon("mdi:arrow-top-right")}</span>` : ""}</${tag}>`;
};
const alert = cfg.alerts.map(get).find(s=>s?.state === "on");
const climateTag = cfg.targets.climate ? "a" : "section";
const body = `<main class="hs-panel" style="${decorationStyle(now,hass.config.time_zone,cfg.base)};--hs-chrome-height:${kioskActive ? 0 : 56}px" aria-label="${esc(cfg.title)}">
  <header class="hs-header"><div><time class="hs-time">${esc(date({hour:"numeric",minute:"2-digit"}))}</time><span class="hs-date">${esc(date({weekday:"short",day:"numeric",month:"short"}))}</span></div>${weatherText ? `<span class="hs-weather">${icon("mdi:weather-partly-cloudy")}${weatherText}</span>` : ""}</header>
  ${alert ? `<aside class="hs-alert" role="alert">${icon("mdi:alert")} ${esc(alert.attributes.friendly_name)} needs attention</aside>` : ""}
  <div class="hs-board">
    <${climateTag} class="hs-tile hs-climate${operating ? " hs-operating" : ""}${cfg.targets.climate ? " hs-link" : ""}"${cfg.targets.climate ? ` href="${esc(cfg.targets.climate)}" aria-label="Open climate controls"` : ' aria-label="Climate not configured"'}>
      <h2>${icon("mdi:snowflake")}Climate</h2><div class="hs-temperature">${online ? temperature(climate.attributes.temperature) : "—"}</div>
      <div class="hs-mode">${esc(mode)}</div><div class="hs-climate-detail">${online && typeof climate.attributes.current_temperature === "number" ? `Currently ${temperature(climate.attributes.current_temperature)}` : "Live temperature not reporting"}${zoneText ? `<br>${esc(zoneText)}` : ""}</div>
      <span class="hs-climate-action">${cfg.targets.climate ? `Climate controls ${icon("mdi:arrow-right")}` : "Climate setup still needed"}</span>
    </${climateTag}>
    ${tile("today", binText?.startsWith("Bins tonight") ? "Bins tonight" : binText?.startsWith("Bins out") ? "Bins this morning" : "Today", "mdi:calendar-blank-outline",todayText,lead && !binText ? (contextSource.state==="attention" ? "Some Today sources need checking" : lead.when || "Next"):event && !binText ? "Household calendar" : binText ? "Household collection service" : "Selected household sources",cfg.targets.today || cfg.targets.context,!binText && !event && !lead)}
    ${tile("call","Call","mdi:phone-outline",callText,callDetail,cfg.targets.call,!callState)}
    ${tile("cameras","Cameras","mdi:cctv",cameraText,cameraDetail,cfg.targets.cameras,!cameraState)}
    ${tile("media","Media","mdi:music",media ? media.attributes.friendly_name : "No speaker selected",mediaText,cfg.targets.music,!media)}
    ${tile("home","Home","mdi:home-outline",homeText,lightStates.some(s=>!usable(s)) ? "Some lights are unavailable" : "Open rooms and controls",cfg.targets.rooms || cfg.targets.context)}
  </div>
  <footer class="hs-nav"><nav class="hs-household" aria-label="Household">${cfg.people.map(p=>`<a href="${esc(p.path)}"${p.path === cfg.path ? ' aria-current="page"' : ""}>${icon(p.icon)}<span>${esc(p.name)}</span></a>`).join("")}</nav><div class="hs-utilities" role="group" aria-label="Display"><a class="hs-display" href="${esc(cfg.base)}/ambient" aria-label="Ambient" title="Ambient display">${icon("mdi:weather-night")}<span class="hs-sr-only">Ambient</span></a>${cfg.kiosk_user_name ? `<a class="hs-display" href="${esc(cfg.base)}/${displayViewer && escapedKiosk ? "home" : "settings"}" aria-label="${displayViewer && escapedKiosk ? "Panel mode" : "Settings"}" title="${displayViewer && escapedKiosk ? "Panel mode" : "Settings"}">${icon(displayViewer && escapedKiosk ? "mdi:fullscreen" : "mdi:cog-outline")}<span class="hs-sr-only">${displayViewer && escapedKiosk ? "Panel mode" : "Settings"}</span></a>` : ""}</div></footer>
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
