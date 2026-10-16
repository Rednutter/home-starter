const controls = focus.controls || [], players = music?.players || focus.players || [];

const attr = s => s?.attributes || {};

const num = v => typeof v === "number" && Number.isFinite(v);

const stateLabel = s => !usable(s) ? "Unavailable" : ({on:"On",off:"Off",playing:"Playing",paused:"Paused",idle:"Ready",closed:"Closed",open:"Open",opening:"Opening",closing:"Closing",cool:"Cool mode",heat:"Heat mode",fan_only:"Fan mode"}[s.state] || s.state);

const features = s => Number.isInteger(attr(s).supported_features) ? attr(s).supported_features : 0;

const action = (label,command,entity,extra="",disabled=false,ico=null) => `<button type="button" data-command="${command}" data-entity="${esc(entity)}" ${extra}${disabled || state.pending ? " disabled" : ""}>${ico ? icon(ico) : ""}<span>${esc(label)}</span></button>`;

const summary = items => {
  if(!items.length) return "No controls selected";

  const live=items.map(i=>[i,get(i.entity_id)]), lines=[];

  const lights=live.filter(([i,s])=>i.domain === "light" && usable(s) && s.state === "on").length;

  if(lights) lines.push(`${lights} ${lights === 1 ? "light" : "lights"} on`);

  if(live.some(([i,s])=>i.domain === "media_player" && s?.state === "playing")) lines.push("Media playing");

  if(live.some(([i,s])=>i.domain === "fan" && s?.state === "on")) lines.push("Fan on");

  if(live.some(([i,s])=>i.domain === "cover" && usable(s) && s.state !== "closed")) lines.push("Blinds open");

  const climate=live.find(([i,s])=>i.domain === "climate" && usable(s));

  if(climate && num(attr(climate[1]).current_temperature)) lines.push(`${attr(climate[1]).current_temperature}°`);

  if(live.some(([,s])=>!usable(s))) lines.push("Some controls unavailable");

  return lines.join(" · ") || (live.length && live.every(([i,s])=>usable(s) && ["off","closed"].includes(s.state)) ? "All off" : "Room controls");

};

const empty = (title,detail,art) => `<section class="hs-feature hs-feature-art hs-${art}-art"><h2>${esc(title)}</h2><p class="hs-secondary">${esc(detail)}</p></section>`;

const rooms = (list=focus.rooms) => list?.length ? `<div class="hs-feature-grid">${list.map(r=>`<a class="hs-feature hs-room-link" href="${esc(r.path)}">${icon("mdi:home-outline")}<div><h3>${esc(r.name)}</h3><p>${esc(summary(r.controls))}</p></div></a>`).join("")}</div>` : empty("No room controls selected","Choose this view’s rooms and controls in Home Starter.","home");

const projection = get(focus.context_entity), owner=attr(projection).home_starter_context;

const fresh = usable(projection) && owner?.surface === common.surface_id && (owner.person_id || null) === (focus.owner || null) && owner.epoch === common.epoch && Date.now() < Date.parse(attr(projection).valid_until) && Date.now()-Date.parse(attr(projection).checked_at) >= 0 && Date.now()-Date.parse(attr(projection).checked_at)<180000;

const briefing = fresh && Array.isArray(attr(projection).briefing) ? attr(projection).briefing : [];

const briefingHTML = (compact=false) => {

  const rows=briefing.slice(0,compact ? 2 : 7), first=rows[0];

  if(!first && compact) return `<p class="hs-secondary">Your personal briefing is not ready yet.</p>`;

  if(!first) return empty(focus.owner ? "Your Today is not ready yet" : "No verified briefing to show",focus.owner ? "Link personal context in Home Starter. House briefing stays in House." : "Choose and verify household context in Home Starter.","today");

  const row = r => `<article class="hs-briefing-row"><time>${esc(r.when)}</time><div><h3>${esc(r.title)}</h3>${r.detail ? `<p class="hs-secondary">${esc(r.detail)}</p>` : ""}</div></article>`;

  if(compact) return `<p class="hs-secondary">${esc(first.when || "Next")} · ${esc(first.title)}${first.detail ? " · "+esc(first.detail) : ""}</p>`;

  return `<section class="hs-feature hs-feature-art hs-today-art"><h2 class="hs-important">${esc(first.title)}</h2><p class="hs-secondary">${esc(first.when || "Next")}</p>${first.detail ? `<p class="hs-secondary">${esc(first.detail)}</p>` : ""}</section>${rows.length>1 ? `<section class="hs-feature hs-briefing-list">${rows.slice(1).map(row).join("")}</section>` : ""}`;

};

