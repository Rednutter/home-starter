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
const model=fresh?board:{day_state:"disconnected",day_summary:"Household context unavailable",layout:"rest",primary:"quiet",today_items:[],future_attention:[],household_exception:[],active_context:[],issues:[]};
const alive=r=>!r.ends_at || new Date(r.ends_at)>now;
const valid=r=>!r.expires_at || new Date(r.expires_at)>now;
const kiosk=new URLSearchParams(window.location.search).has("kiosk")&&!new URLSearchParams(window.location.search).has("disable_km");
const height=window.innerHeight-(kiosk?0:56);
const contentHeight=height-((model.active_context || []).some(valid)?120:0)-(model.issues?.length?32:0), small=contentHeight<850;
const today=(model.today_items || []).filter(alive).slice(0,small?3:4);
const future=(model.future_attention || []).filter(alive);
const preparation=model.phase==="evening"?(model.tomorrow_preparation || []).slice(0,2):[];
const tomorrow=(model.tomorrow_items || future.filter(r=>r.day_offset===1)).filter(alive).slice(0,contentHeight<700?2:small||preparation.length?3:5);
const budget=contentHeight<760?3:contentHeight<1000?4:6;
const available=(model.ahead_groups || (future.length&&!tomorrow.length?[{label:"Coming up",items:future}]:[])).map(g=>({...g,items:g.items.filter(alive)})).filter(g=>g.items.length).slice(0,budget);
const cost=r=>1+(r.people?.length?0.5:0)+(r.detail?.length?0.5:0)+(r.title.length>(small?28:42)?0.5:0);
const groups=[];
let remaining=budget;
for(const group of available){const units=cost(group.items[0]);if(units>remaining&&groups.length)break;groups.push({...group,items:group.items.slice(0,1)});remaining-=units;}
for(let n=1;n<3&&remaining>0;n++)for(let i=0;i<groups.length&&remaining>0;i++){const item=available[i].items[n];if(item&&cost(item)<=remaining){groups[i].items.push(item);remaining-=cost(item);}}
const exceptions=(model.household_exception || []).filter(valid), active=(model.active_context || []).filter(valid);
const movement=model.next_movement && alive(model.next_movement) ? model.next_movement : null;
const hasHorizon=tomorrow.length>0||preparation.length>0||groups.length>0;
const visibleToday=today.filter(r=>!movement||r.id!==movement.id).slice(0,small&&movement&&hasHorizon?1:4);
const session=model.display_session && valid(model.display_session) ? model.display_session : null;
const people=r=>Array.isArray(r.people)&&r.people.length?`<span class="wall-people">${esc(r.people.join(" · "))}</span>`:"";
const row=(r,compact=false)=>`<article class="wall-item${compact?" wall-item-compact":""}${r.when==="This morning"?" wall-item-note":""}${model.phase==="evening"&&r.early_start?" wall-item-early":""}">${r.when==="This morning"?"":`<time>${esc(r.time || r.when)}</time>`}<div><h3>${esc(r.title.replace(/\s+-\s+/g," · "))}</h3><div class="wall-facts">${people(r)}${r.location&&!r.title.toLocaleLowerCase().includes(r.location.toLocaleLowerCase())?`<p>${esc(r.location)}</p>`:""}${r.detail?`<strong class="wall-departure">${esc(r.detail)}</strong>`:""}</div></div></article>`;
const weather=model.weather;
const weatherIcon={sunny:"mdi:weather-sunny","clear night":"mdi:weather-night",rainy:"mdi:weather-rainy",pouring:"mdi:weather-pouring",cloudy:"mdi:weather-cloudy",partlycloudy:"mdi:weather-partly-cloudy"}[weather?.condition] || "mdi:weather-partly-cloudy";
const ordinaryWeather=weather&&model.baseline_state!=="overnight"?`<section class="wall-weather" aria-label="Current conditions">${icon(weatherIcon)}<div><strong>${typeof weather.temperature==="number"&&Number.isFinite(weather.temperature)?esc(Math.round(weather.temperature))+" "+esc(weather.unit):esc(weather.condition)}</strong><p>${esc(weather.condition)}</p></div></section>`:"";
const cue=movement?`<section class="wall-movement wall-surface" aria-label="Next movement"><h2>${esc(movement.label)}</h2><h3>${esc(movement.title)}</h3>${people(movement)}${movement.location?`<p>${esc(movement.location)}</p>`:""}<strong>${esc(movement.detail)}</strong></section>`:"";
const alerts=exceptions.length?`<section class="wall-exceptions" aria-label="Needs attention">${exceptions.map(r=>`<article><span>${icon(r.kind==="weather"?"mdi:weather-rainy":r.kind==="bins"?"mdi:trash-can-outline":"mdi:alert-circle-outline")}</span><div><h2>${esc(r.title)}</h2><p>${esc(r.detail)}</p></div></article>`).join("")}</section>`:"";
const current=fresh?(visibleToday.length||!movement&&!exceptions.length?`<section class="wall-today wall-surface${!movement&&visibleToday.length===0?" wall-today-compact":""}" data-count="${visibleToday.length}"><h2>Today</h2>${visibleToday.length?visibleToday.map(r=>row(r,true)).join(""): `<p class="wall-today-summary">${esc(model.today_summary || model.day_summary)}</p>`}</section>`:""):`<section class="wall-unavailable wall-surface"><h2>Household context unavailable</h2><p>Waiting for a fresh Home Assistant update.</p></section>`;
const next=tomorrow.length||preparation.length?`<section class="wall-tomorrow wall-surface" data-count="${tomorrow.length+preparation.length}"><header><h2>Tomorrow</h2><p>${esc(model.tomorrow_label || "")}</p></header>${tomorrow.map(r=>row(r)).join("")}${preparation.length?`<aside class="wall-preparation"><h3>Get ready for ${esc(model.tomorrow_label)}</h3>${preparation.map(r=>`<p>${esc(r.title)}${r.people.length?` · ${esc(r.people.join(" · "))}`:""}</p>`).join("")}</aside>`:""}</section>`:"";
const ahead=groups.length?`<section class="wall-ahead wall-surface" data-density="${small||groups.length>4?"dense":"normal"}"><header><h2>${tomorrow.length?"Week ahead":"Coming up"}</h2></header><div class="wall-days">${groups.map(group=>`<section class="wall-day"><h4>${esc(group.label)}</h4>${group.items.map(r=>row(r,true)).join("")}</section>`).join("")}</div></section>`:"";
const strip=active.length?`<footer class="wall-context" aria-label="Active household context">${active.map(r=>`<section>${icon(r.kind==="timer"?"mdi:timer-outline":r.kind==="media"?"mdi:music-note":"mdi:thermometer")}<div><h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p></div></section>`).join("")}</footer>`:"";
let picture="";
if(session?.kind==="camera" && /^camera\.[a-z0-9_]+$/.test(session.camera || "")) {
 const path=hass.states[session.camera]?.attributes?.entity_picture;
 if(!["unavailable","unknown"].includes(hass.states[session.camera]?.state) && typeof path==="string" && path.split("?")[0]===`/api/camera_proxy/${session.camera}`)picture=`<img src="${esc(path)}" alt="${esc(session.title)} camera view">`;
}
const overlay=session?`<section class="wall-session" aria-label="Temporary display session"><div><h2>${esc(session.title)}</h2>${picture}${session.kind==="camera"&&!picture?"<p>Camera view unavailable</p>":""}<p class="wall-session-body">${esc(session.body)}</p><p class="wall-session-return">Returns to the family board automatically</p></div></section>`:"";
const layout=exceptions.length||movement?"current":model.layout || (tomorrow.length?"tomorrow":groups.length?"ahead":today.length?"today":"rest");
const body=`<main class="hs-wall" data-state="${esc(model.day_state)}" data-baseline="${esc(model.baseline_state || model.day_state)}" data-primary="${esc(model.primary)}" data-layout="${esc(layout)}" data-phase="${esc(model.phase || "morning")}" data-horizon="${hasHorizon?"visible":"hidden"}" data-current="${movement&&visibleToday.length?"paired":"single"}" data-tomorrow="${next?"visible":"hidden"}" data-ahead="${groups.length?"visible":"hidden"}" style="--wall-chrome:${kiosk?0:56}px" aria-label="${esc(cfg.title)} household board"><header class="wall-header"><div class="wall-clock"><time>${esc(date({hour:"numeric",minute:"2-digit",hour12:false}))}</time><div class="wall-date"><p>${esc(date({weekday:"long"}))}</p><p>${esc(date({day:"numeric",month:"long"}))}</p></div></div>${ordinaryWeather}</header><div class="wall-board"><div class="wall-now">${alerts}${cue}${current}</div>${next}${ahead}</div>${strip}${fresh&&model.issues?.length?`<aside class="wall-source-note">${esc(model.issues.join(" · "))}</aside>`:""}${overlay}</main>`;
return html`<div class="wall-wrapper" .innerHTML=${body}></div>`;
