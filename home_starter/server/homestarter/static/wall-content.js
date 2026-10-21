const cfg = JSON.parse(variables.wall_json);
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const now = new Date();
const date = options => new Intl.DateTimeFormat(hass.locale?.language || "en-AU", {timeZone:hass.config.time_zone,...options}).format(now);
const context = hass.states[cfg.context]?.attributes || {}, owner=context.home_starter_context;
const board=context.wall;
const fresh=hass.connected !== false && owner?.surface===cfg.surface_id && owner?.epoch===cfg.epoch &&
 now-new Date(context.checked_at)>=0 && now-new Date(context.checked_at)<180000 && new Date(context.valid_until)>now &&
 board?.version===1 && new Date(board.valid_until)>now;
const model=fresh?board:{day_state:"disconnected",phase:"morning",cards:[],timeline:{label:"Today",items:[]},secondary:{label:"Upcoming",items:[]},household_exception:[],active_context:[],issues:[]};
const alive=r=>!r.ends_at || new Date(r.ends_at)>now;
const valid=r=>!r.expires_at || new Date(r.expires_at)>now;
const kiosk=new URLSearchParams(window.location.search).has("kiosk")&&!new URLSearchParams(window.location.search).has("disable_km");
const small=window.innerHeight<850;
const night=Boolean(model.focus?.night);
const priority=model.priority&&valid(model.priority)?model.priority:null;
const priorityRelated=(row,name)=>Boolean(priority?.kind==="departure"&&row?.leave_at===priority.leave_at&&
 (row?.id===priority.id||(name?[name]:row?.people || []).some(person=>priority.people?.includes(person))));
