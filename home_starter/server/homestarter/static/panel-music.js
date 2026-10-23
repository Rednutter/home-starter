// Calls use the signed-in HA ingress identity; provider credentials never enter the page.
const musicBackend = typeof common.music_backend === "string" && /^[a-zA-Z0-9_]+$/.test(common.music_backend) ? common.music_backend : null;
const musicScope = focus.owner || null;
const musicState = state.music || (state.music={view:null,at:0,loading:false,folder:null,query:"",delay:0});
const musicRows = rows => Array.isArray(rows) && rows.every(row=>row && typeof row==="object" && !Array.isArray(row));
const validMusicView = value => value?.person_id === musicScope && value?.epoch === common.epoch && ["players","library","favorites","recent","books"].every(key=>musicRows(value[key])) && ["shared","channels","sessions"].every(key=>value[key]==null || musicRows(value[key])) && (value.regional_radio==null || musicRows(value.regional_radio.items));
const music = validMusicView(musicState.view) ? musicState.view : null;
const musicWait = (promise,signal) => new Promise((resolve,reject)=>{
 const abort=()=>reject(Error("Listening timed out"));
 if(signal.aborted){abort();return;}
 signal.addEventListener("abort",abort,{once:true});
 Promise.resolve(promise).then(resolve,reject).finally(()=>signal.removeEventListener("abort",abort));
});
const musicURL = async signal => {
 if(!this._hsMusicEntry) {
  const info=await musicWait(hass.callWS({type:"supervisor/api",endpoint:"/addons/"+musicBackend+"/info",method:"get"}),signal);
  if(!/^\/api\/hassio_ingress\/[a-zA-Z0-9_-]+\/?$/.test(info.ingress_entry || "")) throw Error("invalid ingress");
  const session=await musicWait(hass.callWS({type:"supervisor/api",endpoint:"/ingress/session",method:"post"}),signal);
  document.cookie="ingress_session="+encodeURIComponent(session.session)+";path=/api/hassio_ingress/;SameSite=Strict"+(window.location.protocol === "https:" ? ";Secure" : "");
  this._hsMusicEntry=info.ingress_entry.replace(/\/$/,"");
 }
 const params=new URLSearchParams();
 if(focus.owner) params.set("person",focus.owner);
 if(musicState.folder) params.set("folder",musicState.folder);
 if(musicState.query) params.set("query",musicState.query);
 return this._hsMusicEntry+"/api/listening/"+encodeURIComponent(common.surface_id)+"?"+params;
};
const musicRequest = async body => {
 if(!body && state.pending)return;
 const sequence=musicState.sequence=(musicState.sequence || 0)+1;
 musicState.loading=true;
 const signal=AbortSignal.timeout(body ? 150000:12000);
 try {
  let response=await fetch(await musicURL(signal),{method:body ? "POST":"GET",credentials:"same-origin",headers:body ? {"Content-Type":"application/json"}:{},...(body ? {body:JSON.stringify({...body,epoch:common.epoch})}:{}),signal});
  if(response.status === 401){this._hsMusicEntry=null;throw Error("session expired");}
  const value=await musicWait(response.json(),signal);
  if(sequence!==musicState.sequence || this._hsPage!==state)return;
  if(!response.ok) {musicState.view=null;state.error=typeof value.error === "string" ? value.error : "Listening did not respond. Check Music Assistant and retry.";return;}
  if(!validMusicView(value)) throw Error("invalid listening response");
  musicState.view=value;state.error="";
  if(["transfer_confirm","transfer_recheck"].includes(body?.action) && !value.transfer?.pending && value.default_destination)state.destination=value.default_destination;
  if(!state.destination && value.default_destination) state.destination=value.default_destination;
 } catch {if(sequence!==musicState.sequence || this._hsPage!==state)return;musicState.view=null;state.error="Listening could not be confirmed. Check Music Assistant and the speaker before retrying.";}
 finally {if(sequence===musicState.sequence && this._hsPage===state){musicState.loading=false;musicState.at=Date.now();this.requestUpdate();}}
};
if(musicBackend && ["media","person"].includes(focus.kind) && !musicState.loading && !musicState.editing && Date.now()-musicState.at>5000) void musicRequest();
const musicAction = async (action,extra={}) => {
 if(state.pending || musicState.loading) return;
 musicState.editing=false;state.pending=true;state.error="";this.requestUpdate();
 try {await musicRequest({action,player:state.destination,...(["queue_join","queue_add","queue_next","queue_move","queue_remove","queue_takeover_prepare","queue_takeover"].includes(action) ? {session:musicSession?.revision}:{}),...extra});} finally {state.pending=false;this.requestUpdate();}
};
const musicButton = (label,action,item,extra="") => `<button type="button" data-music="${action}"${item ? ` data-item="${esc(item)}"`:""}${extra}${state.pending || musicState.loading ? " disabled":""}>${esc(label)}</button>`;
const musicSelected=music?.players?.find(p=>p.entity_id===state.destination);
const musicSession=music?.sessions?.find(s=>s.player_id===musicSelected?.player_id);
const musicOccupied=!!musicSession?.owner && !musicSession.owned || ["playing","paused","buffering"].includes(musicSelected?.state) && !musicSession?.owned;
const musicLibrary = () => {
 if(!music) return `<section class="hs-feature"><h2>Your audio</h2><p class="hs-secondary">${musicState.loading ? "Reading your listening choices…":"Listening is unavailable. Try again shortly."}</p>${musicButton("Retry","refresh")}</section>`;
 const items = rows => `<div class="hs-library-list">${rows.map(r=>`<article class="hs-library-row"><div><h3>${esc(r.title)}</h3><p class="hs-quiet">${esc(({track:"Song",album:"Album",playlist:"Playlist",sound_effect:"Ambient sound",radio:"Radio",podcast:"Podcast",audiobook:"Audiobook",artist:"Artist",podcast_episode:"Episode",folder:"Collection"})[r.kind] || "Music")}</p></div><div class="hs-control-actions">${r.folder ? musicButton("Open","folder",r.id) : musicButton(musicSession?.owned ? "Replace my queue":"Play","start",r.id,musicOccupied || musicSelected?.transfer_pending ? " disabled":"")+(musicSession?.can_add && r.queueable && (!r.source_scoped || musicSession.source_scoped) ? musicButton("Add to queue","queue_add",r.id):"")+(musicSession?.can_next && r.queueable && (!r.source_scoped || musicSession.source_scoped) ? musicButton("Play Next","queue_next",r.id):"")+musicButton(music.favorites.some(f=>f.id === r.id) ? "Saved":"Save",music.favorites.some(f=>f.id === r.id) ? "unfavorite":"favorite",r.id)}</div></article>`).join("")}</div>`;
 const takeover=music.takeover?.player_id===musicSelected?.player_id && music.takeover?.revision===musicSession?.revision ? music.takeover:null;
 const confirmTakeover=takeover ? `<section class="hs-feature"><h2>Confirm queue takeover</h2><p class="hs-secondary">Take control of ${esc(musicSession.owner)}'s queue on ${esc(musicSelected.name)}? Contents and playback state stay the same. Its sleep timer will be cleared. Personal progress stays separate.</p><div class="hs-control-actions">${musicButton("Confirm takeover","queue_takeover")}${musicButton("Cancel takeover","queue_takeover_cancel")}</div></section>`:"";
 const queueRows=musicSession?.queue?.length ? `<ol>${musicSession.queue.map(r=>`<li><p>${esc(r.title)}${r.current ? " (now playing)":""}</p>${musicSession.can_edit ? `<div class="hs-control-actions">${musicButton("Up","queue_move",null,` data-entry="${esc(r.entry)}" data-shift="-1"${r.up ? "":" disabled"}`)}${musicButton("Down","queue_move",null,` data-entry="${esc(r.entry)}" data-shift="1"${r.down ? "":" disabled"}`)}${musicButton("Remove","queue_remove",null,` data-entry="${esc(r.entry)}"${r.remove ? "":" disabled"}`)}</div>`:""}</li>`).join("")}</ol>`:"";
 const move=music.transfer,plan=move?.plan;
 const transfer=move?.source_entity || move?.notice ? `<section class="hs-feature"><h2>${plan ? "Confirm playback move":"Move playback"}</h2>${move.notice ? `<p class="hs-secondary">${esc(move.notice)}</p>`:""}${move.pending ? musicButton("Check move","transfer_recheck"):plan ? `<p>Move your queue from ${esc(plan.source_name || move.source_name || "this speaker")} to ${esc(plan.target_name)}? The destination is checked again; the timer deadline stays the same.</p><div class="hs-control-actions">${musicButton("Confirm move","transfer_confirm")}${musicButton("Cancel move","transfer_cancel")}</div>`:move.issue ? `<p class="hs-secondary">${esc(move.issue)}</p>`:`<p class="hs-secondary">From ${esc(move.source_name || "this speaker")}. Choose an empty speaker, then review the move.</p><div class="hs-control-actions">${(move.targets || []).map(p=>musicButton("Move to "+p.name,"transfer_prepare",p.entity_id)).join("")}</div>`}</section>`:"";
 const searchNotice=music.search ? `<section class="hs-feature"><h2>Search coverage</h2><p class="hs-secondary">${esc(music.search.coverage)}</p>${music.search.issue ? `<p class="hs-secondary">${esc(music.search.issue)}</p>`:""}${music.search.incomplete ? `<p class="hs-quiet">Some sources or further matches are unavailable. Refine your search for more.</p>`:""}</section>`:"";
 const participation=musicSession?.owner ? `<section class="hs-feature"><h2>Selected listening session</h2><p class="hs-secondary">${esc(musicSession.owner)} owns this queue.</p>${musicSession.joined ? '<p class="hs-quiet">Joined listening. Controls and progress stay with the owner.</p>':""}<div class="hs-control-actions">${musicSession.can_join ? musicButton("Join listening","queue_join"):""}${musicSession.joined ? musicButton("Leave listening","queue_leave"):""}${musicSession.can_takeover && !takeover ? musicButton("Review takeover","queue_takeover_prepare"):""}</div>${queueRows}${musicSession.issue || musicSession.edit_issue ? `<p class="hs-secondary">${esc(musicSession.issue || musicSession.edit_issue)}</p>`:""}<p class="hs-quiet">Choose another speaker from the room controls to start your own session.</p></section>`:musicSession?.issue ? `<section class="hs-feature"><h2>Selected listening session</h2><p class="hs-secondary">${esc(musicSession.issue)}</p></section>`:"";
 const bookState=music.audiobooks;
 const bookPeople=bookState?.state === "choose_listener" ? (common.people || []).filter(p=>typeof p.path === "string" && p.path.startsWith(common.base+"/person-")) : [];
 const bookSetup=bookState ? `<section class="hs-feature"><h2>Audiobooks</h2><p class="hs-secondary">${esc(bookState.message)}</p>${bookPeople.length ? `<div class="hs-control-actions">${bookPeople.map(p=>link(p.name+"’s books",p.path+"-music","mdi:book-open-page-variant")).join("")}</div>`:""}</section>` : "";
 const books=music.books || [];
 const discoveryChoice=musicState.discoveryChoice || "anything";
 musicState.discoveryOptions=()=>discoveryChoice.startsWith("era:") ? {mode:"era",era:discoveryChoice.slice(4) === "current" ? "current":+discoveryChoice.slice(4)} : discoveryChoice.startsWith("genre:") ? {mode:"genre",genre:discoveryChoice.slice(6)} : {mode:"anything"};
 const discovery=music.discovery ? `<section class="hs-feature"><h2>Music</h2><div class="hs-control-actions">${musicButton("Surprise Me","surprise_me")}${music.session ? (music.keep_it_going ? musicButton("Keep It Going","keep_it_going"):"")+musicButton("Something different","something_different"):""}</div><label>Explore<select data-music="discovery-choice">${[["anything","Anything"],["era:1960","60s"],["era:1970","70s"],["era:1980","80s"],["era:1990","90s"],["era:2000","2000s"],["era:2010","2010s"],["era:current","Current"],["genre:rock","Rock"],["genre:pop","Pop"],["genre:jazz","Jazz"],["genre:classical","Classical"],["genre:electronic","Electronic"]].map(([v,l])=>`<option value="${v}"${v===discoveryChoice ? " selected":""}>${l}</option>`).join("")}</select></label><p class="hs-quiet">Explore the music catalogue. Keep It Going follows the current music.</p></section>`:"";
 const discoveryStatus=!music.discovery && music.discovery_issue ? `<section class="hs-feature"><h2>Music</h2><p class="hs-secondary">${esc(music.discovery_issue)}</p></section>`:"";
 const channels=[["radio","Radio"],["music","Music stations"],["ambient","Ambient"]].map(([category,label])=>{const rows=(music.channels || []).filter(r=>r.category===category);return rows.length ? `<section class="hs-feature"><h2>${label}</h2>${category === "ambient" ? '<p class="hs-quiet">Background audio without a music account.</p>':""}${items(rows)}</section>`:"";}).join("");
 const delay=music.delayed,seconds=delay ? Math.max(0,Math.ceil(delay.at-Date.now()/1000)) : 0;
 const browsing=`${music.browse ? `<section class="hs-feature"><h2>${esc(music.search ? "Search results":music.collection?.title || "Collections")}</h2>${music.collection ? `<p class="hs-quiet">${music.collection.total} ${music.collection.search ? "matches · refine your search for more":"items across your connected sources"}</p>${music.collection.incomplete ? '<p class="hs-secondary">Some sources are temporarily unavailable. This collection may be incomplete.</p>':""}`:""}<form class="hs-control-actions" data-music-search><label>Find music, radio, podcasts or books<input type="search" name="query" maxlength="100" value="${esc(musicState.query)}"></label><button type="submit"${state.pending || musicState.loading ? " disabled":""}>Search</button></form><div class="hs-control-actions">${musicState.back?.length ? musicButton("Back to choices","back"):""}${musicState.query ? musicButton("Clear search","clear-search"):""}${musicButton("All collections","root")}</div><label>Start playback<select data-music="delay-choice"><option value="0"${!musicState.delay ? " selected":""}>Now</option>${[300,600,900].map(v=>`<option value="${v}"${musicState.delay === v ? " selected":""}>${v/60} min</option>`).join("")}</select></label>${music.library.length ? items(music.library) : '<p class="hs-secondary">No matches here. Try another search or return to your choices.</p>'}</section>`:'<section class="hs-feature"><h2>Your listening</h2><p class="hs-secondary">Your saved choices and progress stay with your household view.</p></section>'}`;
 return `${browsing}${transfer}${searchNotice}${confirmTakeover}${participation}${discovery}${discoveryStatus}${channels}${bookSetup}${books.length ? `<section class="hs-feature"><h2>Continue listening</h2>${books.map(b=>`<article class="hs-library-row"><div><h3>${esc(b.title)}</h3><p class="hs-secondary">${Math.floor(b.position/60)} of ${Math.floor(b.duration/60)} minutes · saved for this listener</p></div>${musicButton("Continue","resume",b.id)}</article>`).join("")}</section>`:""}${delay ? `<section class="hs-feature"><h2>Listening scheduled</h2><p>${esc(delay.title)} · starts in ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}</p><div class="hs-control-actions">${musicButton("Cancel","cancel_delay")}${musicButton("Start now","start_now")}</div></section>`:""}${music.session ? `<section class="hs-feature"><h2>${focus.owner ? "Your session":"House session"}</h2><p class="hs-secondary">${esc(music.session.title)}</p><label>Sleep timer<select data-music="sleep"><option value="0">Off</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">1 hour</option></select></label>${music.sleep ? `<p class="hs-quiet">Timer set for this listening session.</p>`:""}</section>`:""}${music.favorites.length ? `<section class="hs-feature"><h2>${focus.owner ? "Mine":"House favourites"}</h2>${items(music.favorites)}</section>`:""}${focus.owner && music.shared?.length ? `<section class="hs-feature"><h2>House favourites</h2><p class="hs-quiet">Shared household choices · your listening progress stays separate.</p>${items(music.shared)}</section>`:""}${music.regional_radio ? `<section class="hs-feature"><h2>Local radio</h2><p class="hs-quiet">${esc(music.regional_radio.name)}</p>${music.regional_radio.issue ? `<p class="hs-secondary">${esc(music.regional_radio.issue)}</p>` : music.regional_radio.items.length ? items(music.regional_radio.items) : '<p class="hs-secondary">No stations matched your region. Search for a station below.</p>'}</section>`:""}${music.recent.length ? `<section class="hs-feature"><h2>Recently listened</h2>${items(music.recent)}</section>`:""}`;
};
const takeoverConfirmation=()=>musicState.view?.takeover?.confirmation;
const musicEvent = event => {
 const el=event.target.closest?.('[data-music]');if(!el)return false;
 event.stopPropagation();event.preventDefault();
 const action=el.dataset.music,item=el.dataset.item;
 if(["folder","root","refresh"].includes(action)) {musicState.editing=false;const continuation=action === "folder" && music?.library?.find(r=>r.id===item)?.continuation;if(action === "folder" && !continuation)musicState.back=[...(musicState.back || []),{folder:musicState.folder,query:musicState.query}];if(action === "root")musicState.back=[];musicState.folder=action === "folder" ? item:null;if(!continuation)musicState.query="";void musicRequest();}
 else if(action === "back") {if(state.pending)return;const previous=musicState.back?.pop();if(previous){musicState.folder=previous.folder;musicState.query=previous.query;musicState.editing=false;void musicRequest();}}
 else if(action === "clear-search") {if(state.pending)return;musicState.query="";musicState.folder=null;musicState.editing=false;void musicRequest();}
 else if(action === "delay-choice") {musicState.delay=+el.value;musicState.editing=false;this.requestUpdate();}
 else if(action === "discovery-choice") {musicState.discoveryChoice=el.value;this.requestUpdate();}
 else if(action === "surprise_me") void musicAction(action,{settings:musicState.discoveryOptions?.() || {mode:"anything"}});
 else if(action === "sleep") void musicAction("sleep",{value:+el.value});
 else if(action.startsWith("transfer_")) void musicAction(action,{player:music.transfer?.plan?.source_entity || music.transfer?.source_entity,...(action === "transfer_prepare" ? {target:item}:{}),...(action === "transfer_confirm" ? {confirmation:music.transfer?.plan?.confirmation}:{})});
 else if(action === "start") void musicAction(musicState.delay ? "delay":"play_item",{item,...(musicState.delay ? {value:musicState.delay}:{})});
 else void musicAction(action,{...(item ? {item}:{}),...(el.dataset.entry ? {entry:el.dataset.entry}:{}),...(action === "queue_move" ? {value:+el.dataset.shift}:{}),...(action === "queue_takeover" ? {confirmation:takeoverConfirmation()}:{} )});
 return true;
};
const musicSearch = event => {
 event.preventDefault();event.stopPropagation();
 if(state.pending)return;
 musicState.editing=false;musicState.draft=null;musicState.query=String(new FormData(event.target).get("query") || "").trim();musicState.folder=music?.collection?.root || null;void musicRequest();
};

const musicInput = event => {if(event.target.name === "query"){musicState.draft=event.target.value;musicState.editing=true;}};
