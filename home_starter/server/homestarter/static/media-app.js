import { apiUrl } from "./routes.js";

const state={surface:null,surfaces:[],person:null,view:null,player:null,folder:null,query:"",delay:0,busy:false,refreshing:false,refreshError:false,pendingText:"",mutating:false,generation:0,controller:null,error:"",remember:false,stationDraft:null,stationScope:"session"};
const $=id=>document.getElementById(id);
const add=(node,...children)=>node.append(...children.filter(child=>child!=null && child!==false));
function h(tag,attrs={},...children){
 const node=document.createElement(tag);
 for(const [key,value] of Object.entries(attrs)){
  if(value==null || value===false)continue;
  if(key.startsWith("on"))node.addEventListener(key.slice(2),value);
  else if(key==="class")node.className=value;
  else if(["value","checked","disabled","selected"].includes(key))node[key]=value;
  else node.setAttribute(key,String(value));
 }
 for(const child of children.flat(Infinity))if(child!=null && child!==false)node.append(child);
 return node;
}
const button=(label,fn,disabled=false)=>h("button",{type:"button",onclick:fn,disabled:disabled || state.busy},label);
const note=text=>h("p",{class:"muted"},text);
const panel=(title,...content)=>h("section",{class:"panel"},h("h2",{},title),...content);
const preferenceKey=()=>"homeStarter.media.profile:"+state.surface;
function rememberProfile(){
 try{if(state.remember)localStorage.setItem(preferenceKey(),state.person || "house");else localStorage.removeItem(preferenceKey());}catch{ /* Optional local preference; never credentials. */ }
}
function selectProfile(person){
 if(state.mutating)return;
 state.person=person;state.stationDraft=null;state.stationScope="session";state.player=null;state.folder=null;state.query="";state.view=null;rememberProfile();void load();
}
function listeningURL(){
 const url=new URL(apiUrl("api/listening/"+encodeURIComponent(state.surface),document.baseURI));
 if(state.person)url.searchParams.set("person",state.person);
 if(state.folder)url.searchParams.set("folder",state.folder);
 if(state.query)url.searchParams.set("query",state.query);
 return url;
}
function focusedControl(){
 const node=document.activeElement;
 if(!node?.matches("button,input,select,summary"))return null;
 const root=node.closest("#profile,#search,#playing,#rooms,#access,#library");
 if(!root)return null;
 const key=n=>[n.tagName,n.getAttribute("aria-label") || n.getAttribute("name") || n.textContent].join("|");
 const matches=[...root.querySelectorAll(node.tagName)].filter(n=>key(n)===key(node));
 return {root:root.id,key:key(node),tag:node.tagName,index:matches.indexOf(node)};
}
function restoreControl(saved){
 if(!saved)return;
 const matches=[...document.getElementById(saved.root)?.querySelectorAll(saved.tag) || []].filter(n=>[n.tagName,n.getAttribute("aria-label") || n.getAttribute("name") || n.textContent].join("|")===saved.key);
 const node=matches[saved.index];if(node && !node.disabled)node.focus({preventScroll:true});
}
async function load(body=null,{background=false}={}){
 if(!state.surface || state.mutating || body && state.busy)return;
 background=background && !!state.view;
 const focus=focusedControl();
 const generation=++state.generation;
 state.controller?.abort();const controller=new AbortController();state.controller=controller;
 let timedOut=false;const deadline=body ? null:setTimeout(()=>{timedOut=true;controller.abort();},12000);
 state.busy=!background;state.refreshing=background;state.mutating=!!body;state.pendingText=body ? ({play_item:"Starting your selection.",resume:"Resuming your audio.",queue_add:"Adding to the queue.",queue_next:"Adding your next choice.",destination:"Saving your speaker choice."}[body.action] || "Updating playback."):state.query ? "Searching your audio. Some sources may take a few seconds.":"Loading your listening choices.";if(!background){state.error="";state.refreshError=false;render();}
 try{
  const response=await fetch(listeningURL(),{method:body ? "POST":"GET",credentials:"same-origin",cache:"no-store",signal:controller.signal,...(body ? {headers:{"Content-Type":"application/json"},body:JSON.stringify({...body,epoch:state.view?.epoch})}:{})});
  const value=await response.json();
  if(generation!==state.generation)return;
  if(!response.ok){if(response.status===401 || response.status===403){state.view=null;state.stationDraft=null;state.surfaces=[];state.surface=null;state.person=null;$("access").replaceChildren();}throw Error(typeof value.error==="string" ? value.error:"Listening is temporarily unavailable.");}
  if(value.person_id!==state.person)throw Error("The listening profile changed. Select your profile again.");
  state.view=value;
  if(background && state.refreshError){state.error="";state.refreshError=false;}
  if(["transfer_confirm","transfer_recheck"].includes(body?.action) && !value.transfer?.pending && value.default_destination)state.player=value.default_destination;
  const allowed=value.players || [];
  if(!allowed.some(p=>p.entity_id===state.player))state.player=value.default_destination || null;
 }catch(error){if(generation===state.generation && (timedOut || error.name!=="AbortError")){
  state.error=timedOut ? "Refresh took too long. Showing the last confirmed state; retry when connected.":error.message || "Could not reach your listening choices. Retry when connected.";state.refreshError=background;
 }}
 finally{clearTimeout(deadline);if(generation===state.generation){state.busy=false;state.refreshing=false;state.mutating=false;
  // Background reads never lock controls or replace an input being edited.
  if(!background || !state.view || !["INPUT","SELECT","TEXTAREA","SUMMARY"].includes(document.activeElement?.tagName)){
   const currentFocus=background ? focusedControl():focus;render();restoreControl(currentFocus);
  }else renderStatus();
 }}
}
function act(action,extra={},player=state.player){return load({action,player,...extra});}
function openFolder(id){if(state.mutating)return;state.folder=id;state.query="";void load();}
function collection(rows){
 const selected=state.view?.players?.find(p=>p.entity_id===state.player);
 const target=state.view?.sessions?.find(s=>s.player_id===selected?.player_id);
 const occupied=!!target?.owner && !target.owned || ["playing","paused","buffering"].includes(selected?.state) && !target?.owned;
 const canPlay=!!selected?.available && !!selected.single && !selected.transfer_pending && !occupied;
 return h("div",{class:rows.length===1 ? "grid single":"grid"},rows.map(row=>{
  if(row.folder)return button(row.title,()=>openFolder(row.id));
  const saved=state.view.favorites.some(f=>f.id===row.id);
  return h("article",{class:"item"},h("h3",{},row.title),h("p",{},({podcast_episode:"Podcast episode",audiobook:"Audiobook",sound_effect:"Ambient sound",radio:"Radio",playlist:"Playlist",album:"Album",artist:"Artist"})[row.kind] || "Music"),h("div",{class:"actions"},button(state.delay ? "Start later":target?.owned ? "Replace my queue":"Play",()=>act(state.delay ? "delay":"play_item",{item:row.id,...(state.delay ? {value:state.delay}:{})}),!canPlay),target?.can_add && row.queueable && (!row.source_scoped || target.source_scoped) ? button("Add to queue",()=>act("queue_add",{item:row.id,session:target.revision})):null,target?.can_next && row.queueable && (!row.source_scoped || target.source_scoped) ? button("Play Next",()=>act("queue_next",{item:row.id,session:target.revision})):null,button(saved ? "Saved":"Save",()=>act(saved ? "unfavorite":"favorite",{item:row.id}))));
 }));
}
function shelf(title,rows){return rows?.length ? h("section",{class:"shelf"},h("h2",{},title),collection(rows)):null;}
function renderStatus(){
 $("notice").replaceChildren(...[state.error || (state.busy ? state.pendingText:""),state.error ? button("Retry",()=>state.surface ? load():bootstrap()):null].filter(child=>child!=null));
 const accessSelect=$("access").querySelector("select");if(accessSelect)accessSelect.disabled=state.mutating;
 document.querySelector(".workspace").setAttribute("aria-busy",String(state.busy));
 }