const wallpaper=wallWallpaper(now,hass.config.time_zone,cfg.surface_id,cfg.wallpapers);
// Authored outline geometry is shared by native HA and isolated previews.
const shapes={home:'<path d="m3 11 9-8 9 8M5 10v11h5v-7h4v7h5V10"/>',car:'<path d="m5 8 2-4h10l2 4M4 17v3m16-3v3"/><rect x="3" y="8" width="18" height="10" rx="3"/><path d="M6 13h2m8 0h2"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',check:'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',sun:'<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"/>',cloud:'<path d="M6 18a5 5 0 1 1 1-10 6 6 0 0 1 11 2 4 4 0 0 1 0 8Z"/>',thermometer:'<path d="M9 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0Z"/><path d="M12 8v10"/>',lock:'<rect x="5" y="10" width="14" height="12" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v3"/>',music:'<path d="M9 18V5l12-3v13M9 8l12-3"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="18" cy="15" rx="3" ry="3"/>',light:'<path d="M8 15a7 7 0 1 1 8 0l-1 4H9ZM9 22h6"/>',camera:'<rect x="2" y="5" width="14" height="14" rx="3"/><path d="m16 10 6-4v12l-6-4"/>',alert:'<path d="m12 2 10 19H2ZM12 8v5m0 3v1"/>'};
Object.assign(shapes,{
 rain:'<path d="M6 15a5 5 0 1 1 1-10 6 6 0 0 1 11 2 4 4 0 0 1 0 8M7 19l-1 3m7-3-1 3m7-3-1 3"/>',
 storm:'<path d="M6 15a5 5 0 1 1 1-10 6 6 0 0 1 11 2 4 4 0 0 1 0 8M13 12l-4 6h5l-3 5"/>',
 wind:'<path d="M2 8h14a3 3 0 1 0-3-3M2 12h18a3 3 0 1 1-3 3M2 16h6"/>',
 cold:'<path d="M12 2v20M3 7l18 10M3 17 21 7M9 4l3 3 3-3M9 20l3-3 3 3"/>',
 bin:'<path d="M5 6h14l-1 14H6ZM4 6h16M9 3h6v3M9 10v6m6-6v6"/><circle cx="7" cy="22" r="1"/><circle cx="17" cy="22" r="1"/>'
});
const weatherIcon=value=>/lightning/.test(value||"")?"storm":/rain|pouring|hail|snow/.test(value||"")?"rain":/wind/.test(value||"")?"wind":["sunny","clear-night","clear night"].includes(value)?"sun":"cloud";
const dayWeather=day=>typeof day?.high==="number"&&Number.isFinite(day.high)?`<span class="wall-day-weather" aria-label="Forecast high ${esc(Math.round(day.high))} degrees">${icon(weatherIcon(day.condition))}${esc(Math.round(day.high))}°${day.warning?`<small title="${esc(day.warning.message)}">${icon("alert")}</small>`:""}</span>`:'<span class="wall-day-weather wall-forecast-unavailable" aria-label="Forecast unavailable">—</span>';
const bins=row=>row.bin_types?.length?`<span class="wall-bin-icons" aria-label="${esc(row.bin_types.join(", "))}">${row.bin_types.map(kind=>`<span data-bin="${esc(kind)}">${icon("bin")}</span>`).join("")}</span>`:"";
const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[name] || shapes.calendar}</svg>`;
const nice=value=>String(value || "").replace(/\s+-\s+/g," · ");
const shortTime=value=>String(value || "").replace(/\s+pm$/i,"");
const clock=value=>new Intl.DateTimeFormat("en-AU",{timeZone:hass.config.time_zone,hour:"numeric",minute:"2-digit",hour12:true}).format(new Date(value)).replace(/\s?[ap]m$/i,"");
const location=r=>r.location&&!r.title.toLocaleLowerCase().includes(r.location.toLocaleLowerCase())?r.location:"";
const rows=(items,limit)=> (items || []).filter(alive).slice(0,limit);
const exceptions=(model.household_exception || []).filter(valid);
const active=(model.active_context || []).filter(r=>valid(r)&&!["climate","media"].includes(r.kind)).slice(0,2);
const cards=(model.cards || []).map(c=>({...c,items:rows(c.items,night?2:small&&c.title==="This week"?2:3)})).filter(c=>c.items.length).slice(0,3);
const avatar=card=>{
 const path=hass.states[card.avatar_entity]?.attributes?.entity_picture;
 return typeof path==="string"&&/^\/api\/image\/serve\/[a-zA-Z0-9_-]+\/\d+x\d+$/.test(path)?`<img src="${esc(path)}" alt="">`:`<span>${esc(card.title.split(/\s+/).map(n=>n[0]).slice(0,2).join(""))}</span>`;
};
const fact=(r,person=false)=>{
 const leave=person&&r.leave_at&&(r.primary_departure||r.id===model.next_movement?.id);
 const title=leave?`Leave ${clock(r.leave_at)}`:`${nice(r.title)}${person&&r.time?" · "+shortTime(r.time):""}`;
 const detail=leave?`${nice(r.title)} · ${shortTime(r.time)}`:r.leave_at?"Leave "+clock(r.leave_at):!person&&r.day_offset>1?"":r.detail || location(r);
 return `<article class="wall-card-fact${!r.time?" wall-preparation-fact":""}" data-priority-related="${priorityRelated(r)}" data-importance="${esc(r.importance || "upcoming")}">${icon(leave?"car":!r.time?"check":"calendar")}<div><h3>${!person&&r.time&&r.day_offset<=1?`<time>${esc(shortTime(r.time))}</time> `:""}${esc(title)}</h3>${detail?`<p>${esc(detail)}</p>`:""}${!person&&r.day_offset>1?`<p>${esc(r.day_label+" · "+shortTime(r.time))}</p>`:""}</div></article>`;
};
const family=cards.length?cards.map((card,n)=>`<section class="wall-family-card wall-tone-${n}" data-key="${esc(card.key || card.kind+card.title)}" data-kind="${esc(card.kind)}" data-importance="${esc(card.importance || "upcoming")}"><header>${card.kind==="person"?`<div class="wall-avatar">${avatar(card)}</div>`:""}<div><h2>${esc(card.title)}</h2>${model.focus?.preview&&card.kind==="person"?'<p class="wall-person-day">Tomorrow</p>':""}</div></header><div class="wall-card-facts">${card.items.map(r=>fact(r,card.kind==="person")).join("")}</div></section>`).join(""):!fresh?'<section class="wall-unavailable"><h2>Household context unavailable</h2><p>Waiting for a fresh Home Assistant update</p></section>':"";
// Presentation-only grouping: count adjacent equal subjects without losing order or periods.
const school=model.school;
const departures=(school?.children || []).map(child=>child.next_departure?.leave_at);
const sharedDeparture=night&&departures.length&&departures.every(value=>value===departures[0]&&Date.parse(value)>now)?departures[0]:null;
const nightReadiness=sharedDeparture?`<p class="wall-night-departure">${esc(model.focus?.label || "School")} · School · Leave ${clock(sharedDeparture)}</p>`:"";
const familyIncomplete=Boolean(school?.children?.length&&!school.children.some(c=>c.periods?.length||c.dated?.length||c.rules?.length||c.commitments?.length));
const schoolBreak=subject=>/^(recess|lunch|morning tea|break)( break)?$/i.test(subject.trim());
// Each native period owns a row even when adjacent lessons join into one card.
// Real gaps get slim rows, preserving the same bell-time positions across people.
const schoolGrid=periods=>{
 const slots=[],gaps=[];
 let breaks=0;
 for(let n=0;n<periods.length;n++){
  const period=periods[n],previous=periods[n-1];
  if(previous&&Date.parse(period.start)-Date.parse(previous.end)>60000){
   const label=["Recess","Lunch"][breaks++] || "Break";
   gaps.push({subject:label,count:0,start:previous.end,end:period.start,row:slots.length+1,span:1,break:true});
   slots.push("var(--wall-break-height)");
  }
  slots.push(schoolBreak(period.subject)?"var(--wall-break-height)":"minmax(0,1fr)");
 }
 return {slots,gaps};
};
const schoolPanel=!night&&school?.children?.length?school.children.map((child,n)=>{
 const dated=rows(child.dated,1),rules=(child.rules || []).slice(0,2),groups=[];
 const readiness=child.next_departure?`Leave ${clock(child.next_departure.leave_at)}`:Number.isFinite(Date.parse(child.periods?.[0]?.start))?`Starts ${clock(child.periods[0].start)}`:school.preview?"Tomorrow":model.focus?.label || "Today";
 const readyLabel=school.preview&&readiness!=="Tomorrow"?`<small>Tomorrow</small>${esc(readiness)}`:esc(readiness);
 const nativePeriods=child.periods || [],grid=schoolGrid(nativePeriods);
 let row=0;
 for(let index=0;index<nativePeriods.length;index++) {
  const period=nativePeriods[index];
  if(index&&Date.parse(period.start)-Date.parse(nativePeriods[index-1].end)>60000)row++;
  row++;
  const last=groups.at(-1);
  const gap=Date.parse(period.start)-Date.parse(last?.end);
  // Cirrus encodes adjacent periods with a one-minute transition, not touching intervals.
  // Preserve larger gaps as visual boundaries without guessing their purpose.
  if(last?.subject===period.subject&&(!last.end&&!period.start||gap>=0&&gap<=60000)){last.count++;last.span++;last.end=period.end;}
  else groups.push({subject:period.subject,count:1,start:period.start,end:period.end,row,span:1});
 }
 const periodRow=r=>{
  const start=Date.parse(r.start),end=Date.parse(r.end);
  const state=Number.isFinite(end)&&end<=now?"completed":Number.isFinite(start)&&Number.isFinite(end)&&start<=now&&now<end?"current":"upcoming";
  const isBreak=r.break || schoolBreak(r.subject);
  const content=isBreak?"":`<span>${esc(r.subject)}</span>`;
  return `<li style="grid-row:${r.row}/span ${r.span}" data-period-count="${r.count}" data-period-state="${state}" data-break="${isBreak}"${isBreak?` role="separator" aria-label="${esc(r.subject)}"`:state==="current"?' aria-current="true"':""}>${content}</li>`;
 };
 const periods=[...groups,...grid.gaps].sort((a,b)=>a.row-b.row);
 const shown=periods.reduce((count,r)=>count+r.count,0);
 const requirements=rules.length?`<div class="wall-school-rules">${rules.map(rule=>`<p>${esc(rule)}</p>`).join("")}</div>`:"";
 const upcoming=dated.length?[]:rows(child.commitments,1),dense=Boolean(upcoming.length||dated.length||rules.length||groups.length>6);
 return `<section class="wall-family-card wall-school-child wall-tone-${n%3}" data-kind="person" data-key="school-${esc(child.person)}" data-status="${esc(child.status)}" style="grid-column:${n+1}" data-dense="${dense}" data-importance="${esc(child.importance || "upcoming")}"><header><div class="wall-avatar">${avatar({title:child.name,avatar_entity:cfg.people?.[child.person]})}</div><div><h2>${esc(child.name)}</h2><p class="wall-person-day" data-priority-related="${priorityRelated(child.next_departure,child.name)}" data-departure="${Boolean(child.next_departure)}">${readyLabel}</p></div></header><div class="wall-card-facts wall-school-day">${periods.length?`<ol class="wall-school-periods" style="grid-template-rows:${grid.slots.join(" ")}">${periods.map(periodRow).join("")}</ol>${child.periods.length>shown?`<p class="wall-school-more">+${child.periods.length-shown} later classes</p>`:""}`:!dated.length&&!rules.length?`<p class="wall-school-fallback">${esc(child.fallback)}</p>`:""}</div><div class="wall-school-extra">${dated.length?`<div class="wall-school-dated">${dated.map(r=>fact(r,true)).join("")}</div>`:""}${requirements}${upcoming.map(r=>fact(r,true)).join("")}</div></section>`;
}).join(""):"";
const upcomingDays=night?[]:(model.upcoming_days || model.week || []);
const upcoming=()=>{
 return upcomingDays.map((day,n)=>{
  const items=rows(day.items,Infinity);
  if(!items.length)return "";
  return `<section class="wall-upcoming-day"><h3>${esc(day.label)}${dayWeather(day.weather)}</h3><ol>${items.map(r=>`<li class="wall-upcoming-row wall-tone-${n%3}"><span class="wall-dot"></span><time>${esc(shortTime(r.time))}</time><p>${bins(r)}${esc(nice(r.title))}${r.people?.length&&!r.person_title?`<span> · ${esc(r.people.join(" · "))}</span>`:""}</p></li>`).join("")}</ol></section>`;
 }).join("");
};
const timeline=(panel,secondary=false)=>{
  const items=rows(panel?.items,Infinity);
 const future=upcoming();
 if(!items.length&&!future)return "";
 return `<section class="wall-surface ${secondary?"wall-secondary":"wall-timeline"}"><header><h2>${esc(panel?.label || (secondary?"Upcoming":"Today"))}${dayWeather(panel?.weather)}</h2>${!secondary?`<p>${esc(panel?.date_label || date({weekday:"short",day:"numeric",month:"short"}))}</p>`:""}</header><ol>${items.map((r,n)=>`<li class="wall-line-item wall-tone-${n%3}"><time aria-label="${esc((r.time&&r.time!=="All day"?"Starts ":"")+(r.time || r.when))}">${r.time&&r.time!=="All day"?"<small>Starts</small>":""}${esc(shortTime(r.time || r.when))}</time><span class="wall-dot"></span><div><h3>${bins(r)}${esc(nice(r.title))}</h3><div class="wall-line-meta">${secondary?(r.day_offset>0?`<p>${esc(r.day_label)}</p>`:""):`${r.people?.length&&!r.person_title?`<p>${esc(r.people.join(" · "))}</p>`:""}${location(r)?`<p>${esc(location(r))}</p>`:""}${r.detail&&!r.bin_types?.length?`<p data-priority-related="${priorityRelated(r)}" class="${r.leave_at?"wall-leave":"wall-event-detail"}">${r.leave_at?icon("car"):""}${esc(r.leave_at&&r.id!==model.next_movement?.id?"Leave "+clock(r.leave_at):r.detail)}</p>`:""}`}</div></div></li>`).join("")}</ol>${future?`<div class="wall-upcoming" aria-label="Upcoming days">${future}</div>`:""}</section>`;
};
const weather=model.weather;
const temperature=value=>typeof value==="number"&&Number.isFinite(value)?Math.round(value)+"°":null;
const preview=Boolean(model.focus?.preview || night);
const weatherCondition=weather?.forecast_condition || (!preview?weather?.condition:null);
const condition=weatherCondition?.replace(/partlycloudy/g,"Partly cloudy").replace(/[-_]/g," ").replace(/^./,c=>c.toUpperCase());
const reading=(value,label,primary=false)=>temperature(value)?`<div class="wall-temperature${primary?" wall-temperature-primary":""}"><${primary?"strong":"span"}>${esc(temperature(value))}</${primary?"strong":"span"}><small>${esc(label)}</small></div>`:"";
const weatherLabel=preview?(model.focus?.label || "Tomorrow"):"Weather";
const weatherSummary=[preview?weatherLabel:null,preview?temperature(weather?.low)&&temperature(weather.low)+" low":temperature(weather?.temperature)&&temperature(weather.temperature)+" now",condition,weather?.high==null?"Forecast high unavailable":null].filter(Boolean).join(" · ") || "Weather unavailable";
const weatherImpact=weather?.warning?.message || (typeof weather?.precipitation_probability==="number"&&weather.precipitation_probability>=60?`${weather.precipitation_probability}% chance of rain`:"");
const weatherPanel=`<section class="wall-weather" data-severity="${esc(weather?.warning?.level || "ordinary")}" aria-label="${esc(weatherLabel)}"><div class="wall-weather-reading">${weatherCondition?icon(weatherIcon(weatherCondition)):""}${reading(weather?.high,"High",true)}${weather?.warning?`<span class="wall-weather-badge">${icon(({heat:"thermometer",cold:"cold",wind:"wind",storm:"storm",rain:"rain"})[weather.warning.kind] || "alert")}${esc(weather.warning.label)}</span>`:""}</div><h2>${esc(weatherSummary)}</h2>${weatherImpact?`<p class="wall-weather-impact">${esc(weatherImpact)}</p>`:""}</section>`;
const priorityPanel=priority?`<section class="wall-priority" aria-label="Household action" data-priority-id="${esc(priority.id)}" data-expires="${esc(priority.expires_at)}" data-level="${esc(priority.level)}"><div class="wall-priority-heading"><span class="wall-priority-icon">${icon(priority.kind==="departure"?"car":priority.kind==="event"||priority.kind==="preparation"?"calendar":"alert")}</span><h1>${esc(priority.title)}</h1></div>${priority.people?.length?`<p>${esc(priority.people.join(" · "))}</p>`:""}${priority.location?`<p>${esc(priority.location)}</p>`:""}<p class="wall-priority-action">${priority.starts_at?`Starts ${esc(clock(priority.starts_at))} · `:""}<strong>${esc(priority.action)}</strong></p></section>`:"";
const status=fresh?model.household_status || {}:{};
const lightsOn=Array.isArray(status.lights_on)?status.lights_on:[];
const lightShapes={
 lamp:'<path d="m8 3-4 10h16L16 3ZM12 13v8m-4 0h8"/>',
 pendant:'<path d="M12 2v5m-7 9a7 7 0 0 1 14 0ZM10 19h4"/>',
 downlight:'<path d="M3 7h18M7 7v4h10V7M8 15l-2 4m6-4v5m4-5 2 4"/>',
 strip:'<path d="M3 8h18v5H3Zm3 9v2m6-2v2m6-2v2"/>',
};
const litIcon=r=>{
 const shape=({'mdi:lamp':'lamp','mdi:floor-lamp':'lamp','mdi:ceiling-light':'pendant','mdi:ceiling-light-multiple':'pendant','mdi:light-recessed':'downlight','mdi:recessed-ceiling':'downlight','mdi:led-strip':'strip','mdi:led-strip-variant':'strip'})[r.icon];
 return shape?`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${lightShapes[shape]}</svg>`:icon("light");
};
const litRow=lightsOn.length?`<div class="wall-lights-on" aria-label="${esc(lightsOn.length+" lights or groups on")}">${lightsOn.slice(0,3).map(r=>`<span class="wall-lit-light" role="img" aria-label="${esc(r.name)}" title="${esc(r.name)}">${litIcon(r)}</span>`).join("")}${lightsOn.length>3?`<span class="wall-lights-more" aria-label="${lightsOn.length-3} more on">+${lightsOn.length-3}</span>`:""}</div>`:"";
const statusCell=(kind,label,value,detail)=>{
 if(night&&(kind==="light"&&value==="All off"||kind==="lock"&&value==="Armed"))return "";
 if(label!=="Home"&&(!value||value==="Not selected"))return "";
 const climate=kind==="thermometer"&&detail;
 return `<section class="wall-status-cell" aria-label="${esc(label)}"><span class="wall-status-icon">${icon(kind)}</span><div><h3>${esc(climate?value:label)}</h3>${kind==="light"&&litRow?litRow:`<strong>${esc(climate?detail:value || "Status unavailable")}</strong>`}</div></section>`;
};
const household=`<section class="wall-household wall-surface" aria-label="Household status">${statusCell("home","Home",status.home)}${statusCell("thermometer","Climate",temperature(status.climate?.temperature)||status.climate?.detail,temperature(status.climate?.temperature)?status.climate?.detail:"")}${statusCell("lock","Security",status.security)}${statusCell("light","Lights",status.lights)}</section>`;
const selectedCameras=status.cameras || [];
const playing=selectedCameras.some(c=>c.available)?[]:(status.now_playing || []).slice(0,2);
const cameras=playing.length?[]:selectedCameras.filter(c=>!night||!c.available).slice(0,3);
const cameraPicture=c=>{
 const path=hass.states[c.entity]?.attributes?.entity_picture;
 return c.available&&typeof path==="string"&&path.split("?")[0]===`/api/camera_proxy/${c.entity}`?`<img src="${esc(path)}" alt="${esc(c.name)} camera view">`:icon("camera");
};
const mediaPanel=playing.length?`<section class="wall-camera-status wall-media-status wall-surface" aria-label="Now playing"><div class="wall-camera-heading"><span class="wall-status-icon">${icon("music")}</span><div><h2>Now playing</h2></div></div><div class="wall-active-status">${playing.map(r=>`<section><h3>${esc(r.title)}</h3><p>${esc([r.artist,r.room].filter(Boolean).join(" · "))}</p></section>`).join("")}</div></section>`:"";
const cameraPanel=mediaPanel || (cameras.length||active.length?`<section class="wall-camera-status wall-surface" aria-label="Cameras and active context">${cameras.length?`<div class="wall-camera-heading"><span class="wall-status-icon">${icon("camera")}</span><div><h2>Cameras</h2><p>${esc(cameras.filter(c=>c.available).length+" available")}</p></div></div><div class="wall-cameras">${cameras.map(c=>`<figure>${cameraPicture(c)}<figcaption>${esc(c.name)}${!c.available?" · Unavailable":""}</figcaption></figure>`).join("")}</div>`:`<div class="wall-active-status">${active.map(r=>`<section><h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p></section>`).join("")}</div>`}</section>`:model.issues?.length?`<aside class="wall-source-note" role="status">${esc(model.issues.some(s=>s.includes("Calendar"))?"Calendar temporarily unavailable":"Some household information is temporarily unavailable")}</aside>`:"");
// Replaceable utility slot: structured escaped data, never arbitrary HTML.
const utility=model.utility || {kind:"household"};
const utilityPanel=utility.kind==="message"&&utility.title?
 `<section class="wall-surface wall-utility-message"><h2>${esc(utility.title)}</h2><p>${esc(utility.body)}</p></section>`:
 household+cameraPanel;
const session=model.display_session && valid(model.display_session) ? model.display_session : null;
let picture="";
if(session?.kind==="camera" && /^camera\.[a-z0-9_]+$/.test(session.camera || "")) {
 const path=hass.states[session.camera]?.attributes?.entity_picture;
 if(!["unavailable","unknown"].includes(hass.states[session.camera]?.state)&&typeof path==="string"&&path.split("?")[0]===`/api/camera_proxy/${session.camera}`)picture=`<img src="${esc(path)}" alt="${esc(session.title)} camera view">`;
}
const overlay=session?`<section class="wall-session" aria-label="Temporary display session"><div><h2>${esc(session.title)}</h2>${picture}${session.kind==="camera"&&!picture?"<p>Camera view unavailable</p>":""}<p class="wall-session-body">${esc(session.body)}</p><p>Returns to the family board automatically</p></div></section>`:"";
const alerts=exceptions.filter(r=>r.kind!=="weather");
const primaryAgenda=night?"":timeline(model.timeline);
const body=`<main class="hs-wall" data-fresh="${fresh}" data-night="${night}" data-priority="${Boolean(priority)}" data-priority-level="${esc(priority?.level || "")}" data-wallpaper-period="${wallpaper.period}" data-wallpaper="${wallpaper.id || "fallback"}" data-wall-surface="${esc(cfg.surface_id)}" data-cursor-hidden="${kiosk}" data-state="${esc(model.day_state)}" data-mode="${esc(model.focus?.mode || "today")}" data-phase="${esc(model.phase || "morning")}" data-agenda="${primaryAgenda?"visible":"hidden"}" style="${decorationStyle(now,hass.config.time_zone,cfg.surface_id)};--wall-chrome:${kiosk?0:56}px${wallpaper.id?`;--wall-landscape:var(--wallpaper-${wallpaper.id})`:""}" aria-label="${esc(cfg.title)} household board">${alerts.length?`<aside class="wall-alerts">${icon("alert")}${esc(alerts.map(r=>r.title+" · "+r.detail).join(" · "))}</aside>`:""}<header class="wall-header"><div class="wall-clock"><time>${esc(date({hour:"numeric",minute:"2-digit",hour12:false}).replace(/^0/,""))}</time><p>${esc(date({weekday:"long",day:"numeric",month:"short"})).replace(",","")}</p>${nightReadiness}</div>${priorityPanel || weatherPanel}${priority?`<template class="wall-priority-fallback">${weatherPanel}</template>`:""}</header>${night?"":`<div class="wall-family${schoolPanel?" wall-family-school":""}" data-incomplete="${familyIncomplete}" data-count="${schoolPanel?school.children.length:cards.length}" aria-label="${esc(school?.label || "Household plans")}">${schoolPanel || family}</div><aside class="wall-agenda">${primaryAgenda}</aside>`}<footer class="wall-bottom" data-region="utility" data-content="${esc(model.utility?.kind || "household")}">${utilityPanel}</footer>${overlay}</main>`;
if(window.customElements&&typeof HTMLElement!=="undefined"&&!window.customElements.get("home-starter-ambient-wall")) {
 // HA uses nested shadow roots. Scope the document-wide rule to this mounted wall
 // route in kiosk mode; remove every injected style/listener on navigation or detach.
 const cursorGuard=host=>{
  const doc=host.ownerDocument,view=doc.defaultView,styles=new Map(),observers=new Map();
  const css=":host,html,body,#root,#app,*,*::before,*::after{cursor:none!important}";
  let surface="",enabled=false,frame=0,active=false;
  const changed=records=>{
   if(records.some(r=>r.removedNodes.length||[...r.addedNodes].some(n=>!(n.nodeType===1&&n.hasAttribute('data-home-starter-wall-cursor'))))&&!frame)
    frame=view.requestAnimationFrame(()=>{frame=0;if(active)cover(doc);});
  };
  const cover=root=>{
   if(root===doc||root instanceof view.ShadowRoot){
    if(!styles.has(root)){
     const style=doc.createElement("style");style.setAttribute("data-home-starter-wall-cursor","");style.textContent=css;
     styles.set(root,style);(root===doc?doc.head:root).append(style);
     const observer=new view.MutationObserver(changed);observer.observe(root,{childList:true,subtree:true});observers.set(root,observer);
    }else if(!styles.get(root).isConnected)(root===doc?doc.head:root).append(styles.get(root));
   }
   if(root.shadowRoot)cover(root.shadowRoot);
   for(const element of root.querySelectorAll("*"))if(element.shadowRoot)cover(element.shadowRoot);
  };
  const clear=()=>{
   active=false;if(frame)view.cancelAnimationFrame(frame);frame=0;
   for(const observer of observers.values())observer.disconnect();observers.clear();
   for(const style of styles.values())style.remove();styles.clear();
  };
  const sync=()=>{
   const query=new URLSearchParams(view.location.search);
   const wanted=host.isConnected&&enabled&&surface&&view.location.pathname.startsWith('/home-starter-'+surface+'/')&&query.has('kiosk')&&!query.has('disable_km');
   if(wanted){active=true;cover(doc);}else clear();
  };
  const events=['popstate','hashchange','location-changed'];for(const event of events)view.addEventListener(event,sync);
  return {set(root){surface=root?.dataset.wallSurface || "";enabled=root?.dataset.cursorHidden==="true";sync();},
   dispose(){clear();for(const event of events)view.removeEventListener(event,sync);}};
 };
 class AmbientWall extends HTMLElement {
  connectedCallback(){
   this._cursorGuard ||= cursorGuard(this);this._cursorGuard.set(this.querySelector('.hs-wall'));
   this._expirePriority();this._priorityAppearance();
    this._resize ||= new ResizeObserver(()=>this._fitAgenda());this._resize.observe(this);
   document.fonts?.ready.then(()=>{if(this.isConnected)this._fitAgenda();});
   this._fitAgenda();
  }
  disconnectedCallback(){clearTimeout(this._priorityTimer);this._cursorGuard?.dispose();this._cursorGuard=null;this._resize?.disconnect();this._resize=null;cancelAnimationFrame(this._fitFrame);}
  _fitAgenda(){
   cancelAnimationFrame(this._fitFrame);
   this._fitFrame=requestAnimationFrame(()=>{
         const panel=this.querySelector('.wall-timeline');
     if(!panel)return;
     const future=panel.querySelector('.wall-upcoming');
     const days=[...(future?.children || [])],detailed=[...panel.querySelectorAll(':scope > ol > li')];
     if(future)future.hidden=false;
     for(const row of detailed)row.hidden=false;
     for(const day of days){day.hidden=false;for(const row of day.querySelectorAll('li'))row.hidden=false;}
     const bottom=panel.getBoundingClientRect().bottom-parseFloat(getComputedStyle(panel).paddingBottom);
     let full=false,visible=0;
     for(const row of detailed){if(full||row.getBoundingClientRect().bottom>bottom){row.hidden=true;full=true;}}
     for(const day of days){
      let count=0;
      for(const row of day.querySelectorAll('li')){
       if(full||row.getBoundingClientRect().bottom>bottom){row.hidden=true;full=true;}
       else {count++;visible++;}
      }
      day.hidden=count===0;
     }
     if(future)future.hidden=visible===0;
   });
  }
   _priorityAppearance(){
    const root=this.querySelector('.hs-wall'),key=root?.querySelector('.wall-priority')?.dataset.priorityId || "";
    if(key&&key!==this._priorityKey)root.dataset.priorityEnter="true";
    this._priorityKey=key;
   }
   _expirePriority(){
    clearTimeout(this._priorityTimer);
    const root=this.querySelector('.hs-wall'),panel=root?.querySelector('.wall-priority');
    if(!panel)return;
    const delay=Date.parse(panel.dataset.expires)-Date.now();
    if(!Number.isFinite(delay))return;
    this._priorityTimer=setTimeout(()=>{
     const fallback=root.querySelector('.wall-priority-fallback');
     if(fallback){panel.replaceWith(fallback.content.cloneNode(true));fallback.remove();}
     root.dataset.priority="false";this._priorityKey="";this._fitAgenda();
    },Math.max(0,delay));
   }
  set content(value) {
   if(value===this._content)return;
   this._content=value;
   const generation=this._generation=(this._generation || 0)+1;
   const parsed=document.createElement("template");parsed.innerHTML=value;
   const next=parsed.content.querySelector(".hs-wall"),old=this.querySelector(".hs-wall");
   const keys=root=>[...(root?.querySelectorAll("[data-key]") || [])].map(e=>e.dataset.key).join("|");
   const changed=old&&next&&(keys(old)!==keys(next)||old.dataset.mode!==next.dataset.mode);
   const update=()=>{if(generation===this._generation){this.innerHTML=value;this._cursorGuard?.set(this.querySelector(".hs-wall"));this._expirePriority();this._priorityAppearance();this._fitAgenda();}};
   this._transition?.skipTransition();
   if(changed&&old.dataset.fresh==="true"&&next.dataset.fresh==="true"&&document.startViewTransition&&!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    this._transition=document.startViewTransition(update);
    this._transition.ready.catch(()=>{});this._transition.finished.catch(()=>{});
   } else update();
  }
 }
 window.customElements.define("home-starter-ambient-wall",AmbientWall);
 if(!document.getElementById("home-starter-wall-transition-style")){
  const style=document.createElement("style");style.id="home-starter-wall-transition-style";
  style.textContent="::view-transition-old(home-starter-wall),::view-transition-new(home-starter-wall){animation-duration:450ms;animation-timing-function:cubic-bezier(.22,1,.36,1)}";
  document.head.append(style);
 }
}
return html`<home-starter-ambient-wall .content=${body}></home-starter-ambient-wall>`;
