import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
const shell=readFileSync('home_starter/server/homestarter/static/panel-shell.js','utf8');
const content=readFileSync('home_starter/server/homestarter/static/decorative.js','utf8')+'\n'+readFileSync('home_starter/server/homestarter/static/panel-pages.js','utf8');
const render=new Function('hass','variables','html','window','helpers','fetch','AbortSignal','document','setTimeout','clearTimeout',shell+'\n'+readFileSync('home_starter/server/homestarter/static/panel-music.js','utf8')+'\n'+content);
const base='/example-panel';
const player={entity_id:'media_player.example',name:'Example room speaker',domain:'media_player',interaction:'both',attributes:{}};
function scene(kind='today',changes={},states={},host=null,services={},backend={},environment={}) {
 const calls=[],nav=[];
 host ||= {style:{setProperty(){}},requestUpdate(){}};
 const focus={kind,path:kind,title:'Example page',back:base+'/home',owner:null,controls:[],players:[],rooms:[],listener:{id:null,scope:'house'},bindings:{},context_entity:'sensor.example_context',...changes};
 const hass={states,services,user:{id:'fixture-user',name:'Fixture display',is_admin:false},config:{time_zone:'Australia/Sydney'},locale:{language:'en'},callService:async(...args)=>calls.push(args),...(environment.hass || {})};
 const common={base,surface_id:'example_panel',epoch:0,kiosk_user_name:'Fixture display',weather:null,people:[{name:'House',path:base+'/home',icon:'mdi:home-outline'}],...backend};
 const output=render.call(host,hass,{focus_json:JSON.stringify(focus),common_json:JSON.stringify(common)},(strings,...values)=>({strings,markup:values.findLast(v=>typeof v==='string'),functions:values.filter(v=>typeof v==='function'),listeners:values.filter(v=>typeof v?.handleEvent==='function')}),{location:{search:''}},{runAction:a=>nav.push(a)},environment.fetch || globalThis.fetch,environment.AbortSignal || globalThis.AbortSignal,environment.document || {},environment.setTimeout || globalThis.setTimeout,environment.clearTimeout || globalThis.clearTimeout);
 return {...output,calls,nav,host,hass,focus};
}
function event(dataset,value,tagName='BUTTON') {const el={dataset,value,tagName};return {target:{...el,closest:q=>q.includes('data-adapter') ? dataset.adapter ? el:null : q.includes('data-command') ? dataset.command ? el:null : null},stopPropagation(){},preventDefault(){}};}
function projection(feature,owner,value) {
 return {state:'current',attributes:{home_starter_capability:{surface:'example_panel',epoch:0,person_id:owner,feature,revision:'fixture-v1'},checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),value}};
}
function binding(feature,owner,actions={}) {return {entity_id:'sensor.example_'+feature,revision:'fixture-v1',actions};}
const livePlayer={state:'playing',attributes:{supported_features:16437,media_title:'Example track',media_artist:'Example artist',volume_level:.25}};

test('household media presents discovery and free ambient without provider IDs or stream URLs',()=>{
 const view={epoch:0,person_id:null,players:[{...player,available:true,single:true}],default_destination:player.entity_id,browse:true,library:[],favorites:[],recent:[],books:[],session:{title:'Example music'},keep_it_going:true,discovery:true,channels:[{id:'opaque-selection',title:'Rain',kind:'radio',category:'ambient'}]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const output=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Surprise Me/);assert.match(output.markup,/Keep It Going/);assert.match(output.markup,/Something different/);
 assert.match(output.markup,/>Ambient</);assert.match(output.markup,/Background audio without a music account/);assert.match(output.markup,/>Rain</);
 assert.doesNotMatch(output.markup,/Infinite Mix|scastream|provider_instance|refresh_token/);
 host._hsPage.music.discoveryChoice='era:1980';
 scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.deepEqual(host._hsPage.music.discoveryOptions(),{mode:'era',era:1980});
});

test('focused setup states stay truthful and belong to the shared shell',()=>{
 for(const [kind,text] of [['today','No verified briefing'],['call','Calling not set up'],['camera','No cameras commissioned'],['media','No speaker selected']]) assert.ok(scene(kind).markup.includes(text));
 assert.match(scene('call').markup,/hs-feature-art hs-call-art/);
 assert.doesNotMatch(scene('call').markup,/<button|dial pad|Kitchen|Front gate/);
});

test('Keep It Going is unavailable unless the service confirms pinned source capability',()=>{
 const view={epoch:0,person_id:null,players:[{...player,available:true,single:true}],default_destination:player.entity_id,browse:true,library:[],favorites:[],recent:[],books:[],session:{title:'Example music'},discovery:true,keep_it_going:false};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const output=scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/data-music="surprise_me"/);
 assert.doesNotMatch(output.markup,/data-music="keep_it_going"/);
});

test('unavailable discovery keeps browsing and free audio without offering blocked music actions',()=>{
 const view={epoch:0,person_id:null,players:[{...player,available:true,single:true}],default_destination:player.entity_id,browse:true,library:[{id:'folder',title:'Podcasts',kind:'folder',folder:true}],favorites:[],recent:[],books:[],session:{title:'Example music'},discovery:false,discovery_issue:'Music discovery is temporarily unavailable. <script>bad</script>',channels:[{id:'ambient',title:'Rain',kind:'sound_effect',category:'ambient'}]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const output=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Music discovery is temporarily unavailable/);
 assert.match(output.markup,/&lt;script&gt;bad&lt;\/script&gt;/);
 assert.doesNotMatch(output.markup,/data-music="surprise_me"|data-music="keep_it_going"|data-music="something_different"|<script>/);
 assert.match(output.markup,/>Rain</);assert.match(output.markup,/>Podcasts</);
});