const controlCard = item => {

 const s=get(item.entity_id),a=attr(s),ready=usable(s),f=features(s),id=item.entity_id;

 let buttons="", sliders="", info=stateLabel(s),ico=({light:"mdi:lightbulb-outline",fan:"mdi:fan",climate:"mdi:thermostat",cover:"mdi:blinds-horizontal",media_player:"mdi:speaker",switch:"mdi:power-plug-outline",sensor:"mdi:thermometer",lock:"mdi:lock-outline"}[item.domain] || "mdi:information-outline");

 if(["light","switch","input_boolean","fan"].includes(item.domain) && item.interaction !== "status") {

  buttons=action(s?.state === "on" ? "Turn off" : "Turn on","toggle",id,`aria-pressed="${s?.state === "on"}"`,!ready);

  if(item.domain === "light" && a.supported_color_modes?.some(m=>!["onoff","unknown"].includes(m))) sliders=`<label>Brightness<input type="range" min="1" max="100" value="${num(a.brightness) ? Math.round(a.brightness/255*100) : 1}" data-command="brightness" data-entity="${esc(id)}"${!ready ? " disabled" : ""}></label>`;

  if(item.domain === "fan" && f&1) sliders=`<label>Fan speed<input type="range" min="0" max="100" value="${num(a.percentage) ? a.percentage : 0}" data-command="fan-speed" data-entity="${esc(id)}"${!ready ? " disabled" : ""}></label>`;

 } else if(item.domain === "climate") {

  info=ready ? (s.state === "off" ? "Off" : {cooling:"Cooling",heating:"Heating",idle:"Idle",fan:"Fan only"}[a.hvac_action] || stateLabel(s)) : "Unavailable";

  if(num(a.current_temperature)) info+=` · Currently ${a.current_temperature}°`;

  if(f&1 && num(a.temperature)) buttons=action("Decrease target","temperature-down",id,"",!ready,"mdi:minus")+`<span class="hs-important">${esc(a.temperature)}°</span>`+action("Increase target","temperature-up",id,"",!ready,"mdi:plus");

  if(Array.isArray(a.hvac_modes)) buttons+=a.hvac_modes.map(m=>action(({off:"Off",cool:"Cool",heat:"Heat",auto:"Auto",fan_only:"Fan",dry:"Dry"}[m] || m),"climate-mode",id,`data-value="${esc(m)}" aria-pressed="${s?.state === m}"`,!ready)).join("");

 } else if(item.domain === "cover" && !["garage","gate","door","damper"].includes(item.device_class)) {

  buttons=(f&1 ? action("Open","cover-open",id,"",!ready) : "")+(f&8 ? action("Stop","cover-stop",id,"",!ready) : "")+(f&2 ? action("Close","cover-close",id,"",!ready) : "");

 } else if(item.domain === "media_player") {

  const mediaPath=focus.owner ? common.base+"/person-"+Array.from(new TextEncoder().encode(focus.owner),b=>b.toString(16).padStart(2,"0")).join("")+"-music" : common.base+"/music";

  buttons=link("Open Media",mediaPath,"mdi:music");

 } else if(item.domain === "sensor" && ready) info=s.state+(a.unit_of_measurement ? " "+a.unit_of_measurement : "");

 // Locks, gates, security, scenes and scripts are status only here. No guessed action.

 return `<section class="hs-control"><div class="hs-control-head">${icon(ico)}<div><h2>${esc(item.name)}</h2><p>${esc(info)}</p></div></div>${buttons ? `<div class="hs-control-actions">${buttons}</div>` : ""}${sliders}</section>`;

};

// Provider projections are listener/call/camera state, never inferred from a speaker.

