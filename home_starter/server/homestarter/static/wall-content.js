const cfg = JSON.parse(variables.wall_json);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const icon = name => `<ha-icon icon="${name}" aria-hidden="true"></ha-icon>`;
const get = id => id ? hass.states[id] : undefined;
const usable = s => s && !["unavailable","unknown"].includes(s.state);
const now = new Date();
const date = options => new Intl.DateTimeFormat(hass.locale?.language || "en-AU", {timeZone:hass.config.time_zone,...options}).format(now);
const attr = s => s?.attributes || {};
const projection = get(cfg.context), context = attr(projection), owner = context.home_starter_context;
const fresh = owner?.surface === cfg.surface_id && owner?.epoch === cfg.epoch &&
  now - new Date(context.checked_at) >= 0 && now - new Date(context.checked_at) < 180000 && new Date(context.valid_until) > now;
const rows = fresh && Array.isArray(context.briefing) ? context.briefing.filter(r => r && typeof r.title === "string") : [];
const pending = !fresh || /not selected|needs verification|unavailable|choose and verify/i.test(context.near || "");
const agenda = rows.filter(r => !(r.when === "This morning" && r.people?.length));
const today = agenda.filter(r => ["now","later_today"].includes(r.proximity));
const later = today.filter(r => r.proximity === "later_today").slice(-3);
const upcoming = later.length ? later : agenda.filter(r => !["now","later_today"].includes(r.proximity)).slice(0,3);
const todayLimit = window.innerHeight >= 900 ? 4 : 3;
const weather = get(cfg.weather), condition = usable(weather) ? weather.state.replaceAll("_"," ") : "Weather unavailable";
const weatherIcon = {sunny:"mdi:weather-sunny",clear_night:"mdi:weather-night",partlycloudy:"mdi:weather-partly-cloudy",cloudy:"mdi:weather-cloudy",rainy:"mdi:weather-rainy",pouring:"mdi:weather-pouring",fog:"mdi:weather-fog",windy:"mdi:weather-windy",lightning:"mdi:weather-lightning"}[weather?.state] || "mdi:weather-partly-cloudy";
const temperature = n => typeof n === "number" && Number.isFinite(n) ? `${esc(Math.round(n))}°` : "—";
const wind = attr(weather).wind_speed;
const weatherDetail = usable(weather) && typeof wind === "number" ? `Wind ${esc(Math.round(wind))} ${esc(attr(weather).wind_speed_unit || "")}` : "Current conditions";
const eventRow = (r, compact=false) => `<article class="wall-event${compact ? " wall-event-compact" : ""}"><time>${esc(r.when === "This morning" ? "Now" : r.when || "Today")}</time><span class="wall-event-dot" aria-hidden="true"></span><div><h3>${esc(r.title)}</h3>${r.detail && !compact ? `<p>${esc(r.detail)}</p>` : ""}</div></article>`;
const childCard = (child,index) => {
  const personal = child.native_id ? rows.filter(r => Array.isArray(r.people) && r.people.includes(child.native_id)) : [];
  const initials = child.name.trim().split(/\s+/).slice(0,2).map(s=>s[0]).join("");
  return `<article class="wall-child wall-child-${index%3}" aria-label="${esc(child.name)} plans"><header><span class="wall-avatar" aria-hidden="true">${esc(initials)}</span><div><h2>${esc(child.name)}</h2><p>School &amp; activities</p></div></header><div class="wall-child-plan">${personal.length ? personal.slice(0,3).map(r=>`<section><span class="wall-plan-icon">${icon(r.when === "This morning" ? "mdi:clipboard-check-outline" : "mdi:calendar-blank-outline")}</span><div><h3>${esc(r.title)}</h3><p>${esc(r.detail || r.when)}</p></div></section>`).join("") : `<section class="wall-plan-pending"><span class="wall-plan-icon">${icon("mdi:calendar-blank-outline")}</span><div><h3>Plans to come</h3><p>${pending ? "Calendar connection pending" : "No shared plans for today"}</p></div></section><p class="wall-child-note">${pending ? "Morning reminders will appear here once they’re added." : "Enjoy the quieter day."}</p>`}</div></article>`;
};
const climate = get(cfg.climate), climateOnline = usable(climate);
const climateMode = climateOnline ? climate.state === "off" ? "Off" : ({cooling:"Cooling",heating:"Heating",idle:"Idle",fan:"Fan only"}[attr(climate).hvac_action] || climate.state.replaceAll("_"," ")) : "Not selected";
const lights = cfg.lights.map(get), lightsOn = lights.filter(s=>s?.state === "on").length;
const security = cfg.security.map(get).find(usable);
const endpoint = get(cfg.endpoint), health = attr(endpoint);
const endpointFresh = new Date(health.valid_until) > now && health.home_starter_endpoint?.epoch === cfg.epoch && endpoint?.state === "online";
const voice = endpointFresh && health.voice_connected ? health.voice_muted ? "Microphone muted" : "Listening" : "Not connected";
const alerts = cfg.alerts.filter(a=>a.alarm ? get(a.entity)?.state === "triggered" : get(a.entity)?.state === "on");
const kiosk = new URLSearchParams(window.location.search).has("kiosk") && !new URLSearchParams(window.location.search).has("disable_km");
const metric = (title,ico,value,detail="") => `<section class="wall-metric"><span>${icon(ico)}</span><div><h3>${esc(title)}</h3><strong>${esc(value)}</strong>${detail ? `<p>${esc(detail)}</p>` : ""}</div></section>`;
const body = `<main class="hs-wall" style="--wall-chrome:${kiosk ? 0 : 56}px" aria-label="${esc(cfg.title)} family display">
${alerts.length ? `<aside class="wall-alert" role="alert">${icon("mdi:alert")} ${alerts.map(a=>esc(a.name)+" needs attention").join(" · ")}</aside>` : ""}
<div class="wall-upper"><section class="wall-family"><header class="wall-hero"><div class="wall-clock"><time>${esc(date({hour:"numeric",minute:"2-digit",hour12:false}))}</time><p>${esc(date({weekday:"short",day:"numeric",month:"short"}))}</p></div><section class="wall-weather" aria-label="Current weather"><div>${icon(weatherIcon)}<strong>${usable(weather) ? temperature(attr(weather).temperature) : "—"}</strong></div><h2>${esc(condition)}</h2><p>${weatherDetail}</p></section></header>
<section class="wall-children" style="--wall-child-count:${Math.max(1,Math.min(3,cfg.children.length))}" aria-label="Children’s plans">${cfg.children.length ? cfg.children.map(childCard).join("") : `<article class="wall-child wall-child-1"><h2>Household plans</h2><p>Shared reminders will appear here.</p></article>`}</section></section>
<aside class="wall-agenda" aria-label="Household schedule"><section class="wall-today wall-surface"><header><h2>Today</h2><span>${esc(date({weekday:"short",day:"numeric",month:"short"}))}</span></header><div class="wall-timeline">${today.length ? today.slice(0,todayLimit).map(r=>eventRow(r)).join("") : `<div class="wall-agenda-empty">${icon("mdi:calendar-blank-outline")}<h3>${pending ? "Your family schedule" : "A quieter day"}</h3><p>${pending ? "Connect your household calendar to bring today’s plans together." : "No more shared commitments today."}</p></div>`}</div></section>
<section class="wall-later wall-surface"><header><h2>${later.length ? "Later today" : "Coming up"}</h2></header>${upcoming.length ? upcoming.map(r=>eventRow(r,true)).join("") : `<p class="wall-later-empty">${pending ? "Upcoming plans will appear after calendar setup." : "Nothing else on the shared calendar."}</p>`}</section></aside></div>
<footer class="wall-footer"><section class="wall-house wall-surface" aria-label="Household status"><div class="wall-home-mark">${icon("mdi:home")}<span>Home</span></div>${metric("Climate","mdi:thermometer",climateOnline ? temperature(attr(climate).current_temperature ?? attr(climate).temperature) : "—",climateMode)}${metric("Security","mdi:lock-outline",security ? security.state.replaceAll("_"," ") : "—",security ? "" : "Not shared")}${metric("Lights","mdi:lightbulb-outline",lights.length ? `${lightsOn} on` : "Not selected")}${metric("Voice","mdi:microphone-outline","Hey Jarvis",voice)}</section><section class="wall-cameras wall-surface"><span class="wall-camera-mark">${icon("mdi:cctv")}</span><div><h2>Cameras</h2><p>Camera views aren’t connected yet</p><span>Feeds will appear here once selected and checked.</span></div></section></footer></main>`;
return html`<div class="wall-wrapper" .innerHTML=${body}></div>`;