function render(){
 renderStatus();
 const view=state.view;
 $("profile").replaceChildren();$("search").replaceChildren();$("library").replaceChildren();$("playing").replaceChildren();$("rooms").replaceChildren();
 if(!view){$("library").append(note(state.surface ? "Your listening choices will appear after access is verified.":"Open Media through your signed-in Home Assistant account and configured household screen."));return;}
 const name=state.person ? view.profiles?.find(p=>p.id===state.person)?.name || "Your profile":"House";
 const profileButtons=[...(!view.bound_profile ? [{id:null,name:"House"}]:[]),...(view.profiles || [])].map(p=>{
  const node=h("button",{type:"button",onclick:()=>selectProfile(p.id),disabled:state.mutating},p.name);node.setAttribute("aria-pressed",String(p.id===state.person));return node;
 });
 add($("profile"),h("h1",{},name+"’s listening"),h("div",{class:"profile-list","aria-label":"Listening profile"},profileButtons),h("label",{class:"support"},h("input",{type:"checkbox",checked:state.remember,onchange:e=>{state.remember=e.target.checked;rememberProfile();}})," Remember this profile on this browser"));
 const library=$("library");
 if(view.browse){
  const search=h("input",{type:"search",name:"query",maxlength:100,value:state.query,placeholder:"Songs, radio, podcasts, books…","aria-label":"Search household audio"});
  add($("search"),h("form",{class:"search",onsubmit:e=>{e.preventDefault();if(state.mutating)return;state.query=search.value.trim();state.folder=view.collection?.root || null;void load();}},h("label",{},search),h("button",{type:"submit",disabled:state.busy},"Search")),button("All collections",()=>{state.folder=null;state.query="";void load();}));
 }
 if(view.discovery)add(library,h("section",{class:"shelf"},h("h2",{},"Find your next favourite"),note("Explore the catalogue, then keep the music going."),h("div",{class:"actions"},button("Surprise Me",()=>act("surprise_me",{settings:{mode:"anything"}}),!state.player),view.session && view.keep_it_going ? button("Keep It Going",()=>act("keep_it_going"),!state.player):null,view.session ? button("Something different",()=>act("something_different",{settings:{mode:"anything"}}),!state.player):null)));
 else if(view.discovery_issue)add(library,panel("Music",note(view.discovery_issue)));
 if(view.audiobooks){
  const bookPeople=view.audiobooks.state==="choose_listener" ? h("div",{class:"actions"},(view.profiles || []).map(p=>button(p.name+"’s books",()=>selectProfile(p.id)))):null;
  add(library,panel("Audiobooks",note(view.audiobooks.message),bookPeople));
 }
 if(view.books?.length)add(library,h("section",{class:"shelf"},h("h2",{},"Continue listening"),view.books.map(book=>h("article",{class:"item"},h("h3",{},book.title),note(Math.floor(book.position/60)+" minutes saved for this profile"),button("Continue",()=>act("resume",{item:book.id}),!state.player)))));
 add(library,shelf("Favourites",view.favorites),shelf("Household favourites",view.shared),shelf("Recently played",view.recent));
 for(const [kind,title] of [["radio","Radio"],["music","Music stations"],["ambient","Ambient"]])add(library,shelf(title,(view.channels || []).filter(row=>row.category===kind)));
 if(view.regional_radio)add(library,shelf("Local radio",view.regional_radio.items),view.regional_radio.issue ? note(view.regional_radio.issue):null);
 if(view.browse){
  const delay=h("select",{"aria-label":"Playback start",onchange:e=>{state.delay=+e.target.value;render();document.querySelector(".playback-options summary")?.focus();}},[[0,"Now"],[300,"In 5 minutes"],[600,"In 10 minutes"],[900,"In 15 minutes"]].map(([v,label])=>h("option",{value:v,selected:state.delay===v},label)));
  const catalogueSection=h("section",{class:"shelf"},h("h2",{},view.search ? "Search results":view.collection?.title || "Collections"),view.collection?.incomplete ? note("Some sources are unavailable; this collection may be incomplete."):null,h("details",{class:"playback-options",open:state.delay>0},h("summary",{},state.delay ? "Starts in "+Math.round(state.delay/60)+" minutes":"Start later"),h("label",{},"Start playback",delay)),view.search ? h("div",{},h("details",{class:"search-health"},h("summary",{},view.search.incomplete ? "Some matches may be missing":"Search availability"),note(view.search.coverage),view.search.issue ? note(view.search.issue):null,view.search.incomplete ? note("Some sources or further matches are unavailable. Refine the search for more."):null),[["track","Tracks"],["album","Albums"],["artist","Artists"],["playlist","Playlists"],["radio","Radio"],["podcast","Podcasts"],["podcast_episode","Episodes"],["audiobook","Audiobooks"]].map(([kind,label])=>shelf(label,view.library.filter(row=>row.kind===kind))),collection(view.library.filter(row=>row.continuation)),!view.library.length ? note("No matches found in your available audio."):null):view.library?.length ? collection(view.library):note("No items here. Choose another collection or search."));
  if(view.search)library.prepend(catalogueSection);else add(library,catalogueSection);
 }
 renderStations(view,library);renderPlaying(view);renderRooms(view);
}
function renderStations(view,library){
 const model=view.stations;if(!model)return;
 const box=panel("Household radio recipes",note(model.issue),note(model.coverage));
 if(model.notice)add(box,note(model.notice));
 if(view.browse)add(box,button("Create station recipe",()=>{state.stationDraft={name:"",seeds:[],genres:[],era:null,track_gap_days:1,artist_gap:3,discovery:50,exclude_explicit:false};render();}));
 if(view.browse && state.stationDraft){
  const spec=state.stationDraft || {name:"",seeds:[],genres:[],era:null,track_gap_days:1,artist_gap:3,discovery:50,exclude_explicit:false};
  const name=h("input",{name:"stationName",value:spec.name,maxlength:80,required:true,"aria-label":"Station name"});
  const seeds=h("input",{name:"stationSeeds",value:spec.seeds.join("; "),maxlength:640,"aria-label":"Station seeds",placeholder:"Artists, songs or text; separate with semicolons"});
  const genres=h("input",{name:"stationGenres",value:spec.genres.join(", "),maxlength:320,"aria-label":"Station genres"});
  const era=h("select",{"aria-label":"Station era"},h("option",{value:"",selected:spec.era==null},"Any era"),[1960,1970,1980,1990,2000,2010,2020].map(v=>h("option",{value:v,selected:spec.era===v},v+"s")));
  const gap=h("input",{type:"number",value:spec.track_gap_days,min:0,max:30,required:true,"aria-label":"Track repeat gap days"});
  const artist=h("input",{type:"number",value:spec.artist_gap,min:0,max:50,required:true,"aria-label":"Artist repeat gap tracks"});
  const discovery=h("input",{type:"number",value:spec.discovery,min:0,max:100,required:true,"aria-label":"Discovery percent"});
  const restricted=h("input",{type:"checkbox",checked:spec.exclude_explicit,"aria-label":"Exclude explicit or unknown content"});
  add(box,h("form",{onsubmit:async e=>{e.preventDefault();const draft={name:name.value,seeds:seeds.value.split(";").map(v=>v.trim()).filter(Boolean),genres:genres.value.split(",").map(v=>v.trim()).filter(Boolean),era:era.value==="" ? null:+era.value,track_gap_days:+gap.value,artist_gap:+artist.value,discovery:+discovery.value,exclude_explicit:restricted.checked};state.stationDraft={...draft,...(spec.id ? {id:spec.id}:{})};await act("station_save",{settings:draft,...(spec.id ? {station:spec.id}:{})});if(!state.error){state.stationDraft=null;render();}}},h("label",{},"Station name",name),h("label",{},"Seeds",seeds),h("label",{},"Genres (comma separated)",genres),h("label",{},"Era preference",era),h("div",{class:"grid"},h("label",{},"Track repeat gap (days)",gap),h("label",{},"Artist repeat gap (tracks)",artist),h("label",{},"Discovery (%)",discovery)),h("label",{class:"support"},restricted," Exclude explicit and unknown content"),h("div",{class:"actions"},h("button",{type:"submit",disabled:state.busy},spec.id ? "Save recipe changes":"Save station recipe"),button("Cancel editing",()=>{state.stationDraft=null;render();}))),note("Draft settings are editable defaults, not commissioned household preferences. Saving never starts playback."));
 }
 for(const saved of model.recipes || [])add(box,h("article",{class:"item"},h("h3",{},saved.name),note([...saved.seeds,...saved.genres].join(" / ")),h("div",{class:"actions"},view.browse ? button("Edit recipe",()=>{state.stationDraft=saved;render();}):null,view.browse ? button("Preview new session",()=>act("station_preview",{station:saved.id}),!model.can_preview):null)));
 if(!model.can_preview)add(box,note("Station previews are not available for your connected music yet."));
 const preview=model.preview;
 if(preview){
  const labels={ready:"Eligible proposal queue",partial:"Only some eligible tracks were returned; restrictions were kept.",exhausted:"No returned candidates meet these rules. Change the seeds or choose another source.",provider_unavailable:"The catalogue is temporarily unavailable. Your recipe and exclusions were kept."};
  add(box,h("h3",{},labels[preview.state] || "Station preview"),note(preview.coverage),preview.partial_sources ? note("Some catalogue queries were unavailable."):null);
  const scope=h("select",{"aria-label":"Station feedback scope",onchange:e=>{state.stationScope=e.target.value;}},[["session","This preview session"],["station","This station"],["profile","This profile's previews"]].map(([value,label])=>h("option",{value,selected:state.stationScope===value},label)));
  add(box,view.browse ? h("label",{},"Apply feedback to",scope):null,h("ol",{},preview.items.map(row=>h("li",{},h("span",{},row.title),view.browse ? h("div",{class:"actions"},[["More like this","more"],["Less like this","less"],["Never in previews","never"]].map(([label,value])=>button(label,()=>act("station_feedback",{preview:preview.id,entry:row.entry,value,settings:{scope:state.stationScope}})))):null))),view.browse ? button("Regenerate this preview",()=>act("station_refine",{station:preview.station,preview:preview.id}),!model.can_preview):null,view.browse ? button("Reset selected feedback scope",()=>act("station_reset",{station:preview.station,preview:preview.id,settings:{scope:state.stationScope}})):null);
 }
 add(library,box);
}
function transferPanel(view){
 const model=view.transfer;if(!model?.source_entity && !model?.notice)return null;
 const plan=model.plan;
 if(model.pending)return panel("Move playback",note(model.notice),button("Check move",()=>act("transfer_recheck",{},model.source_entity)));
 if(plan)return panel("Confirm playback move",note("Move your queue from "+(plan.source_name || "this speaker")+" to "+plan.target_name+"? The speaker is checked again before moving. Your timer deadline stays the same."),button("Confirm move",()=>act("transfer_confirm",{confirmation:plan.confirmation},plan.source_entity)),button("Cancel move",()=>act("transfer_cancel",{},plan.source_entity)));
 return panel("Move playback",model.notice ? note(model.notice):null,model.source_name ? note("From "+model.source_name):null,model.issue ? note(model.issue):note("Choose an empty speaker. This reviews the move before changing playback."),h("div",{class:"actions"},(model.targets || []).map(p=>button("Move to "+p.name,()=>act("transfer_prepare",{target:p.entity_id},model.source_entity)))));
}
function renderPlaying(view){
 const player=view.players.find(p=>p.entity_id===state.player);
 const owned=view.session && view.players.find(p=>p.player_id===view.session.player_id);
 const target=view.sessions?.find(s=>s.player_id===player?.player_id);
 const roomSelect=h("select",{"aria-label":"Choose a speaker",disabled:state.busy,onchange:e=>{if(state.mutating)return;state.player=e.target.value || null;if(state.player)void act("destination");else render();}},h("option",{value:""},"Choose a speaker"),view.players.map(p=>h("option",{value:p.entity_id,selected:p.entity_id===state.player,disabled:!p.available || !p.single},p.name+(!p.available ? " · unavailable":!p.single ? " · group not verified":""))));
 const controls=owned ? h("div",{class:"actions"},[ ["Play","play"],["Pause","pause"],["Stop","stop"],["Previous","previous"],["Next","next"] ].filter(([,action])=>action === "pause" ? owned.features?.includes("pause") : ["previous","next"].includes(action) ? owned.features?.includes("next_previous") : true).map(([label,action])=>button(label,()=>act(action,{},owned.entity_id),!owned.available || owned.transfer_pending))):null;
 const sleep=owned ? h("label",{},"Sleep timer",h("select",{"aria-label":"Sleep timer",disabled:state.busy || owned.transfer_pending,onchange:e=>void act("sleep",{value:+e.target.value},owned.entity_id)},[["","Choose timer"],[0,"Off"],[900,"15 minutes"],[1800,"30 minutes"],[3600,"1 hour"]].map(([value,label])=>h("option",{value,selected:value===""},label)))):null;
 const volume=owned?.features?.includes("volume_set") ? h("form",{class:"volume",onsubmit:e=>{e.preventDefault();const input=e.target.elements.volume;if(input.value!=="")void act("volume",{value:Number(input.value)},owned.entity_id);}},h("label",{},"Set speaker volume (%) ",h("input",{type:"number",name:"volume",min:0,max:100,required:true,"aria-label":"Speaker volume percent"})),h("button",{type:"submit",disabled:state.busy || owned.transfer_pending},"Apply"),note("Speaker’s own scale; household calibration is pending.")):null;
 const queueRows=target?.queue?.length ? h("ol",{"aria-label":"Selected speaker queue"},target.queue.map(row=>h("li",{},h("span",{},row.title+(row.current ? " (now playing)":"")),target.can_edit ? h("div",{class:"actions"},button("Up",()=>act("queue_move",{entry:row.entry,value:-1,session:target.revision}),!row.up),button("Down",()=>act("queue_move",{entry:row.entry,value:1,session:target.revision}),!row.down),button("Remove",()=>act("queue_remove",{entry:row.entry,session:target.revision}),!row.remove)):null))):null;
 const pending=view.takeover?.player_id===player?.player_id && view.takeover?.revision===target?.revision ? view.takeover:null;
 const confirmation=pending ? h("section",{class:"panel",role:"group","aria-labelledby":"takeover-title"},h("h2",{id:"takeover-title",tabindex:-1},"Confirm queue takeover"),h("p",{},"Take control of "+target.owner+"'s queue on "+player.name+"? Queue contents and playback state stay the same. Its existing sleep timer will be cleared; personal progress stays separate."),h("div",{class:"actions"},button("Confirm takeover",()=>act("queue_takeover",{session:target.revision,confirmation:pending.confirmation})),button("Cancel takeover",()=>act("queue_takeover_cancel")))):null;
 const participation=target?.owner ? panel("Selected session",h("p",{},target.owner+" owns this queue"),target.joined ? note("You joined listening. Playback controls and progress stay with the owner."):null,h("div",{class:"actions"},target.can_join ? button("Join listening",()=>act("queue_join",{session:target.revision})):null,target.joined ? button("Leave listening",()=>act("queue_leave")):null,target.can_takeover && !pending ? button("Review takeover",()=>act("queue_takeover_prepare",{session:target.revision})):null,!target.owned ? button("Choose another speaker",()=>roomSelect.focus()):null),queueRows,target.can_edit ? note("Play Next follows any audio the speaker has already loaded."):null,target.issue || target.edit_issue || target.takeover_issue ? note(target.issue || target.edit_issue || target.takeover_issue):null):target?.issue ? panel("Selected session",note(target.issue),button("Choose another speaker",()=>roomSelect.focus())):null;
 add($("playing"),transferPanel(view),confirmation,participation,panel("Now playing",owned ? h("span",{class:"badge"},owned.name):null,h("p",{class:"now-title"},view.session?.title || (player?.state==="playing" ? "Audio started elsewhere":"Ready when you are")),h("label",{},"Play to",roomSelect),controls,sleep,volume,view.sleep ? note("A sleep timer is active for this listening session."):null,view.delayed ? h("div",{},note("Scheduled listening: "+view.delayed.title),h("div",{class:"actions"},button("Start now",()=>act("start_now")),button("Cancel",()=>act("cancel_delay")))):null,!player?.available ? note("Choose an available speaker to start listening."):null));
}
function renderRooms(view){
 add($("rooms"),panel("Around the house",view.players.map(p=>h("div",{class:"room"},h("div",{},h("p",{class:p.entity_id===state.player ? "selected":""},p.name),h("small",{},!p.available ? "Unavailable":({playing:"Playing",paused:"Paused",idle:"Ready",off:"Off"})[p.state] || "Available")),button("Choose",()=>{state.player=p.entity_id;void act("destination");},!p.available || !p.single))),h("p",{class:"support"},"Selecting a speaker never starts playback. Existing sessions are protected by the household service.")));
}
async function bootstrap(){
 try{
  const response=await fetch(apiUrl("api/listening",document.baseURI),{credentials:"same-origin",cache:"no-store"});
  const value=await response.json();if(!response.ok)throw Error(value.error || "Sign in through Home Assistant to open your household.");
  state.surfaces=value.surfaces;
  if(!state.surfaces.length)throw Error("No permitted household media screen is connected to this account yet.");
  const requested=new URL(location.href).searchParams.get("surface");
  const initial=state.surfaces.find(s=>s.id===requested) || state.surfaces[0];state.surface=initial.id;state.person=initial.person_id;
  const select=h("select",{"aria-label":"Household screen",onchange:e=>{if(state.mutating)return;state.surface=e.target.value;state.stationDraft=null;state.stationScope="session";state.person=state.surfaces.find(s=>s.id===state.surface)?.person_id || null;state.view=null;state.player=null;state.folder=null;state.query="";void load();}},state.surfaces.map(s=>h("option",{value:s.id,selected:s.id===state.surface},s.name)));
  add($("access"),select);
  await load();
  try{const preferred=localStorage.getItem(preferenceKey());if(preferred && state.view && (preferred==="house" && !state.view.bound_profile || state.view.profiles?.some(p=>p.id===preferred))){state.remember=true;if(preferred!==(state.person || "house"))selectProfile(preferred==="house" ? null:preferred);else render();}}catch{ /* Optional local preference. */ }
 }catch(error){state.error=error.message;render();}
}
void bootstrap();
setInterval(()=>{if(state.surface && !state.busy && !state.refreshing && !document.hidden && !["INPUT","SELECT","TEXTAREA","SUMMARY"].includes(document.activeElement?.tagName))void load(null,{background:true});},7000);