const adapter = feature => {

 const binding=focus.bindings?.[feature],source=get(binding?.entity_id),a=attr(source),proof=a.home_starter_capability;

 if(!binding || !usable(source) || proof?.surface !== common.surface_id || proof.epoch !== common.epoch || (proof.person_id || null) !== (focus.owner || null) || proof.feature !== feature || proof.revision !== binding.revision || !(Date.now() < Date.parse(a.valid_until)) || !(Date.now()-Date.parse(a.checked_at)>=0 && Date.now()-Date.parse(a.checked_at)<180000)) return null;

 return a.value && typeof a.value === "object" && !Array.isArray(a.value) ? a.value : null;

};

const supportedAction = (feature,name) => {

 const spec=focus.bindings?.[feature]?.actions?.[name];

 return spec && /^[a-z_]+$/.test(spec.domain) && /^[a-z0-9_]+$/.test(spec.service) && hass.services?.[spec.domain]?.[spec.service] ? spec : null;

};

const adapterButton = (feature,name,label,value="") => supportedAction(feature,name) ? `<button type="button" data-adapter="${feature}" data-provider-action="${name}" data-value="${esc(value)}"${(state.pending || feature === "listening" && ["resume","play"].includes(name) && !players.some(p=>p.entity_id === state.destination && usable(get(p.entity_id)))) ? " disabled" : ""}>${esc(label)}</button>` : "";

const listeningHTML = () => {
 if(musicBackend) return musicLibrary();

 const listening=adapter("listening");

 if(!listening || listening.listener_id !== focus.owner) return empty(focus.bindings?.listening ? "Your listening is unavailable" : "Personal library not connected","Favourites, audiobook progress and bedtime playback will appear when this listener’s service is commissioned.","media");

 const book=listening.audiobook,delay=listening.delayed_start,seconds=delay?.start_at ? Math.max(0,Math.ceil((Date.parse(delay.start_at)-Date.now())/1000)) : 0;

 return `<section class="hs-feature"><h2>Your listening</h2>${book && num(book.position) && num(book.duration) && book.duration>0 && book.position>=0 && book.position<=book.duration ? `<h3>${esc(book.title)}</h3><p class="hs-secondary">${Math.floor(book.position/60)} of ${Math.floor(book.duration/60)} minutes</p><div class="hs-control-actions">${adapterButton("listening","resume","Continue audiobook",book.id)}</div>` : ""}${seconds ? `<p class="hs-secondary">Starts in ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}</p><div class="hs-control-actions">${adapterButton("listening","cancel_delay","Cancel",delay.id)}${adapterButton("listening","start_now","Start now",delay.id)}</div>` : ""}${listening.sleep_timer?.ends_at ? `<p class="hs-secondary">Sleep timer ends ${esc(new Intl.DateTimeFormat(hass.locale?.language || undefined,{hour:"numeric",minute:"2-digit",timeZone:hass.config.time_zone}).format(new Date(listening.sleep_timer.ends_at)))}</p>${adapterButton("listening","cancel_sleep","Cancel sleep timer",listening.sleep_timer.id)}` : ""}${["mine","shared","house"].filter(k=>Array.isArray(listening[k]) && listening[k].length).map(k=>`<h3>${{mine:"Mine",shared:"Shared",house:"House"}[k]}</h3><div class="hs-inline-links">${listening[k].slice(0,6).map(item=>adapterButton("listening","play","Play "+item.title,item.id) || `<span class="hs-secondary">${esc(item.title)}</span>`).join("")}</div>`).join("")}${supportedAction("listening","delay") ? `<label>Start listening<select data-adapter="listening" data-provider-action="delay"><option value="0">Now</option><option value="300">5 min</option><option value="600">10 min</option><option value="900">15 min</option></select></label><label>Start at<input type="time" data-adapter="listening" data-provider-action="start_at"></label>` : ""}${supportedAction("listening","sleep") ? `<label>Sleep timer<select data-adapter="listening" data-provider-action="sleep"><option value="0">Off</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">1 hour</option></select></label>` : ""}</section>`;

};

