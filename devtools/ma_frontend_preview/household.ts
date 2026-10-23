import { ref, computed, watch } from 'vue';
import { profile, releaseMode } from './context';

export const listening=ref<any>(null), surface=ref(''), player=ref<string|null>(null), speakers=ref<string[]>([]);
export const currentMedia=ref<any>(null), notice=ref(''), pending=ref(false), selecting=ref(false), drawer=ref(false), folder=ref<string|null>(null);
export const speakerSelectionDirty=ref(false);
let version=0, poll:ReturnType<typeof setInterval>|undefined;
const base=()=>new URL('.',document.baseURI);
const listeningURL=()=>{const u=new URL('../api/listening/'+encodeURIComponent(surface.value),base());if(profile.value!=='house')u.searchParams.set('person',profile.value);if(folder.value)u.searchParams.set('folder',folder.value);return u;};
export const selected= computed(()=>listening.value?.players?.find((p:any)=>p.entity_id===player.value));
export const session=computed(()=>listening.value?.sessions?.find((s:any)=>s.player_id===selected.value?.player_id));
export const transport=computed(()=>listening.value?.transport?.find((s:any)=>s.player_id===selected.value?.player_id));
export const canTransport=(name:string)=>!!transport.value?.actions?.includes(name);
export async function transportAction(name:string,extra:Record<string,any>={}){if(!canTransport(name)||!transport.value?.revision){notice.value=transport.value?.issue||'Refresh the current household session before controlling this speaker.';return;}await action(name,{...extra,session:transport.value.revision});}
export const occupied=computed(()=>!!session.value?.owner && !session.value?.owned || ['playing','paused','buffering'].includes(selected.value?.state) && !session.value?.owned);
export async function refresh(){
 if(!releaseMode || !surface.value || pending.value)return;
 const stamp=++version,person=profile.value;
 try{const response=await fetch(listeningURL(),{cache:'no-store',signal:AbortSignal.timeout(12000)});const data=await response.json();if(stamp!==version || person!==profile.value)return;if(!response.ok)throw Error(data.error||'Household playback is unavailable.');if(data.person_id!==(person==='house'?null:person))throw Error('Profile changed. Choose it again.');listening.value=data;if(!data.players.some((p:any)=>p.entity_id===player.value)){player.value=data.default_destination||null;speakerSelectionDirty.value=false;}if(!speakerSelectionDirty.value){const leader=data.players.find((p:any)=>p.entity_id===player.value);const group=data.grouping?.groups?.find((g:any)=>g.leader===leader?.player_id);speakers.value=group?data.players.filter((p:any)=>group.members.includes(p.player_id)).map((p:any)=>p.entity_id):player.value?[player.value]:[];}}
 catch(error){if(stamp===version)notice.value=error instanceof Error && error.name!=='TypeError'?error.message:'Household playback is unavailable. Retry the read; no command was sent.';}
}
export async function connectHousehold(id:string){surface.value=id;await refresh();if(!poll)poll=setInterval(()=>{if(!document.hidden)void refresh();},7000);}
watch(profile,()=>{version++;speakerSelectionDirty.value=false;listening.value=null;currentMedia.value=null;folder.value=null;notice.value='';void refresh();});
export async function action(name:string,extra:Record<string,any>={},target=player.value){
 if(pending.value || !releaseMode || !listening.value)return;
 if(speakers.value.length>1 && ['play_item','resume'].includes(name)){name='group_prepare';extra={...extra,settings:{members:[...speakers.value]}};drawer.value=true;}
 if(!target && !['favorite','unfavorite'].includes(name)){drawer.value=true;notice.value='Choose an available speaker.';return;}
 pending.value=true;version++;const person=profile.value;
 try{const response=await fetch(listeningURL(),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:name,epoch:listening.value.epoch,player:target,...extra}),signal:AbortSignal.timeout(30000)});const value=await response.json();if(!response.ok)throw Error(value.error||'That action could not be confirmed.');if(person===profile.value){if(['group_confirm','group_cancel','group_recheck'].includes(name))speakerSelectionDirty.value=false;listening.value=value;notice.value='';}}
 catch(error){notice.value=error instanceof Error && !['TimeoutError','TypeError','AbortError'].includes(error.name)?error.message:'The action has not been confirmed. Checking current playback; it will not be retried automatically.';}
 finally{pending.value=false;await refresh();}
}
export async function chooseMedia(item:any,mode='play_item'){
 if(pending.value || selecting.value || !releaseMode)return;
 selecting.value=true;const person=profile.value;
 try{const response=await fetch(new URL('select',base()),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile:person,selection:item.household_selection}),signal:AbortSignal.timeout(12000)});const record=await response.json();if(person!==profile.value)return;if(!response.ok)throw Error(record.error||'Choose this item again.');currentMedia.value={...item,household_id:record.id};if(mode==='select_only')return;if(record.folder){folder.value=record.id;location.hash='#/episodes';await refresh();return;}if(['queue_add','queue_next'].includes(mode) && (!record.queueable || record.source_scoped && !session.value?.source_scoped)){notice.value='This source cannot safely be added to the current queue. Choose a compatible source or another speaker.';return;}if(!player.value){drawer.value=true;notice.value='Choose a speaker, then press Play.';return;}await action(mode,{item:record.id,...(['queue_add','queue_next'].includes(mode)?{session:session.value?.revision}:{})});}
 catch(error){notice.value=error instanceof Error?error.message:'This item is unavailable.';}
 finally{selecting.value=false;}
}
