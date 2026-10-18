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
// Authored outline geometry is shared by native HA and isolated previews.
const shapes={home:'<path d="m3 11 9-8 9 8M5 10v11h5v-7h4v7h5V10"/>',car:'<path d="m5 8 2-4h10l2 4M4 17v3m16-3v3"/><rect x="3" y="8" width="18" height="10" rx="3"/><path d="M6 13h2m8 0h2"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',check:'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',sun:'<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"/>',cloud:'<path d="M6 18a5 5 0 1 1 1-10 6 6 0 0 1 11 2 4 4 0 0 1 0 8Z"/>',thermometer:'<path d="M9 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0Z"/><path d="M12 8v10"/>',lock:'<rect x="5" y="10" width="14" height="12" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v3"/>',light:'<path d="M8 15a7 7 0 1 1 8 0l-1 4H9ZM9 22h6"/>',camera:'<rect x="2" y="5" width="14" height="14" rx="3"/><path d="m16 10 6-4v12l-6-4"/>',alert:'<path d="m12 2 10 19H2ZM12 8v5m0 3v1"/>'};
const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[name] || shapes.calendar}</svg>`;
const nice=value=>String(value || "").replace(/\s+-\s+/g," · ");
const shortTime=value=>String(value || "").replace(/\s+pm$/i,"");
const clock=value=>new Intl.DateTimeFormat("en-AU",{timeZone:hass.config.time_zone,hour:"numeric",minute:"2-digit",hour12:true}).format(new Date(value)).replace(/\s?[ap]m$/i,"");
const location=r=>r.location&&!r.title.toLocaleLowerCase().includes(r.location.toLocaleLowerCase())?r.location:"";
const rows=(items,limit)=> (items || []).filter(alive).slice(0,limit);
const exceptions=(model.household_exception || []).filter(valid);
const active=(model.active_context || []).filter(r=>valid(r)&&r.kind!=="climate").slice(0,2);
const cards=(model.cards || []).map(c=>({...c,items:rows(c.items,night?2:small&&c.title==="This week"?2:3)})).filter(c=>c.items.length).slice(0,3);
const avatar=card=>{
 const path=hass.states[card.avatar_entity]?.attributes?.entity_picture;
 return typeof path==="string"&&/^\/api\/image\/serve\/[a-zA-Z0-9_-]+\/\d+x\d+$/.test(path)?`<img src="${esc(path)}" alt="">`:`<span>${esc(card.title.split(/\s+/).map(n=>n[0]).slice(0,2).join(""))}</span>`;
};
const fact=(r,person=false)=>{
 const leave=person&&r.leave_at&&(r.primary_departure||r.id===model.next_movement?.id);
 const title=leave?`Leave ${clock(r.leave_at)}`:`${nice(r.title)}${person&&r.time?" · "+shortTime(r.time):""}`;
 const detail=leave?`${nice(r.title)} · ${shortTime(r.time)}`:r.leave_at?"Leave "+clock(r.leave_at):!person&&r.day_offset>1?"":r.detail || location(r);
 return `<article class="wall-card-fact${!r.time?" wall-preparation-fact":""}" data-importance="${esc(r.importance || "upcoming")}">${icon(leave?"car":!r.time?"check":"calendar")}<div><h3>${!person&&r.time&&r.day_offset<=1?`<time>${esc(shortTime(r.time))}</time> `:""}${esc(title)}</h3>${detail?`<p>${esc(detail)}</p>`:""}${!person&&r.day_offset>1?`<p>${esc(r.day_label+" · "+shortTime(r.time))}</p>`:""}</div></article>`;
};
const family=cards.length?cards.map((card,n)=>`<section class="wall-family-card wall-tone-${n}" data-key="${esc(card.key || card.kind+card.title)}" data-kind="${esc(card.kind)}" data-importance="${esc(card.importance || "upcoming")}"><header>${card.kind==="person"?`<div class="wall-avatar">${avatar(card)}</div>`:""}<div><h2>${esc(card.title)}</h2>${model.focus?.preview&&card.kind==="person"?'<p class="wall-person-day">Tomorrow</p>':""}</div></header><div class="wall-card-facts">${card.items.map(r=>fact(r,card.kind==="person")).join("")}</div></section>`).join(""):!fresh?'<section class="wall-unavailable"><h2>Household context unavailable</h2><p>Waiting for a fresh Home Assistant update</p></section>':"";
// Presentation-only grouping: count adjacent equal subjects without losing order or periods.
const school=model.school;
const schoolPanel=school?.children?.length?school.children.map((child,n)=>{
 const dated=rows(child.dated,2),rules=(child.rules || []).slice(0,2),groups=[];
 if(night){
  const first=child.periods?.[0],next=rows(child.commitments,1);
  const summary=first?`School · ${clock(first.start)}`:!dated.length?(child.status==="not_configured"?"Timetable not linked":"No classes listed"):"";
  return `<section class="wall-family-card wall-school-child wall-tone-${n%3}" data-kind="person" data-key="school-${esc(child.person)}" data-status="${esc(child.status)}"><header><div class="wall-avatar">${avatar({title:child.name,avatar_entity:cfg.people?.[child.person]})}</div><div><h2>${esc(child.name)}</h2><p class="wall-person-day">${esc(model.focus?.label || (model.focus?.preview?"Tomorrow":"Today"))}</p></div></header><div class="wall-card-facts">${summary?`<p class="wall-night-summary">${esc(summary)}</p>`:""}${dated.slice(0,1).map(r=>fact(r,true)).join("")}${rules.map(r=>`<p class="wall-night-rule">${esc(r)}</p>`).join("")}${next.map(r=>fact(r,true)).join("")}</div></section>`;
 }
 for(const period of child.periods || []) {
  const last=groups.at(-1);
  if(last?.subject===period.subject)last.count++;
  else groups.push({subject:period.subject,count:1});
 }
 const periods=groups.slice(0,Math.max(2,(small?7:8)-dated.length*2-rules.length));
 const shown=periods.reduce((count,r)=>count+r.count,0);
 return `<section class="wall-family-card wall-school-child wall-tone-${n%3}" data-kind="person" data-key="school-${esc(child.person)}" data-status="${esc(child.status)}" data-importance="upcoming"><header><div class="wall-avatar">${avatar({title:child.name,avatar_entity:cfg.people?.[child.person]})}</div><div><h2>${esc(child.name)}</h2><p class="wall-person-day">${esc(model.focus?.preview?"Tomorrow":"Today")} at school</p></div></header><div class="wall-card-facts">${dated.length?`<div class="wall-school-dated">${dated.map(r=>fact(r,true)).join("")}</div>`:""}${periods.length?`<ol class="wall-school-periods">${periods.map(r=>`<li data-period-count="${r.count}"><span>${esc(r.subject)}</span>${r.count>1?`<span class="wall-period-count" aria-label="${r.count} scheduled periods">&times;${r.count}</span>`:""}</li>`).join("")}</ol>${child.periods.length>shown?`<p class="wall-school-more">+${child.periods.length-shown} later classes</p>`:""}`:!dated.length&&!rules.length?`<p class="wall-school-fallback">${esc(child.fallback)}</p>`:""}${rules.length?`<div class="wall-school-rules">${rules.map(rule=>`<p>${esc(rule)}</p>`).join("")}</div>`:""}</div></section>`;
}).join(""):"";
const weekPanel=!night&&model.week?.length?`<section class="wall-week wall-secondary wall-surface" aria-label="Week ahead"><header><h2>Week ahead</h2></header><ol class="wall-week-days">${model.week.slice(0,6).map((day,n)=>rows(day.items,1).map(r=>`<li class="wall-week-row wall-tone-${n%3}"><span class="wall-week-day">${esc(day.label.length>9?day.label:day.label.slice(0,3))}</span><time>${esc(shortTime(r.time))}</time><span class="wall-dot"></span><h3>${esc(nice(r.title))}</h3></li>`).join("")).join("")}</ol></section>`:"";
const timeline=(panel,secondary=false)=>{
 const available=rows(panel?.items,secondary?3:small?4:5),items=[];
 let capacity=secondary?(small?2:3):small?5:7;
 for(const r of available){const cost=1+(r.title.length>28?0.5:0)+(!secondary&&(r.detail||location(r))?0.5:0)+(secondary&&r.day_offset>0?0.5:0);if(cost>capacity&&items.length)break;items.push(r);capacity-=cost;}
 if(!items.length)return "";
 return `<section class="wall-surface ${secondary?"wall-secondary":"wall-timeline"}"><header><h2>${esc(panel?.label || (secondary?"Upcoming":"Today"))}</h2>${!secondary?`<p>${esc(panel?.date_label || date({weekday:"short",day:"numeric",month:"short"}))}</p>`:""}</header><ol>${items.map((r,n)=>`<li class="wall-line-item wall-tone-${n%3}"><time aria-label="${esc(r.time || r.when)}">${esc(shortTime(r.time || r.when))}</time><span class="wall-dot"></span><div><h3>${esc(nice(r.title))}</h3><div class="wall-line-meta">${secondary?(r.day_offset>0?`<p>${esc(r.day_label)}</p>`:""):`${r.people?.length&&!r.person_title?`<p>${esc(r.people.join(" · "))}</p>`:""}${location(r)?`<p>${esc(location(r))}</p>`:""}${r.detail?`<p class="wall-leave">${icon("car")}${esc(r.leave_at&&r.id!==model.next_movement?.id?"Leave "+clock(r.leave_at):r.detail)}</p>`:""}`}</div></div></li>`).join("")}</ol></section>`;
};
const weather=model.weather;
const temperature=value=>typeof value==="number"&&Number.isFinite(value)?Math.round(value)+"°":null;
const preview=Boolean(model.focus?.preview || night);
const weatherCondition=preview?weather?.forecast_condition:weather?.condition;
const condition=weatherCondition?.replace(/partlycloudy/g,"Partly cloudy").replace(/^./,c=>c.toUpperCase());
const reading=(value,label,primary=false)=>temperature(value)?`<div class="wall-temperature${primary?" wall-temperature-primary":""}"><${primary?"strong":"span"}>${esc(temperature(value))}</${primary?"strong":"span"}><small>${esc(label)}</small></div>`:"";
const weatherLabel=preview?(model.focus?.label || "Tomorrow"):"Weather";
const weatherSummary=[preview?weatherLabel:null,condition,weather?.high==null?"Forecast high unavailable":null].filter(Boolean).join(" · ") || "Weather unavailable";
const weatherImpact=exceptions.find(e=>e.kind==="weather")?.title || (typeof weather?.precipitation_probability==="number"&&weather.precipitation_probability>=60?`${weather.precipitation_probability}% chance of rain`:"");
const weatherPanel=`<section class="wall-weather" aria-label="${esc(weatherLabel)}"><div class="wall-weather-reading">${weatherCondition?icon(["sunny","clear night"].includes(weatherCondition)?"sun":"cloud"):""}${preview?reading(weather?.high,"High",true)+reading(weather?.low,"Low"):reading(weather?.temperature,"Now",true)+reading(weather?.high,"High")}</div><h2>${esc(weatherSummary)}</h2>${weatherImpact?`<p class="wall-weather-impact">${esc(weatherImpact)}</p>`:""}</section>`;
const status=fresh?model.household_status || {}:{};
const statusCell=(kind,label,value,detail)=>{
 if(night&&(kind==="light"&&value==="All off"||kind==="lock"&&value==="Armed"))return "";
 if(label!=="Home"&&(!value||value==="Not selected"))return "";
 const climate=kind==="thermometer"&&detail;
 return `<section class="wall-status-cell" aria-label="${esc(label)}"><span class="wall-status-icon">${icon(kind)}</span><div><h3>${esc(climate?value:label)}</h3><strong>${esc(climate?detail:value || "Status unavailable")}</strong></div></section>`;
};
const household=`<section class="wall-household wall-surface" aria-label="Household status">${statusCell("home","Home",status.home)}${statusCell("thermometer","Climate",temperature(status.climate?.temperature)||status.climate?.detail,temperature(status.climate?.temperature)?status.climate?.detail:"")}${statusCell("lock","Security",status.security)}${statusCell("light","Lights",status.lights)}</section>`;
const cameras=(status.cameras || []).filter(c=>!night||!c.available).slice(0,3);
const cameraPicture=c=>{
 const path=hass.states[c.entity]?.attributes?.entity_picture;
 return c.available&&typeof path==="string"&&path.split("?")[0]===`/api/camera_proxy/${c.entity}`?`<img src="${esc(path)}" alt="${esc(c.name)} camera view">`:icon("camera");
};
const cameraPanel=cameras.length||active.length||model.issues?.length?`<section class="wall-camera-status wall-surface" aria-label="Cameras and active context">${cameras.length?`<div class="wall-camera-heading"><span class="wall-status-icon">${icon("camera")}</span><div><h2>Cameras</h2><p>${esc(cameras.filter(c=>c.available).length+" available")}</p></div></div>`:""}${active.length?`<div class="wall-active-status">${active.map(r=>`<section><h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p></section>`).join("")}</div>`:cameras.length?`<div class="wall-cameras">${cameras.map(c=>`<figure>${cameraPicture(c)}<figcaption>${esc(c.name)}${!c.available?" · Unavailable":""}</figcaption></figure>`).join("")}</div>`:model.issues?.length?`<p class="wall-source-note">${esc(model.issues[0])}</p>`:""}</section>`:"";
const session=model.display_session && valid(model.display_session) ? model.display_session : null;
let picture="";
if(session?.kind==="camera" && /^camera\.[a-z0-9_]+$/.test(session.camera || "")) {
 const path=hass.states[session.camera]?.attributes?.entity_picture;
 if(!["unavailable","unknown"].includes(hass.states[session.camera]?.state)&&typeof path==="string"&&path.split("?")[0]===`/api/camera_proxy/${session.camera}`)picture=`<img src="${esc(path)}" alt="${esc(session.title)} camera view">`;
}
const overlay=session?`<section class="wall-session" aria-label="Temporary display session"><div><h2>${esc(session.title)}</h2>${picture}${session.kind==="camera"&&!picture?"<p>Camera view unavailable</p>":""}<p class="wall-session-body">${esc(session.body)}</p><p>Returns to the family board automatically</p></div></section>`:"";
const alerts=exceptions.filter(r=>r.kind!=="weather");
const primaryAgenda=timeline(model.timeline),secondaryAgenda=night?"":weekPanel || timeline(model.secondary,true);
const body=`<main class="hs-wall" data-fresh="${fresh}" data-night="${night}" data-wall-surface="${esc(cfg.surface_id)}" data-cursor-hidden="${kiosk}" data-state="${esc(model.day_state)}" data-mode="${esc(model.focus?.mode || "today")}" data-phase="${esc(model.phase || "morning")}" data-agenda="${primaryAgenda||secondaryAgenda||weekPanel?"visible":"hidden"}" style="--wall-chrome:${kiosk?0:56}px" aria-label="${esc(cfg.title)} household board">${alerts.length?`<aside class="wall-alerts">${icon("alert")}${esc(alerts.map(r=>r.title+" · "+r.detail).join(" · "))}</aside>`:""}<header class="wall-header"><div class="wall-clock"><time>${esc(date({hour:"numeric",minute:"2-digit",hour12:false}).replace(/^0/,""))}</time><p>${esc(date({weekday:"long",day:"numeric",month:"short"})).replace(",","")}</p></div>${weatherPanel}</header><div class="wall-family${schoolPanel?" wall-family-school":""}" data-count="${schoolPanel?school.children.length:cards.length}" aria-label="${esc(school?.label || "Household plans")}">${schoolPanel || family}</div><aside class="wall-agenda">${primaryAgenda}${secondaryAgenda}</aside><footer class="wall-bottom">${household}${cameraPanel}</footer>${overlay}</main>`;
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
  connectedCallback(){this._cursorGuard ||= cursorGuard(this);this._cursorGuard.set(this.querySelector('.hs-wall'));}
  disconnectedCallback(){this._cursorGuard?.dispose();this._cursorGuard=null;}
  set content(value) {
   if(value===this._content)return;
   this._content=value;
   const generation=this._generation=(this._generation || 0)+1;
   const parsed=document.createElement("template");parsed.innerHTML=value;
   const next=parsed.content.querySelector(".hs-wall"),old=this.querySelector(".hs-wall");
   const keys=root=>[...(root?.querySelectorAll("[data-key]") || [])].map(e=>e.dataset.key).join("|");
   const changed=old&&next&&(keys(old)!==keys(next)||old.dataset.mode!==next.dataset.mode);
   const update=()=>{if(generation===this._generation){this.innerHTML=value;this._cursorGuard?.set(this.querySelector(".hs-wall"));}};
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