const callHTML = () => {

 const call=adapter("call");

 if(!call) return empty(focus.bindings?.call ? "Calling unavailable" : "Calling not set up","No callable destinations are commissioned for this view.","call");

 if(["incoming","active","dialing"].includes(call.state)) {

  const duration=call.state === "active" && Date.parse(call.started_at)<=Date.now() ? Math.floor((Date.now()-Date.parse(call.started_at))/1000) : null;

  return `<section class="hs-feature hs-feature-art hs-call-art"><h2>${esc(call.state === "incoming" ? "Incoming call" : call.state === "dialing" ? "Calling" : "In call")}</h2><p class="hs-important">${esc(call.label)}</p>${duration !== null ? `<p class="hs-secondary">${Math.floor(duration/60)}:${String(duration%60).padStart(2,"0")}</p>` : ""}<div class="hs-control-actions">${call.state === "incoming" ? adapterButton("call","answer","Answer",call.id)+adapterButton("call","reject","Reject",call.id) : adapterButton("call","mute",call.muted ? "Unmute" : "Mute",call.id)+adapterButton("call","end","End call",call.id)}</div></section>`;

 }

 return call.destinations?.length ? `<section class="hs-feature"><h2>Who would you like to call?</h2><div class="hs-feature-grid">${call.destinations.slice(0,16).map(d=>adapterButton("call","start",d.name,d.id)).join("")}</div></section>` : empty("No callable destinations","Review this view’s calling destinations in Home Starter.","call");

};

const cameraHTML = () => {

 const value=adapter("camera"),cameras=focus.bindings?.camera?.cameras || [];

 if(!value || !cameras.length) return empty(focus.bindings?.camera ? "Camera connection unavailable" : "No cameras commissioned","Choose and verify a camera in Home Starter. Door and gate actions need their own confirmed association.","camera");

 const event=value.event && !state.dismissed?.includes(value.event.id) ? value.event : null;

 const selected=cameras.find(c=>c.entity_id === (event?.camera_entity_id || state.camera)) || cameras[0],s=get(selected.entity_id),picture=attr(s).entity_picture;

 const image=usable(s) && typeof picture === "string" && /^\/api\/camera_proxy\//.test(picture) ? picture : null;

 const entry=(focus.bindings.camera.entry || []).find(e=>e.camera_entity_id === selected.entity_id && e.allowed_users?.includes(hass.user?.id));

 return `<section class="hs-feature"><h2>${esc(event?.label || selected.name)}</h2>${image ? `<img class="hs-camera-image" src="${esc(image)}" alt="${esc(selected.name)} camera image">` : '<p class="hs-secondary">Camera image unavailable</p>'}<div class="hs-control-actions">${adapterButton("camera","talk","Talk",selected.entity_id)}${entry && event && supportedAction("camera",entry.action) ? adapterButton("camera",entry.action,"Open",entry.id) : ""}${event ? '<button data-dismiss="'+esc(event.id)+'">Dismiss</button>' : ""}</div></section>${!event ? `<section class="hs-feature"><h2>Cameras</h2><div class="hs-feature-grid">${cameras.map(c=>`<button data-camera="${esc(c.entity_id)}" aria-pressed="${c.entity_id === selected.entity_id}">${esc(c.name)}</button>`).join("")}</div></section>` : ""}`;

};