test('House audiobook choices route to the chosen person without playing or exposing setup internals',()=>{
 const view={epoch:0,person_id:null,players:[{...player,available:true,single:true}],default_destination:player.entity_id,browse:true,library:[],favorites:[],recent:[],books:[],audiobooks:{state:'choose_listener',message:'Choose who is listening.'}};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const output=scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon',people:[{name:'House',path:base+'/home',icon:'mdi:home-outline'},{name:'Example <listener>',path:base+'/person-6f6e65',icon:'mdi:account'}]});
 assert.match(output.markup,/href="\/example-panel\/person-6f6e65-music"/);
 assert.match(output.markup,/Example &lt;listener&gt;’s books/);
 assert.doesNotMatch(output.markup,/home-music|provider_id|password|API key/);
 assert.equal(output.calls.length,0);
 view.audiobooks={state:'not_connected',message:'Your audiobook library is not connected yet.'};
 view.person_id='one';
 assert.match(scene('media',{owner:'one',players:[player]}, {},host,{}, {music_backend:'fixture_addon'}).markup,/Your audiobook library is not connected yet/);
});

test('Media participation keeps a foreign paused queue owned and exposes only supported additions',()=>{
 const view={epoch:0,person_id:null,players:[{...player,player_id:'fixture',state:'paused',available:true,single:true}],default_destination:player.entity_id,browse:true,library:[{id:'song',title:'Example local music',kind:'track',folder:false,queueable:true}],favorites:[],recent:[],books:[],sessions:[{player_id:'fixture',owner:'Example <script>owner</script>',owned:false,joined:false,can_join:true,can_add:false,revision:'opaque-revision'}]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 let markup=scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon'}).markup;
 assert.match(markup,/Example &lt;script&gt;owner&lt;\/script&gt; owns this queue/);
 assert.match(markup,/data-music="queue_join"/);
 assert.match(markup,/data-music="start" data-item="song" disabled/);
 assert.doesNotMatch(markup,/<script>|data-music="queue_add"/);
 Object.assign(view.sessions[0],{joined:true,can_join:false,can_add:true});
 markup=scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon'}).markup;
 assert.match(markup,/data-music="queue_leave"/);assert.match(markup,/data-music="queue_add"/);
 assert.match(markup,/Controls and progress stay with the owner/);
});

test('Media queue edits and takeover confirmation follow checked service capabilities',()=>{
 const target={player_id:'fixture',owner:'Other <script>profile</script>',owned:false,joined:true,can_join:false,can_add:true,can_next:true,can_edit:false,can_takeover:true,revision:'fixture-revision',queue:[{title:'Current song',current:true,entry:'opaque-current',remove:false,up:false,down:false},{title:'Upcoming song',current:false,entry:'opaque-upcoming',remove:true,up:false,down:false}]};
 const view={epoch:0,person_id:null,players:[{...player,player_id:'fixture',state:'paused',available:true,single:true}],default_destination:player.entity_id,browse:true,library:[{id:'song',title:'Local song',kind:'track',queueable:true}],favorites:[],recent:[],books:[],sessions:[target]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const show=()=>scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon'}).markup;
 let markup=show();
 assert.match(markup,/data-music="queue_next"/);assert.match(markup,/data-music="queue_takeover_prepare"/);
 assert.doesNotMatch(markup,/data-music="queue_takeover"|data-music="queue_remove"|<script>/);
 view.takeover={player_id:'fixture',revision:'fixture-revision',confirmation:'fixture-intent'};
 markup=show();
 assert.match(markup,/Confirm queue takeover/);assert.match(markup,/data-music="queue_takeover"/);
 assert.match(markup,/Other &lt;script&gt;profile&lt;\/script&gt;/);assert.doesNotMatch(markup,/fixture-intent/);
 view.takeover=null;Object.assign(target,{owned:true,can_edit:true,can_takeover:false});
 markup=show();
 assert.match(markup,/data-music="queue_remove" data-entry="opaque-current" disabled/);
 assert.match(markup,/data-music="queue_remove" data-entry="opaque-upcoming"/);
});
test('Today accepts only fresh owned context and renders a briefing, not a calendar grid',()=>{
 const state={state:'current',attributes:{home_starter_context:{surface:'example_panel',epoch:0},checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),briefing:[{when:'Leave 08:30',title:'Example school requirement',detail:'Example kit'},{when:'Tomorrow',title:'Example activity',detail:''}]}};
 const output=scene('today',{}, {'sensor.example_context':state}).markup;
 assert.match(output,/Example school requirement/);assert.match(output,/hs-important/);assert.match(output,/Tomorrow/);assert.doesNotMatch(output,/hui-calendar|month/);
 assert.doesNotMatch(scene('today',{owner:'example'},{'sensor.example_context':state}).markup,/Example school requirement/);
 state.attributes.valid_until='2000-01-01T00:00:00Z';assert.doesNotMatch(scene('today',{}, {'sensor.example_context':state}).markup,/Example school requirement/);
});
test('room controls are feature-specific and never expose gate or lock actions',async()=>{
 const controls=[{entity_id:'light.example',name:'Example lamp',domain:'light',interaction:'both'},{entity_id:'cover.example',name:'Example gate',domain:'cover',device_class:'gate'},{entity_id:'lock.example',name:'Example lock',domain:'lock'}];
 const states={'light.example':{state:'off',attributes:{supported_color_modes:['brightness']}},'cover.example':{state:'closed',attributes:{supported_features:15}},'lock.example':{state:'locked',attributes:{}}};
 const output=scene('room',{controls},states);
 assert.match(output.markup,/Brightness/);assert.match(output.markup,/Turn on/);assert.doesNotMatch(output.markup,/data-command="cover-open"|Unlock/);
 await output.functions[0](event({command:'toggle',entity:'light.example'}));
 assert.deepEqual(output.calls,[['light','turn_on',{entity_id:'light.example'}]]);
 await output.functions[0](event({command:'toggle',entity:'light.unselected'}));assert.equal(output.calls.length,1);
});
test('person listener and speaker destination remain separate; selecting another permitted speaker does not play',async()=>{
 const other={...player,entity_id:'media_player.other',name:'Example other speaker'};
 const first=scene('media',{owner:'example',listener:{id:'example',scope:'person'},controls:[player,other],players:[player,other],default_destination:player.entity_id},{[player.entity_id]:livePlayer,[other.entity_id]:livePlayer});
 assert.match(first.markup,/Your listening view/);assert.match(first.markup,/Example room speaker/);
 await first.functions[0](event({command:'destination',entity:other.entity_id}));assert.equal(first.calls.length,0);assert.equal(first.host._hsPage.destination,other.entity_id);
 const next=scene('media',{owner:'example',controls:[player,other],players:[player,other],default_destination:player.entity_id},{[player.entity_id]:livePlayer,[other.entity_id]:{...livePlayer,state:'paused'}},first.host);
 await next.functions[0](event({command:'play',entity:other.entity_id}));
 assert.deepEqual(next.calls,[['media_player','media_play',{entity_id:other.entity_id}]]);
});
test('independent audiobook positions follow listeners even on the same physical player',()=>{
 const changes=owner=>({owner,controls:[player],players:[player],default_destination:player.entity_id,bindings:{listening:binding('listening',owner)}});
 const states=owner=>({[player.entity_id]:livePlayer,'sensor.example_listening':projection('listening',owner,{listener_id:owner,audiobook:{id:'fixture-book',title:'Example book',position:owner==='example_a'?600:1200,duration:3600}})});
 assert.match(scene('media',changes('example_a'),states('example_a')).markup,/10 of 60 minutes/);
 assert.match(scene('media',changes('example_b'),states('example_b')).markup,/20 of 60 minutes/);
 assert.doesNotMatch(scene('media',changes('example_a'),states('example_b')).markup,/of 60 minutes/);
 const invalid=states('example_a');delete invalid['sensor.example_listening'].attributes.valid_until;
 assert.doesNotMatch(scene('media',changes('example_a'),invalid).markup,/of 60 minutes/);
});
test('delayed start delegates scheduling without starting or advancing playback',async()=>{
 const actions={delay:{domain:'music_assistant',service:'fixture_delay',value_parameter:'seconds',destination_parameter:'player'}};
 const output=scene('media',{owner:'example',controls:[player],players:[player],default_destination:player.entity_id,bindings:{listening:binding('listening','example',actions)}},{[player.entity_id]:livePlayer,'sensor.example_listening':projection('listening','example',{listener_id:'example',audiobook:{id:'fixture-book',title:'Example book',position:600,duration:3600}})},null,{music_assistant:{fixture_delay:{}}});
 await output.functions[1](event({adapter:'listening',providerAction:'delay'},'600','SELECT'));
 assert.deepEqual(output.calls,[['music_assistant','fixture_delay',{seconds:'600',player:player.entity_id}]]);
 assert.match(output.markup,/10 of 60 minutes/);assert.doesNotMatch(output.calls[0][1],/play|resume/);
});
test('incoming and active calls replace the destination grid and only show supported actions',()=>{
 const actions={answer:{domain:'voip',service:'fixture_answer'},reject:{domain:'voip',service:'fixture_reject'},end:{domain:'voip',service:'fixture_end'}};
 const changes={bindings:{call:binding('call',null,actions)}};
 const value={state:'incoming',id:'fixture-call',label:'Example door',destinations:[{id:'fixture-other',name:'Example other endpoint'}]};
 const incoming=scene('call',changes,{'sensor.example_call':projection('call',null,value)},null,{voip:{fixture_answer:{},fixture_reject:{}}}).markup;
 assert.match(incoming,/Answer/);assert.match(incoming,/Reject/);assert.doesNotMatch(incoming,/Example other endpoint/);
 const active=scene('call',changes,{'sensor.example_call':projection('call',null,{...value,state:'active',started_at:new Date().toISOString()})},null,{voip:{fixture_end:{}}}).markup;
 assert.match(active,/End call/);assert.doesNotMatch(active,/Answer|Example other endpoint/);
});
test('camera Open requires an explicit association and the real signed-in HA user',()=>{
 const camera={entity_id:'camera.example',name:'Example entry'};
 const bindings={camera:{...binding('camera',null,{open:{domain:'cover',service:'open_cover'}}),cameras:[camera],entry:[{id:'fixture-entry',camera_entity_id:camera.entity_id,action:'open',allowed_users:['fixture-user']}]}};
 const states={'camera.example':{state:'idle',attributes:{entity_picture:'/api/camera_proxy/camera.example?token=fixture'}},'sensor.example_camera':projection('camera',null,{event:{id:'fixture-event',camera_entity_id:camera.entity_id,label:'Example entry event'}})};
 const output=scene('camera',{bindings},states,null,{cover:{open_cover:{}}}).markup;
 assert.match(output,/hs-camera-image/);assert.match(output,/>Open</);assert.match(output,/Dismiss/);assert.doesNotMatch(output,/Talk/);
 bindings.camera.entry[0].allowed_users=['another-user'];assert.doesNotMatch(scene('camera',{bindings},states,null,{cover:{open_cover:{}}}).markup,/>Open</);
});
test('entity and person text cannot become HTML or executable button-card content',()=>{
 const output=scene('room',{controls:[{...player,name:'<img src=x onerror=bad>'}]},{[player.entity_id]:livePlayer}).markup;
 assert.doesNotMatch(output,/<img src=x/);assert.match(output,/&lt;img/);
});


test('service failures leave a retryable error and clear pending controls',async()=>{
 const controls=[{entity_id:'light.example',name:'Example lamp',domain:'light',interaction:'both'}];
 const output=scene('room',{controls},{'light.example':{state:'off',attributes:{}}});
 output.hass.callService=async()=>{throw Error('fixture failure');};
 await output.functions[0](event({command:'toggle',entity:'light.example'}));
 assert.equal(output.host._hsPage.pending,false);
 assert.match(output.host._hsPage.error,/did not respond/);
 const retried=scene('room',{controls},{'light.example':{state:'off',attributes:{}}},output.host);
 assert.match(retried.markup,/role="alert"/);
});

test('speaker grouping is explicit, feature-gated and limited to permitted players',async()=>{
 const other={...player,entity_id:'media_player.other'};
 const live={state:'playing',attributes:{supported_features:524288}};
 const output=scene('media',{controls:[player,other],players:[player,other],default_destination:player.entity_id},{[player.entity_id]:live,[other.entity_id]:live},null,{media_player:{join:{}}});
 await output.functions[0](event({command:'group',entity:player.entity_id,value:other.entity_id}));
 assert.deepEqual(output.calls,[['media_player','join',{entity_id:player.entity_id,group_members:[other.entity_id]}]]);
 await output.functions[0](event({command:'group',entity:player.entity_id,value:'media_player.unselected'}));
 assert.equal(output.calls.length,1);
});

test('Dark retains active safety alerts without identifying a person as authenticated',()=>{
 const header=new Function('hass','variables','html','window','helpers',shell+'\nreturn header();');
 const common={base,surface_id:'example_panel',epoch:0,people:[],alerts:[{entity_id:'binary_sensor.example_smoke',name:'Example smoke alarm',domain:'binary_sensor'}]};
 const output=header.call({style:{setProperty(){}}},{states:{'binary_sensor.example_smoke':{state:'on',attributes:{}}},user:{},config:{time_zone:'Australia/Sydney'}},{common_json:JSON.stringify(common),focus_json:JSON.stringify({kind:'dark',path:'dark',owner:null})},(strings,...values)=>values.find(v=>typeof v==='string'),{location:{search:''}},{});
 assert.match(output,/role="alert"/);assert.match(output,/Example smoke alarm/);
});


test('household footer stays available on every focused page including Dark',()=>{
 const footer=new Function('hass','variables','html','window','helpers',shell+'\nreturn footer();');
 const common={base,surface_id:'example_panel',epoch:0,people:[{name:'House',path:base+'/home',icon:'mdi:home-outline'},{name:'Example person',path:base+'/person-6578616d706c65',icon:'mdi:account-circle-outline'}]};
 for(const kind of ['person','today','media','room','rooms','context','climate','call','camera','settings','ambient','dark']){
  const output=footer.call({style:{setProperty(){}}},{states:{},user:{},config:{time_zone:'Australia/Sydney'}},{common_json:JSON.stringify(common),focus_json:JSON.stringify({kind,path:kind,owner:'example'})},(strings,...values)=>values.find(v=>typeof v==='string'),{location:{search:''}},{});
  assert.match(output,/aria-label="Household"/);assert.match(output,/>House</);assert.match(output,/>Example person</);assert.match(output,/aria-current="page"/);
 }
});


test('Music Assistant library uses listener-owned state and exact permitted speaker choices',()=>{
 const view={epoch:0,person_id:'example',players:[{...player,available:true,single:true},{...player,entity_id:'media_player.offline',name:'Offline speaker',available:false,single:true}],default_destination:player.entity_id,browse:true,library:[{id:'fixture-item',title:'Example radio',kind:'radio'}],favorites:[],recent:[],books:[{id:'fixture-book',title:'Example book',kind:'audiobook',position:600,duration:3600}],session:null,delayed:null,sleep:null};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const output=scene('media',{owner:'example',players:[player]}, {[player.entity_id]:livePlayer,'media_player.offline':livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Collections/);assert.match(output.markup,/10 of 60 minutes/);assert.match(output.markup,/Example radio/);
 assert.match(output.markup,/data-entity="media_player.offline"[^>]*disabled/);
 assert.doesNotMatch(output.markup,/data-command="group"/);
 host._hsPage.music.editing=true;host._hsPage.music.draft='Typing a new query';
 assert.equal(scene('media',{owner:'example',players:[player]}, {[player.entity_id]:livePlayer,'media_player.offline':livePlayer},host,{}, {music_backend:'fixture_addon'}).strings,output.strings,'button-card recompilation must retain Lit template identity');
 assert.equal(scene('media',{owner:'example',players:[player]}, {[player.entity_id]:livePlayer,'media_player.offline':livePlayer},host,{}, {music_backend:'fixture_addon'}).markup,output.markup,'typing must not replace the native search DOM on periodic updates');
 const personalHost={...host,_hsPage:{...host._hsPage,path:'person',music:{...host._hsPage.music,view:{...view,default_destination:player.entity_id}}}};
 const personal=scene('person',{owner:'example',destinations:{media:base+'/music',today:base+'/today',rooms:base+'/rooms',call:base+'/call'},supervision:[]}, {[player.entity_id]:livePlayer},personalHost,{}, {music_backend:'fixture_addon'});
 assert.match(personal.markup,/Example room speaker/);
 view.person_id='other';host._hsPage.music.at=Date.now();
 assert.doesNotMatch(scene('media',{owner:'example'}, {},host,{}, {music_backend:'fixture_addon'}).markup,/Example book|Example radio/);
});

test('combined collections show paging, honest partial state and no account plumbing',()=>{
 const view={epoch:0,person_id:null,players:[{...player,available:true,single:true}],default_destination:player.entity_id,browse:true,collection:{title:'Playlists',root:'bucket',total:85,incomplete:true},library:[{id:'one',title:'Same title',kind:'playlist',folder:false},{id:'page',title:'More playlists',kind:'folder',folder:true,continuation:true}],favorites:[],recent:[],books:[]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',music:{view,at:Date.now(),loading:false,query:'',delay:0}}};
 const output=scene('media',{players:[player]},{[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/<h2>Playlists<\/h2>/);assert.match(output.markup,/85 items across your connected sources/);
 assert.match(output.markup,/Some sources are temporarily unavailable/);assert.match(output.markup,/More playlists/);
 assert.doesNotMatch(output.markup,/spotify--|provider_filter|client_secret/);
});


test('stalled ingress setup times out only Media and clears loading without transport or retry',async()=>{
 const abort=new AbortController(),requests=[];
 const environment={AbortSignal:{timeout:milliseconds=>{assert.equal(milliseconds,12000);return abort.signal;}},hass:{callWS:()=>new Promise(()=>{})},fetch:async(...args)=>{requests.push(args);assert.fail('No listening transport before ingress');}};
 const output=scene('media',{}, {},null,{}, {music_backend:'fixture_addon'},environment);
 assert.match(output.markup,/Reading your listening choices/);
 assert.equal(output.host._hsPage.music.loading,true);
 abort.abort();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(output.host._hsPage.music.loading,false);
 assert.equal(output.host._hsPage.music.view,null);
 assert.equal(output.host._hsPage.pending,false);
 assert.equal(requests.length,0);
 const retry=scene('media',{}, {},output.host,{}, {music_backend:'fixture_addon'},environment);
 assert.match(retry.markup,/Listening is unavailable/);
 assert.match(retry.markup,/data-music="refresh">Retry/);
 const climate=scene('room',{controls:[{entity_id:'climate.fixture',name:'Example climate',domain:'climate'}]}, {'climate.fixture':{state:'off',attributes:{supported_features:1,temperature:22,hvac_modes:['off','cool']}}},output.host,{}, {music_backend:'fixture_addon'},environment);
 assert.match(climate.markup,/Increase target/);assert.doesNotMatch(climate.markup,/data-command="temperature-up"[^>]* disabled/);
 assert.equal(requests.length,0);
});

test('malformed or wrong-profile listening data becomes an isolated unavailable state',async()=>{
 for(const value of [{epoch:0,person_id:null,players:{}},{epoch:0,person_id:null,players:[null],library:[],favorites:[],recent:[],books:[]},{epoch:0,person_id:null,players:[],library:[],favorites:[],recent:[],books:[],sessions:{}},{epoch:0,person_id:'different',players:[],library:[],favorites:[],recent:[],books:[]}]){
  const host={style:{setProperty(){}},requestUpdate(){},_hsMusicEntry:'/api/hassio_ingress/fixture'};
  const environment={fetch:async()=>({ok:true,status:200,json:async()=>value})};
  scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(host._hsPage.music.view,null);assert.equal(host._hsPage.music.loading,false);
  assert.match(scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment).markup,/Listening is unavailable/);
 }
});

test('a slow camera expires locally, supports explicit retry and ignores stale image events',()=>{
 const timers=[],environment={setTimeout:(callback,delay)=>{timers.push({callback,delay});return {unref(){}};},clearTimeout(){}};
 const camera={entity_id:'camera.example',name:'Example camera'},bindings={camera:{...binding('camera',null),cameras:[camera]}};
 const states={'camera.example':{state:'idle',attributes:{entity_picture:'/api/camera_proxy/camera.example?token=fixture'}},'sensor.example_camera':projection('camera',null,{})};
 const output=scene('camera',{bindings},states,null,{}, {},environment);
 assert.match(output.markup,/Loading camera image/);assert.match(output.markup,/loading="lazy" decoding="async"/);
 assert.equal(output.host._hsPage.pending,false);assert.equal(timers[0].delay,8000);
 const old={...output.host._hsPage.cameraImage};
 timers[0].callback();assert.equal(output.host._hsPage.cameraImage.status,'failed');
 const failed=scene('camera',{bindings},states,output.host,{}, {},environment);
 assert.match(failed.markup,/Camera image unavailable/);assert.doesNotMatch(failed.markup,/<img/);
 const node={dataset:{cameraRetry:camera.entity_id}};
 failed.functions[0]({target:{closest:q=>q.includes('data-camera-retry') ? node:null}});
 const retried=scene('camera',{bindings},states,output.host,{}, {},environment);
 const current=output.host._hsPage.cameraImage;
 const imageEvent=revision=>({type:'load',target:{dataset:{cameraImage:camera.entity_id,cameraRevision:String(revision)},getAttribute:()=>current.url}});
 retried.listeners[0].handleEvent(imageEvent(old.revision));assert.equal(current.status,'loading');
 retried.listeners[0].handleEvent(imageEvent(current.revision));assert.equal(current.status,'ready');
 assert.equal(output.calls.length,0);
 // Navigating away is synchronous; the obsolete camera timer cannot change the new page.
 const call=scene('call',{},states,output.host,{}, {},environment);
 assert.match(call.markup,/Calling not set up/);assert.doesNotMatch(call.markup,/<button/);
 timers.at(-1).callback();assert.equal(output.host._hsPage.path,'call');
 const media=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},output.host,{}, {},environment);
 assert.match(media.markup,/Example room speaker/);assert.equal(output.calls.length,0);
});

test('lost camera projection clears pending image state rather than preserving a private stale image',()=>{
 const camera={entity_id:'camera.example',name:'Example camera'},bindings={camera:{...binding('camera',null),cameras:[camera]}};
 const states={'camera.example':{state:'idle',attributes:{entity_picture:'/api/camera_proxy/camera.example?token=fixture'}},'sensor.example_camera':projection('camera',null,{})};
 const output=scene('camera',{bindings},states);
 assert.equal(output.listeners[0].capture,true);
 const image=output.host._hsPage.cameraImage;
 output.listeners[0].handleEvent({type:'error',target:{dataset:{cameraImage:camera.entity_id,cameraRevision:String(image.revision)},getAttribute:()=>image.url}});
 assert.equal(image.status,'failed');assert.equal(output.host._hsPage.pending,false);
 delete states['sensor.example_camera'];
 const failed=scene('camera',{bindings},states,output.host);
 assert.match(failed.markup,/Camera connection unavailable/);assert.doesNotMatch(failed.markup,/<img/);assert.equal(output.host._hsPage.cameraImage,null);
});


test('an uncertain timed-out playback response is not automatically submitted again',async()=>{
 const controller=new AbortController(),requests=[];
 const view={epoch:0,person_id:null,players:[{...player,player_id:'fixture',available:true,single:true}],default_destination:player.entity_id,browse:true,library:[{id:'selection',title:'Example audio',kind:'track'}],favorites:[],recent:[],books:[]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsMusicEntry:'/api/hassio_ingress/fixture',_hsPage:{path:'media',destination:player.entity_id,pending:false,music:{view,at:Date.now(),loading:false}}};
 const environment={AbortSignal:{timeout:ms=>{assert.equal(ms,150000);return controller.signal;}},fetch:async(url,options)=>{requests.push(options);return {ok:true,status:200,json:()=>new Promise(()=>{})};}};
 const output=scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon'},environment);
 const node={dataset:{music:'start',item:'selection'},tagName:'BUTTON'};
 output.functions[0]({target:{...node,closest:q=>q.includes('data-music') ? node:null},stopPropagation(){},preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(requests.length,1);assert.equal(requests[0].method,'POST');
 controller.abort();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(host._hsPage.pending,false);assert.equal(host._hsPage.music.loading,false);assert.equal(host._hsPage.music.view,null);
 assert.match(host._hsPage.error,/speaker before retrying/);
 scene('media',{players:[player]}, {},host,{}, {music_backend:'fixture_addon'},environment);
 assert.equal(requests.length,1);
});


test('Media transfer offers review, confirmation and recheck without direct player commands',()=>{
 const view={epoch:0,person_id:null,players:[{...player,player_id:'fixture',available:true,single:true}],default_destination:player.entity_id,browse:true,library:[],favorites:[],recent:[],books:[],session:{player_id:'fixture',title:'Example queue'},transfer:{source_entity:player.entity_id,targets:[{entity_id:'media_player.other',name:'Example other room'}]}};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false}}};
 let output=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Move to Example other room/);assert.match(output.markup,/data-music="transfer_prepare"/);
 assert.doesNotMatch(output.markup,/Confirm move|data-command="transfer/);
 view.transfer.plan={source_entity:player.entity_id,target_name:'Example <room>',confirmation:'opaque-confirmation'};
 output=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Confirm playback move/);assert.match(output.markup,/Example &lt;room&gt;/);assert.match(output.markup,/data-music="transfer_confirm"/);
 view.transfer.pending=true;view.transfer.notice='Move needs checking';view.players[0].transfer_pending=true;
 output=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Check move/);assert.doesNotMatch(output.markup,/data-music="transfer_confirm"/);
 assert.match(output.markup,/data-command="pause"[^>]* disabled/);assert.equal(output.calls.length,0);
 view.transfer={source_entity:player.entity_id,issue:'Moving audio is not available yet.',targets:[]};
 output=scene('media',{players:[player]}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/not available yet/);assert.doesNotMatch(output.markup,/data-music="transfer_prepare"/);
});


