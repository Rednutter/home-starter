import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
const shell=readFileSync('home_starter/server/homestarter/static/panel-shell.js','utf8');
const content=readFileSync('home_starter/server/homestarter/static/panel-pages.js','utf8');
const render=new Function('hass','variables','html','window','helpers',shell+'\n'+readFileSync('home_starter/server/homestarter/static/panel-music.js','utf8')+'\n'+content);
const base='/example-panel';
const player={entity_id:'media_player.example',name:'Example room speaker',domain:'media_player',interaction:'both',attributes:{}};
function scene(kind='today',changes={},states={},host=null,services={},backend={}) {
 const calls=[],nav=[];
 host ||= {style:{setProperty(){}},requestUpdate(){}};
 const focus={kind,path:kind,title:'Example page',back:base+'/home',owner:null,controls:[],players:[],rooms:[],listener:{id:null,scope:'house'},bindings:{},context_entity:'sensor.example_context',...changes};
 const hass={states,services,user:{id:'fixture-user',name:'Fixture display',is_admin:false},config:{time_zone:'Australia/Sydney'},locale:{language:'en'},callService:async(...args)=>calls.push(args)};
 const common={base,surface_id:'example_panel',epoch:0,kiosk_user_name:'Fixture display',weather:null,people:[{name:'House',path:base+'/home',icon:'mdi:home-outline'}],...backend};
 const output=render.call(host,hass,{focus_json:JSON.stringify(focus),common_json:JSON.stringify(common)},(strings,...values)=>({markup:values.findLast(v=>typeof v==='string'),functions:values.filter(v=>typeof v==='function')}),{location:{search:''}},{runAction:a=>nav.push(a)});
 return {...output,calls,nav,host,hass,focus};
}
function event(dataset,value,tagName='BUTTON') {const el={dataset,value,tagName};return {target:{...el,closest:q=>q.includes('data-adapter') ? dataset.adapter ? el:null : q.includes('data-command') ? dataset.command ? el:null : null},stopPropagation(){},preventDefault(){}};}
function projection(feature,owner,value) {
 return {state:'current',attributes:{home_starter_capability:{surface:'example_panel',epoch:0,person_id:owner,feature,revision:'fixture-v1'},checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),value}};
}
function binding(feature,owner,actions={}) {return {entity_id:'sensor.example_'+feature,revision:'fixture-v1',actions};}
const livePlayer={state:'playing',attributes:{supported_features:16437,media_title:'Example track',media_artist:'Example artist',volume_level:.25}};

test('focused setup states stay truthful and belong to the shared shell',()=>{
 for(const [kind,text] of [['today','No verified briefing'],['call','Calling not set up'],['camera','No cameras commissioned'],['media','No speaker selected']]) assert.ok(scene(kind).markup.includes(text));
 assert.match(scene('call').markup,/hs-feature-art hs-call-art/);
 assert.doesNotMatch(scene('call').markup,/<button|dial pad|Kitchen|Front gate/);
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
 assert.match(output.markup,/Music Assistant library/);assert.match(output.markup,/10 of 60 minutes/);assert.match(output.markup,/Example radio/);
 assert.match(output.markup,/data-entity="media_player.offline"[^>]*disabled/);
 assert.doesNotMatch(output.markup,/data-command="group"/);
 view.person_id='other';host._hsPage.music.at=Date.now();
 assert.doesNotMatch(scene('media',{owner:'example'}, {},host,{}, {music_backend:'fixture_addon'}).markup,/Example book|Example radio/);
});