const mediaHTML = () => {
 if(musicBackend && !music) return musicLibrary();

 if(!players.length) return empty("No speaker selected","Choose a listening destination in Home Starter. Speakers remain shared house devices.","media")+(musicBackend || focus.owner ? listeningHTML() : "");

 if(!players.some(p=>p.entity_id === state.destination)) state.destination=music?.default_destination || focus.default_destination;

 if(!state.destination) return empty("Where would you like to listen?","Choose a permitted speaker for this listening view.","media")+`<section class="hs-feature"><div class="hs-feature-grid">${players.map(p=>action(p.name,"destination",p.entity_id,"",(!usable(get(p.entity_id)) || musicBackend && (!p.available || !p.single)),"mdi:speaker")).join("")}</div></section>`;

 const player=players.find(p=>p.entity_id === state.destination) || players[0],s=get(player.entity_id),a=attr(s),ready=usable(s) && (!musicBackend || player.available && player.single),f=features(s);

 const picture=typeof a.entity_picture === "string" && /^\/api\/media_player_proxy\//.test(a.entity_picture) ? a.entity_picture : null;

 const title=a.media_title || (s?.state === "playing" ? "Playing" : "Choose something to listen to");

 const transport=(f&16 ? action("Previous","previous",player.entity_id,"",!ready,"mdi:skip-previous") : "")+(s?.state === "playing" && f&1 ? action("Pause","pause",player.entity_id,"",!ready,"mdi:pause") : s?.state !== "playing" && f&16384 ? action("Play","play",player.entity_id,"",!ready,"mdi:play") : "")+(f&32 ? action("Next","next",player.entity_id,"",!ready,"mdi:skip-next") : "");

 return `${focus.owner ? '<p class="hs-quiet">Your listening view · destinations are shared.</p>' : ""}<section class="hs-feature"><div class="hs-media-layout">${picture ? `<img class="hs-artwork" src="${esc(picture)}" alt="Current media artwork">` : `<div class="hs-artwork-fallback">${icon("mdi:music")}</div>`}<div><p class="hs-secondary">${esc(stateLabel(s))} · ${esc(player.name)}</p><h2>${esc(title)}</h2>${a.media_artist || a.media_album_name ? `<p class="hs-secondary">${esc(a.media_artist || a.media_album_name)}</p>` : ""}<div class="hs-control-actions">${transport}</div></div></div></section><section class="hs-feature"><h2>Where to listen</h2><div class="hs-feature-grid">${players.map(p=>action(p.name,"destination",p.entity_id,`aria-pressed="${p.entity_id === state.destination}"`,(!usable(get(p.entity_id)) || musicBackend && (!p.available || !p.single)),"mdi:speaker")).join("")}</div>${!musicBackend && f&524288 && hass.services?.media_player?.join ? `<div class="hs-control-actions">${players.filter(p=>p.entity_id !== player.entity_id && usable(get(p.entity_id)) && features(get(p.entity_id))&524288).map(p=>action("Group with "+p.name,"group",player.entity_id,`data-value="${esc(p.entity_id)}"`)).join("")}${a.group_members?.length>1 && hass.services?.media_player?.unjoin ? action("Separate speaker","ungroup",player.entity_id) : ""}</div>` : ""}${f&4 ? `<label>Speaker volume<input type="range" min="0" max="100" value="${num(a.volume_level) ? Math.round(a.volume_level*100) : 0}" data-command="volume" data-entity="${esc(player.entity_id)}"${!ready ? " disabled" : ""}></label><p class="hs-quiet">Speaker’s own scale · household volume calibration is not set up.</p>` : ""}</section>${musicBackend || focus.owner ? listeningHTML() : ""}`;

};

let body="";

if(focus.kind === "dark") body=`<section class="hs-dark"><p class="hs-quiet">Screen resting</p>${link("Wake",common.base+"/home","mdi:gesture-tap")}</section>`;
else if(focus.kind === "ambient") body=`<section class="hs-feature hs-feature-art"><h2>House at rest</h2><p class="hs-secondary">${esc(summary(controls))}</p><div class="hs-inline-links">${link("Active",common.base+"/home","mdi:home-outline")}${link("Dark",common.base+"/dark","mdi:monitor-off")}</div></section>${fresh && briefing.length ? briefingHTML(true) : ""}`;
else if(focus.kind === "today") body=briefingHTML();

else if(focus.kind === "call") body=callHTML();

else if(focus.kind === "camera") body=cameraHTML();

else if(focus.kind === "media") body=mediaHTML();

else if(focus.kind === "rooms") body=`<section class="hs-feature"><h2>Home at a glance</h2><p class="hs-secondary">${esc(summary(controls))}</p></section>${rooms()}<div class="hs-inline-links">${link("Around the house",common.base+"/"+(focus.owner ? focus.path.replace(/rooms$/,"context") : "context"),"mdi:information-outline")}</div>`;

else if(focus.kind === "room" || focus.kind === "context") body=controls.length ? `<div class="hs-feature-grid">${controls.map(controlCard).join("")}</div>` : empty("Nothing selected for this view","Review this view’s sources in Home Starter.","home");

