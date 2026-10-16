// Calls use the signed-in HA ingress identity; provider credentials never enter the page.
const musicBackend = typeof common.music_backend === "string" && /^[a-zA-Z0-9_]+$/.test(common.music_backend) ? common.music_backend : null;
const musicScope = focus.owner || null;
const musicState = state.music || (state.music={view:null,at:0,loading:false,folder:null,query:"",delay:0});
const music = musicState.view?.person_id === musicScope && musicState.view?.epoch === common.epoch ? musicState.view : null;
const musicURL = async () => {
 if(!this._hsMusicEntry) {
  const info=await hass.callWS({type:"supervisor/api",endpoint:"/addons/"+musicBackend+"/info",method:"get"});
  if(!/^\/api\/hassio_ingress\/[a-zA-Z0-9_-]+\/?$/.test(info.ingress_entry || "")) throw Error("invalid ingress");
  const session=await hass.callWS({type:"supervisor/api",endpoint:"/ingress/session",method:"post"});
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
 musicState.loading=true;
 try {
  let response=await fetch(await musicURL(),{method:body ? "POST":"GET",credentials:"same-origin",headers:body ? {"Content-Type":"application/json"}:{},...(body ? {body:JSON.stringify({...body,epoch:common.epoch})}:{}),signal:AbortSignal.timeout(45000)});
  if(response.status === 401){this._hsMusicEntry=null;throw Error("session expired");}
  const value=await response.json();
  if(!response.ok) {musicState.view=null;state.error=typeof value.error === "string" ? value.error : "Listening did not respond. Check Music Assistant and retry.";return;}
  if(value.person_id !== musicScope || value.epoch !== common.epoch) throw Error("scope changed");
  musicState.view=value;state.error="";
  if(!state.destination && value.default_destination) state.destination=value.default_destination;
 } catch {musicState.view=null;state.error="Listening could not be confirmed. Check Music Assistant and the speaker before retrying.";}
 finally {musicState.loading=false;musicState.at=Date.now();this.requestUpdate();}
};
if(musicBackend && ["media","person"].includes(focus.kind) && !musicState.loading && !musicState.editing && Date.now()-musicState.at>5000) void musicRequest();
const musicAction = async (action,extra={}) => {
 if(state.pending || musicState.loading) return;
 state.pending=true;state.error="";this.requestUpdate();
 try {await musicRequest({action,player:state.destination,...extra});} finally {state.pending=false;this.requestUpdate();}
};
const musicButton = (label,action,item,extra="") => `<button type="button" data-music="${action}"${item ? ` data-item="${esc(item)}"`:""}${extra}${state.pending || musicState.loading ? " disabled":""}>${esc(label)}</button>`;
const musicLibrary = () => {
 if(!music) return `<section class="hs-feature"><h2>Music Assistant</h2><p class="hs-secondary">${musicState.loading ? "Reading your listening choices…":"Listening is unavailable. Check Music Assistant and retry."}</p>${musicButton("Retry","refresh")}</section>`;
 const items = rows => `<div class="hs-library-list">${rows.map(r=>`<article class="hs-library-row"><div><h3>${esc(r.title)}</h3><p class="hs-quiet">${esc(({sound_effect:"Ambient sound",radio:"Radio",audiobook:"Audiobook",podcast_episode:"Episode",folder:"Collection"})[r.kind] || "Music")}</p></div><div class="hs-control-actions">${r.folder ? musicButton("Open","folder",r.id) : musicButton("Play","start",r.id)+musicButton(music.favorites.some(f=>f.id === r.id) ? "Saved":"Save",music.favorites.some(f=>f.id === r.id) ? "unfavorite":"favorite",r.id)}</div></article>`).join("")}</div>`;
 const books=music.books || [];
 const delay=music.delayed,seconds=delay ? Math.max(0,Math.ceil(delay.at-Date.now()/1000)) : 0;
 return `${books.length ? `<section class="hs-feature"><h2>Continue listening</h2>${books.map(b=>`<article class="hs-library-row"><div><h3>${esc(b.title)}</h3><p class="hs-secondary">${Math.floor(b.position/60)} of ${Math.floor(b.duration/60)} minutes · saved for this listener</p></div>${musicButton("Continue","resume",b.id)}</article>`).join("")}</section>`:""}${delay ? `<section class="hs-feature"><h2>Listening scheduled</h2><p>${esc(delay.title)} · starts in ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}</p><div class="hs-control-actions">${musicButton("Cancel","cancel_delay")}${musicButton("Start now","start_now")}</div></section>`:""}${music.session ? `<section class="hs-feature"><h2>${focus.owner ? "Your session":"House session"}</h2><p class="hs-secondary">${esc(music.session.title)}</p><label>Sleep timer<select data-music="sleep"><option value="0">Off</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">1 hour</option></select></label>${music.sleep ? `<p class="hs-quiet">Timer set for this listening session.</p>`:""}</section>`:""}${music.favorites.length ? `<section class="hs-feature"><h2>${focus.owner ? "Mine":"House favourites"}</h2>${items(music.favorites)}</section>`:""}${music.recent.length ? `<section class="hs-feature"><h2>Recently listened</h2>${items(music.recent)}</section>`:""}${music.browse ? `<section class="hs-feature"><h2>Music Assistant library</h2><form class="hs-control-actions" data-music-search><label>Find music, radio or books<input type="search" name="query" maxlength="100" value="${esc(musicState.draft ?? musicState.query)}"></label><button type="submit">Search</button></form><div class="hs-control-actions">${musicButton("All sources","root")}</div><label>Start playback<select data-music="delay-choice"><option value="0"${!musicState.delay ? " selected":""}>Now</option>${[300,600,900].map(v=>`<option value="${v}"${musicState.delay === v ? " selected":""}>${v/60} min</option>`).join("")}</select></label>${music.library.length ? items(music.library) : '<p class="hs-secondary">No items here. Choose another source or search.</p>'}</section>`:'<section class="hs-feature"><h2>Your listening</h2><p class="hs-secondary">Your saved choices and progress stay with your household view.</p></section>'}`;
};
const musicEvent = event => {
 const el=event.target.closest?.('[data-music]');if(!el)return false;
 event.stopPropagation();event.preventDefault();
 const action=el.dataset.music,item=el.dataset.item;
 if(["folder","root","refresh"].includes(action)) {musicState.folder=action === "folder" ? item:null;musicState.query="";void musicRequest();}
 else if(action === "delay-choice") {musicState.delay=+el.value;}
 else if(action === "sleep") void musicAction("sleep",{value:+el.value});
 else if(action === "start") void musicAction(musicState.delay ? "delay":"play_item",{item,...(musicState.delay ? {value:musicState.delay}:{})});
 else void musicAction(action,{...(item ? {item}:{})});
 return true;
};
const musicSearch = event => {
 event.preventDefault();event.stopPropagation();
 musicState.editing=false;musicState.draft=null;musicState.query=String(new FormData(event.target).get("query") || "").trim();musicState.folder=null;void musicRequest();
};

const musicInput = event => {if(event.target.name === "query"){musicState.draft=event.target.value;musicState.editing=true;}};
