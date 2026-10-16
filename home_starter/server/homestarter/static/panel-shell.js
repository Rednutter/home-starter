const common = JSON.parse(variables.common_json);
const route = JSON.parse(variables.focus_json);
const scope = common.scopes?.[route.scope_key] || {};
const focus = {...scope,...route};
focus.controls = (scope.controls || focus.controls || []).filter(c=>!focus.control_ids || focus.control_ids.includes(c.entity_id));
focus.rooms = (scope.rooms || focus.rooms || []).map(r=>({...r,controls:r.controls || (scope.controls || []).filter(c=>r.control_ids?.includes(c.entity_id))}));
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const icon = name => `<ha-icon icon="${esc(name)}" aria-hidden="true"></ha-icon>`;
const get = id => id ? hass.states[id] : undefined;
const usable = s => s && !["unknown","unavailable"].includes(s.state);
const state = this._hsPage?.path === focus.path ? this._hsPage : (this._hsPage = {path:focus.path,destination:focus.default_destination,error:"",pending:false});
const viewer = common.kiosk_user_name && hass.user?.name === common.kiosk_user_name && !hass.user?.is_admin;
const kiosk = viewer && !new URLSearchParams(window.location.search).has("disable_km");
this.style.setProperty("--hs-chrome-height",kiosk ? "0px" : "56px");
const date = opts => new Intl.DateTimeFormat(hass.locale?.language || undefined,{timeZone:hass.config.time_zone,...opts}).format(new Date());
const link = (label,path,ico="mdi:arrow-right",cls="hs-action") => `<a class="${cls}" href="${esc(path)}">${icon(ico)}<span>${esc(label)}</span></a>`;
const navigate = event => {
  event.stopPropagation();
  const path = event.target.closest?.("a[href]")?.getAttribute("href");
  if (!path || !(path.startsWith(common.base+"/") || focus.kind === "settings" && ["/profile","/lovelace/0?disable_km"].includes(path)) || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();helpers.runAction({action:"navigate",navigation_path:path});
};
const stop = event => event.stopPropagation();
const wrap = body => html`<div @click=${navigate} @mousedown=${stop} @touchstart=${stop} @touchend=${stop} .innerHTML=${body}></div>`;
const safety = () => (common.alerts || []).filter(i=>{
 const s=get(i.entity_id);return usable(s) && (i.domain === "alarm_control_panel" ? s.state === "triggered" : i.domain === "event" ? Date.now()-Date.parse(s.state)>=0 && Date.now()-Date.parse(s.state)<120000 : s.state === "on");
}).map(i=>`<aside class="hs-alert" role="alert">${icon("mdi:alert")}<span>${esc(i.name)} needs attention</span></aside>`).join("");
const header = () => {
  if(focus.kind === "dark") return wrap(safety());
  const weather = get(common.weather), temp = usable(weather) && typeof weather.attributes.temperature === "number" ? weather.attributes.temperature : null;
  return wrap(`${safety()}<div class="hs-focus-top"><header class="hs-header"><div><time class="hs-time">${esc(date({hour:"numeric",minute:"2-digit"}))}</time><span class="hs-date">${esc(date({weekday:"short",day:"numeric",month:"short"}))}</span></div>${temp !== null ? `<span class="hs-weather">${icon("mdi:weather-partly-cloudy")}${esc(temp)}°</span>` : ""}</header><div class="hs-page-heading">${link("Back",focus.back,"mdi:arrow-left","hs-back")}<div><h1>${esc(focus.title)}</h1>${focus.owner ? '<p class="hs-subtitle">Personal view · shared panel</p>' : ""}</div>${focus.back !== common.base+"/home" ? link("House",common.base+"/home","mdi:home-outline","hs-house-return") : ""}</div></div>`);
};
const footer = () => focus.kind === "dark" ? wrap("") : wrap(`<footer class="hs-nav"><nav class="hs-household" aria-label="Household">${common.people.map(p=>`<a href="${esc(p.path)}"${focus.owner && p.path === common.base+"/person-"+Array.from(new TextEncoder().encode(focus.owner),b=>b.toString(16).padStart(2,"0")).join("") ? ' aria-current="page"' : !focus.owner && p.path === common.base+"/home" ? ' aria-current="page"' : ""}>${icon(p.icon)}<span>${esc(p.name)}</span></a>`).join("")}</nav><div class="hs-utilities" role="group" aria-label="Display">${link("Ambient",common.base+"/ambient","mdi:weather-night","hs-display")}${common.kiosk_user_name ? link("Settings",common.base+"/settings","mdi:cog-outline","hs-display") : ""}</div></footer>`);