else if(focus.kind === "person") {

 const own=(focus.rooms || []).filter(r=>focus.default_rooms.includes(r.id));

 const destination=players.find(p=>p.entity_id === focus.default_destination);
 body=`<div class="hs-person-grid"><section><h2 class="hs-section-title">Your room</h2>${rooms(own)}</section><section><h2 class="hs-section-title">Your listening</h2><div class="hs-feature hs-feature-art hs-media-art hs-person-summary"><h3>${esc(destination?.name || (players.length ? "Choose where to listen" : "No speaker selected"))}</h3><p class="hs-secondary">${esc(destination ? stateLabel(get(destination.entity_id)) : players.length ? "Choose a permitted destination." : "Choose a default room in Home Starter.")}</p><div class="hs-inline-links">${link("Open your Media",focus.destinations.media,"mdi:music")}</div></div></section></div><section class="hs-feature hs-person-today"><div><h2>Your Today</h2>${briefingHTML(true)}</div><div class="hs-inline-links">${link("Your Today",focus.destinations.today,"mdi:calendar-blank-outline")}${link("Shared controls",focus.destinations.rooms,"mdi:home-outline")}${link("Call",focus.destinations.call,"mdi:phone-outline")}</div></section>${focus.supervision?.length ? `<section class="hs-feature"><h2>Family views</h2><p class="hs-quiet">Shared household views; opening a person does not sign in as them.</p><div class="hs-inline-links">${focus.supervision.map(p=>link(p.name,p.path,"mdi:account-circle-outline")).join("")}</div></section>` : ""}`;

} else if(focus.kind === "settings") body=`<section class="hs-feature"><h2>Display settings</h2><p class="hs-secondary">Profile, appearance and app settings stay in Home Assistant.</p><div class="hs-inline-links">${link("Profile / app settings","/profile","mdi:cog-outline")}${link("Panel mode",common.base+"/home","mdi:fullscreen")}${link("Exit panel","/lovelace/0?disable_km","mdi:exit-to-app")}</div></section>`;

const command = async event => {

 const el=event.target.closest?.('[data-command]');if(!el) return;

 event.stopPropagation();event.preventDefault();

 const kind=el.dataset.command,id=el.dataset.entity,item=controls.find(i=>i.entity_id === id),player=players.find(i=>i.entity_id === id),s=get(id),a=attr(s),f=features(s);

 if(musicBackend && player && ["destination","play","pause","next","previous","volume"].includes(kind)) {
  if(kind === "destination") {state.destination=id;await musicAction("destination");}
  else await musicAction(kind,{player:id,...(kind === "volume" ? {value:+el.value}:{})});
  return;
 }

 if(kind === "destination" && player && usable(s)) {state.destination=id;state.error="";this.requestUpdate();return;}

 if(state.pending || !usable(s) || (!item && !player)) return;

 const domain=item?.domain || "media_player";

 let service=null,data={entity_id:id};

 if(kind === "toggle" && item && ["light","switch","input_boolean","fan"].includes(domain) && item.interaction !== "status") service=[domain,s.state === "on" ? "turn_off" : "turn_on"];

 if(kind === "brightness" && domain === "light" && a.supported_color_modes?.some(m=>!["onoff","unknown"].includes(m)) && num(+el.value) && +el.value>=1 && +el.value<=100) {service=["light","turn_on"];data.brightness_pct=+el.value;}

 if(kind === "fan-speed" && domain === "fan" && f&1 && +el.value>=0 && +el.value<=100) {service=["fan","set_percentage"];data.percentage=+el.value;}

 if(["temperature-down","temperature-up"].includes(kind) && domain === "climate" && f&1 && num(a.temperature)) {service=["climate","set_temperature"];const delta=(num(a.target_temp_step) ? a.target_temp_step : 1)*(kind === "temperature-up" ? 1 : -1);data.temperature=Math.round(Math.max(a.min_temp ?? 7,Math.min(a.max_temp ?? 35,a.temperature+delta))*10)/10;}

 if(kind === "climate-mode" && domain === "climate" && a.hvac_modes?.includes(el.dataset.value)) {service=["climate","set_hvac_mode"];data.hvac_mode=el.dataset.value;}

 if(kind.startsWith('cover-') && domain === "cover" && !["garage","gate","door","damper"].includes(item.device_class)) {const ops={"cover-open":[1,"open_cover"],"cover-close":[2,"close_cover"],"cover-stop":[8,"stop_cover"]};if(ops[kind] && f&ops[kind][0]) service=["cover",ops[kind][1]];}

 if(player && f&524288 && kind === "group" && hass.services?.media_player?.join && players.some(p=>p.entity_id === el.dataset.value && usable(get(p.entity_id)) && features(get(p.entity_id))&524288)) {service=["media_player","join"];data.group_members=[el.dataset.value];}

 if(player && f&524288 && kind === "ungroup" && hass.services?.media_player?.unjoin) service=["media_player","unjoin"];

 const mediaOps={previous:[16,"media_previous_track"],next:[32,"media_next_track"],pause:[1,"media_pause"],play:[16384,"media_play"],volume:[4,"volume_set"]};

 if(player && mediaOps[kind] && f&mediaOps[kind][0]) {service=["media_player",mediaOps[kind][1]];if(kind === "volume") {if(!num(+el.value) || +el.value<0 || +el.value>100)return;data.volume_level=+el.value/100;}}

 if(!service) return;

 try {state.pending=true;state.error="";this.requestUpdate();await hass.callService(service[0],service[1],data);}

 catch {state.error="That control did not respond. Check the device and try again.";}

 finally {state.pending=false;this.requestUpdate();}

};