test('owned AirTouch Media uses the same service title rather than a stale HA cue',()=>{
 const view={epoch:0,person_id:null,players:[{...player,player_id:'fixture',available:true,single:true}],default_destination:player.entity_id,browse:true,library:[],favorites:[],recent:[],books:[],session:{player_id:'fixture',title:'Example Radio'}};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false}}};
 const markup=scene('media',{players:[player]}, {[player.entity_id]:{state:'playing',attributes:{media_title:'Asset Stop 00:00 2026-10-19T05:20:00Z'}}},host,{}, {music_backend:'fixture_addon'}).markup;
 assert.match(markup,/Example Radio/);assert.doesNotMatch(markup,/Asset Stop/);
});


test('ordinary owned Stop uses the shared service once and never falls through to HA',async()=>{
 const requests=[];let finish;
 const view={epoch:0,person_id:null,players:[{...player,player_id:'fixture',available:true,single:true}],default_destination:player.entity_id,browse:true,library:[],favorites:[],recent:[],books:[],session:{player_id:'fixture',title:'Example audio'}};
 const host={style:{setProperty(){}},requestUpdate(){},_hsMusicEntry:'/api/hassio_ingress/fixture',_hsPage:{path:'media',destination:player.entity_id,music:{view,at:Date.now(),loading:false}}};
 const environment={fetch:async(url,options)=>{requests.push(JSON.parse(options.body));await new Promise(resolve=>{finish=resolve});return {ok:true,status:200,json:async()=>view};}};
 const output=scene('media',{}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'},environment);
 assert.match(output.markup,/data-command="stop"/);
 await Promise.resolve();
 const first=output.functions[0](event({command:'stop',entity:player.entity_id}));
 output.functions[0](event({command:'stop',entity:player.entity_id}));
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(requests.length,1);assert.equal(requests[0].action,'stop');assert.equal(output.calls.length,0);
 finish();await first;await new Promise(resolve=>setImmediate(resolve));
 assert.equal(host._hsPage.pending,false);
 view.session=null;
 assert.doesNotMatch(scene('media',{}, {[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'},environment).markup,/data-command="stop"/);
});

test('late older media reads and responses after page close cannot replace current choices',async()=>{
 const releases=[];
 const view={epoch:0,person_id:null,players:[],browse:true,library:[],favorites:[],recent:[],books:[]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsMusicEntry:'/api/hassio_ingress/fixture'};
 const environment={fetch:async()=>({ok:true,status:200,json:()=>new Promise(resolve=>releases.push(resolve))})};
 const first=scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
 await new Promise(resolve=>setImmediate(resolve));
 host._hsPage.music.loading=false;host._hsPage.music.at=0;
 scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
 await new Promise(resolve=>setImmediate(resolve));
 releases[1]({...view,library:[{id:'new',title:'New result',kind:'track'}]});
 await new Promise(resolve=>setImmediate(resolve));
 releases[0]({...view,library:[{id:'old',title:'Old result',kind:'track'}]});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(host._hsPage.music.view.library[0].id,'new');
 host._hsPage.music.at=0;scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
 await new Promise(resolve=>setImmediate(resolve));
 scene('call',{}, {},host);
 releases[2](view);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(host._hsPage.path,'call');assert.equal(first.calls.length,0);
});


test('browse Back and empty/unavailable search remain metadata-only and precede shelves',async()=>{
 const requests=[];
 const view={epoch:0,person_id:null,players:[],browse:true,library:[{id:'folder',title:'Example playlists',kind:'folder',folder:true}],favorites:[],recent:[],books:[],channels:[{id:'rain',title:'Rain',kind:'sound_effect',category:'ambient'}],discovery:false,discovery_issue:'Music discovery is temporarily unavailable.'};
 const host={style:{setProperty(){}},requestUpdate(){},_hsMusicEntry:'/api/hassio_ingress/fixture',_hsPage:{path:'media',music:{view,at:Date.now(),loading:false,folder:null,query:'',delay:0}}};
 const environment={fetch:async(url,options)=>{assert.equal(options.method,'GET');requests.push(url);return {ok:true,status:200,json:async()=>({...view,library:[]})};}};
 const tap=(output,action,item)=>output.functions[0]({target:{tagName:'BUTTON',closest:q=>q.includes('data-music') ? {dataset:{music:action,item}}:null},stopPropagation(){},preventDefault(){}});
 let output=scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
 assert.ok(output.markup.indexOf('data-music-search')<output.markup.indexOf('>Ambient<'));
 tap(output,'folder','folder');await new Promise(resolve=>setImmediate(resolve));
 assert.match(requests[0],/folder=folder/);
 output=scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
 assert.match(output.markup,/Back to choices/);assert.match(output.markup,/No matches here/);
 tap(output,'back');await new Promise(resolve=>setImmediate(resolve));
 assert.doesNotMatch(requests.at(-1),/folder=/);assert.equal(host._hsPage.music.back.length,0);
 host._hsPage.music.query='missing';host._hsPage.music.view.search={coverage:'Connected audio only',issue:'One source is unavailable',incomplete:true};
 output=scene('media',{}, {},host,{}, {music_backend:'fixture_addon'},environment);
 assert.match(output.markup,/Search results|Clear search/);assert.match(output.markup,/One source is unavailable/);assert.match(output.markup,/>Rain</);
 tap(output,'clear-search');await new Promise(resolve=>setImmediate(resolve));
 assert.equal(host._hsPage.music.query,'');assert.equal(output.calls.length,0);
});

test('Today separates verified empty sources from failed sources without inventing events',()=>{
 const context={state:'current',attributes:{home_starter_context:{surface:'example_panel',epoch:0},checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),briefing:[]}};
 assert.match(scene('today',{}, {'sensor.example_context':context}).markup,/Nothing upcoming/);
 assert.doesNotMatch(scene('today',{}, {'sensor.example_context':context}).markup,/Choose and verify/);
 context.state='attention';
 assert.match(scene('today',{}, {'sensor.example_context':context}).markup,/Today sources need checking/);
 context.attributes.valid_until='2000-01-01T00:00:00Z';
 assert.doesNotMatch(scene('today',{}, {'sensor.example_context':context}).markup,/Nothing upcoming/);
});

test('unknown room readings do not become zero sliders or current climate temperatures',()=>{
 const controls=[{entity_id:'light.fixture',domain:'light',name:'Light'},{entity_id:'fan.fixture',domain:'fan',name:'Fan'},{entity_id:'climate.fixture',domain:'climate',name:'Climate'}];
 const states={'light.fixture':{state:'on',attributes:{supported_color_modes:['brightness']}},'fan.fixture':{state:'on',attributes:{supported_features:1}},'climate.fixture':{state:'unavailable',attributes:{current_temperature:29,temperature:22,supported_features:1}}};
 const output=scene('room',{controls},states);
 assert.match(output.markup,/Brightness unavailable/);assert.match(output.markup,/Fan speed unavailable/);
 assert.doesNotMatch(output.markup,/type="range"|Currently 29|22°/);
 states['light.fixture'].attributes.brightness=128;states['fan.fixture'].attributes.percentage=0;
 const known=scene('room',{controls},states).markup;
 assert.match(known,/value="50"/);assert.match(known,/value="0"/);
});

test('malformed calling destinations stay unavailable and cannot invoke a service',async()=>{
 const output=scene('call',{bindings:{call:binding('call',null,{start:{domain:'fixture',service:'call'}})}},{sensor:{},sensor_example:{} ,'sensor.example_call':projection('call',null,{state:'idle',destinations:'invalid'})},null,{fixture:{call:{}}});
 assert.match(output.markup,/No callable destinations/);
 await output.functions[0](event({adapter:'call',providerAction:'start',value:'invalid'}));
 assert.equal(output.calls.length,0);
});

test('person summary uses shared-service availability instead of a stale playing HA entity',()=>{
 const view={epoch:0,person_id:'one',players:[{...player,available:false,state:'playing'}],default_destination:player.entity_id,library:[],favorites:[],recent:[],books:[]};
 const host={style:{setProperty(){}},requestUpdate(){},_hsPage:{path:'person',music:{view,at:Date.now(),loading:false}}};
 const output=scene('person',{owner:'one',destinations:{media:base+'/music',today:base+'/today',rooms:base+'/rooms',call:base+'/call'}},{[player.entity_id]:livePlayer},host,{}, {music_backend:'fixture_addon'});
 assert.match(output.markup,/Speaker unavailable/);assert.doesNotMatch(output.markup,/>Playing</);
});

test('unavailable camera talk and concurrent provider taps issue no duplicate action',async()=>{
 const actions={talk:{domain:'fixture',service:'talk'}};
 const focus={bindings:{camera:{...binding('camera',null,actions),cameras:[{entity_id:'camera.fixture',name:'Example camera'}]}}};
 const states={'sensor.example_camera':projection('camera',null,{}),'camera.fixture':{state:'unavailable',attributes:{}}};
 let output=scene('camera',focus,states,null,{fixture:{talk:{}}});
 assert.doesNotMatch(output.markup,/data-provider-action="talk"/);
 await output.functions[0](event({adapter:'camera',providerAction:'talk',value:'camera.fixture'}));
 assert.equal(output.calls.length,0);
 states['camera.fixture'].state='idle';
 let release,count=0;
 output=scene('camera',focus,states,null,{fixture:{talk:{}}},{},{hass:{callService:()=>{count++;return new Promise(resolve=>release=resolve);}}});
 const first=output.functions[0](event({adapter:'camera',providerAction:'talk',value:'camera.fixture'}));
 await output.functions[0](event({adapter:'camera',providerAction:'talk',value:'camera.fixture'}));
 assert.equal(count,1);release();await first;
 assert.equal(output.host._hsPage.pending,false);
});

test('partial Today keeps verified items visible with a source-health notice',()=>{
 const context={state:'attention',attributes:{home_starter_context:{surface:'example_panel',epoch:0},checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),briefing:[{when:'Tomorrow',title:'Example verified event'}]}};
 const output=scene('today',{}, {'sensor.example_context':context});
 assert.match(output.markup,/Example verified event/);assert.match(output.markup,/Some Today sources need checking/);
});

test('a stale slider event cannot set a missing room reading',async()=>{
 const controls=[{entity_id:'fan.fixture',domain:'fan',name:'Fan'},{entity_id:'light.fixture',domain:'light',name:'Light'}];
 const states={'fan.fixture':{state:'on',attributes:{supported_features:1}},'light.fixture':{state:'on',attributes:{supported_color_modes:['brightness']}}};
 const output=scene('room',{controls},states);
 await output.functions[1](event({command:'fan-speed',entity:'fan.fixture'},50,'INPUT'));
 await output.functions[1](event({command:'brightness',entity:'light.fixture'},50,'INPUT'));
 assert.equal(output.calls.length,0);
});
