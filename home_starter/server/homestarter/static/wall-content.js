const cfg = JSON.parse(variables.wall_json);
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const icon = name => `<ha-icon icon="${name}" aria-hidden="true"></ha-icon>`;
const now = new Date();
const date = options => new Intl.DateTimeFormat(hass.locale?.language || "en-AU", {timeZone:hass.config.time_zone,...options}).format(now);
const context = hass.states[cfg.context]?.attributes || {}, owner=context.home_starter_context;
const board=context.wall;
const fresh=hass.connected !== false && owner?.surface===cfg.surface_id && owner?.epoch===cfg.epoch &&
 now-new Date(context.checked_at)>=0 && now-new Date(context.checked_at)<180000 && new Date(context.valid_until)>now &&
 board?.version===1 && new Date(board.valid_until)>now;
const model=fresh?board:{day_state:"disconnected",day_summary:"Household context unavailable",primary:"quiet",today_items:[],future_attention:[],household_exception:[],active_context:[],issues:[]};
const alive=r=>!r.ends_at || new Date(r.ends_at)>now;
const valid=r=>!r.expires_at || new Date(r.expires_at)>now;
const capacity=window.innerHeight<900?2:4;
const today=(model.today_items || []).filter(alive).slice(0,capacity), future=(model.future_attention || []).filter(alive).slice(0,window.innerHeight<900?3:5);
const exceptions=(model.household_exception || []).filter(valid), active=(model.active_context || []).filter(valid);
const movement=model.next_movement && alive(model.next_movement) ? model.next_movement : null;
const session=model.display_session && valid(model.display_session) ? model.display_session : null;
const people=r=>Array.isArray(r.people)&&r.people.length?`<span class="wall-people">${esc(r.people.join(" Ã‚Â· "))}</span>`:"";
const row=r=>`<article class="wall-item"><time>${esc(r.when)}</time><div><h3>${esc(r.title)}</h3>${people(r)}${r.location?`<p>${esc(r.location)}</p>`:""}${r.detail?`<strong class="wall-departure">${esc(r.detail)}</strong>`:""}</div></article>`;
const weather=model.weather;
const weatherIcon={sunny:"mdi:weather-sunny","clear night":"mdi:weather-night",rainy:"mdi:weather-rainy",pouring:"mdi:weather-pouring",cloudy:"mdi:weather-cloudy",partlycloudy:"mdi:weather-partly-cloudy"}[weather?.condition] || "mdi:weather-partly-cloudy";
const ordinaryWeather=weather&&model.baseline_state!=="overnight"?`<section class="wall-weather" aria-label="Current conditions">${icon(weatherIcon)}<div><strong>${typeof weather.temperature==="number"&&Number.isFinite(weather.temperature)?esc(Math.round(weather.temperature))+" "+esc(weather.unit):esc(weather.condition)}</strong><p>${esc(weather.condition)}</p></div></section>`:"";
const cue=movement?`<section class="wall-movement" aria-label="Next movement"><h2>${esc(movement.label)}</h2><h3>${esc(movement.title)}</h3>${people(movement)}${movement.location?`<p>${esc(movement.location)}</p>`:""}<strong>${esc(movement.detail)}</strong></section>`:"";
const alerts=exceptions.length?`<section class="wall-exceptions" aria-label="Needs attention">${exceptions.map(r=>`<article><span>${icon(r.kind==="weather"?"mdi:weather-rainy":r.kind==="bins"?"mdi:trash-can-outline":"mdi:alert-circle-outline")}</span><div><h2>${esc(r.title)}</h2><p>${esc(r.detail)}</p></div></article>`).join("")}</section>`:"";
const current=today.length?`<section class="wall-today wall-surface"><h2>Today</h2>${today.filter(r=>!movement || r.id!==movement.id).map(row).join("")}${today.every(r=>movement&&r.id===movement.id)?`<p class="wall-quiet-note">ThatÃ¢â‚¬â„¢s the next commitment.</p>`:""}</section>`:"";
const next=future.length?`<section class="wall-upcoming wall-surface"><h2>${model.baseline_state==="evening"||model.baseline_state==="overnight"?"Tomorrow & coming up":"Coming up"}</h2>${future.map(row).join("")}</section>`:"";
const quiet=!movement&&!today.length?`<section class="wall-quiet"><h2>${esc(model.day_summary)}</h2><p>${!fresh?"Waiting for a fresh Home Assistant update. Old plans are hidden.":future.length?"A little room to look ahead.":model.issues?.length?"Connect the household calendar in Home Starter to bring shared plans here.":"Nothing else needs your attention."}</p></section>`:"";
const strip=active.length?`<footer class="wall-context" aria-label="Active household context">${active.map(r=>`<section>${icon(r.kind==="timer"?"mdi:timer-outline":r.kind==="media"?"mdi:music-note":"mdi:thermometer")}<div><h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p></div></section>`).join("")}</footer>`:"";
let picture="";
if(session?.kind==="camera" && /^camera\.[a-z0-9_]+$/.test(session.camera || "")) {
 const path=hass.states[session.camera]?.attributes?.entity_picture;
 if(!["unavailable","unknown"].includes(hass.states[session.camera]?.state) && typeof path==="string" && path.split("?")[0]===`/api/camera_proxy/${session.camera}`)picture=`<img src="${esc(path)}" alt="${esc(session.title)} camera view">`;
}
const overlay=session?`<section class="wall-session" aria-label="Temporary display session"><div><h2>${esc(session.title)}</h2>${picture}${session.kind==="camera"&&!picture?"<p>Camera view unavailable</p>":""}<p class="wall-session-body">${esc(session.body)}</p><p class="wall-session-return">Returns to the family board automatically</p></div></section>`:"";
const kiosk=new URLSearchParams(window.location.search).has("kiosk")&&!new URLSearchParams(window.location.search).has("disable_km");
const body=`<main class="hs-wall" data-state="${esc(model.day_state)}" data-baseline="${esc(model.baseline_state || model.day_state)}" data-primary="${esc(model.primary)}" data-today="${today.length?"visible":"hidden"}" data-future="${future.length?"visible":"hidden"}" style="--wall-chrome:${kiosk?0:56}px" aria-label="${esc(cfg.title)} household board"><header class="wall-header"><div class="wall-clock"><time>${esc(date({hour:"numeric",minute:"2-digit",hour12:false}))}</time><p>${esc(date({weekday:"long",day:"numeric",month:"short"}))}</p></div>${ordinaryWeather}</header><div class="wall-board"><div class="wall-now">${alerts}${cue}${quiet}${current}</div>${next}</div>${strip}${fresh&&model.issues?.length?`<aside class="wall-source-note">${esc(model.issues.join(" Ã‚Â· "))}</aside>`:""}${overlay}</main>`;
return html`<div class="wall-wrapper" .innerHTML=${body}></div>`;