const providerCommand = async event => {

 const el=event.target.closest?.('[data-adapter]');if(!el) return;

 const feature=el.dataset.adapter,name=el.dataset.providerAction,value=el.value ?? el.dataset.value,source=adapter(feature),spec=supportedAction(feature,name);

 if(!source || !spec || state.pending || (feature === "listening" && source.listener_id !== focus.owner)) return;

 let allowed=[];

 if(feature === "call") allowed=name === "start" ? (source.destinations || []).map(d=>d.id) : [source.id];

 if(feature === "camera") allowed=name === "talk" ? (focus.bindings.camera.cameras || []).map(c=>c.entity_id) : (focus.bindings.camera.entry || []).filter(e=>e.allowed_users?.includes(hass.user?.id) && e.action === name && e.camera_entity_id === source.event?.camera_entity_id).map(e=>e.id);

 if(feature === "listening") {

  allowed=name === "resume" ? [source.audiobook?.id] : ["start_now","cancel_delay"].includes(name) ? [source.delayed_start?.id] : name === "cancel_sleep" ? [source.sleep_timer?.id] : ["mine","shared","house"].flatMap(k=>(source[k] || []).map(i=>i.id));

  if(["resume","play"].includes(name) && !players.some(p=>p.entity_id === state.destination && usable(get(p.entity_id)))) return;

 }

 if(["delay","sleep"].includes(name)) {if(!["0","300","600","900","1800","3600"].includes(value)) return;}

 else if(name === "start_at") {if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) return;}

 else if(!allowed.includes(value)) return;

 const data={...spec.data};

 if(spec.value_parameter && /^[a-z_]+$/.test(spec.value_parameter)) data[spec.value_parameter]=value;

 if(["resume","play","delay","start_at"].includes(name) && spec.destination_parameter && players.some(p=>p.entity_id === state.destination)) data[spec.destination_parameter]=state.destination;

 try {state.pending=true;state.error="";this.requestUpdate();await hass.callService(spec.domain,spec.service,data);}

 catch {state.error="That action did not respond. Check the service and try again.";}

 finally {state.pending=false;this.requestUpdate();}

};

const change = event => {event.stopPropagation();if(event.target.closest?.("[data-music]")) {musicEvent(event);return;}if(event.target.closest?.('[data-adapter]')) void providerCommand(event);else void command(event);};

const click = event => {
 if(event.target.closest?.("[data-music]")) {if(!["SELECT","INPUT"].includes(event.target.tagName))musicEvent(event);return;}


 const camera=event.target.closest?.('[data-camera]'),dismiss=event.target.closest?.('[data-dismiss]');

 if(camera && focus.bindings?.camera?.cameras.some(c=>c.entity_id === camera.dataset.camera)) {state.camera=camera.dataset.camera;this.requestUpdate();return;}

 if(dismiss) {state.dismissed=[...(state.dismissed || []),dismiss.dataset.dismiss];this.requestUpdate();return;}

 if(event.target.closest?.('[data-adapter]')) {event.stopPropagation();if(!["SELECT","INPUT"].includes(event.target.tagName)) void providerCommand(event);return;}

 if(event.target.closest?.('[data-command]')) {if(event.target.type !== "range") void command(event);} else navigate(event);};

return html`<div class="hs-page-content" @click=${click} @change=${change} @submit=${musicSearch} @input=${musicInput} @mousedown=${stop} @touchstart=${stop} @touchend=${stop} .innerHTML=${(state.error ? `<p class="hs-feedback" role="alert">${esc(state.error)}</p>` : "")+body}></div>`;
