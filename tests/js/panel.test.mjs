import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const render=new Function("hass","variables","html","window","helpers",readFileSync("home_starter/server/homestarter/static/decorative.js","utf8")+"\n"+readFileSync("home_starter/server/homestarter/static/panel-content.js","utf8"));
const html=(strings,...values)=>strings.map((s,i)=>s+(typeof values[i]==="string"?values[i]:"")).join("");
function scene(states={},changes={},user={},search="") {
  return render({states,user,config:{time_zone:"Australia/Sydney"},locale:{language:"en"}}, {panel:{title:"Example panel",base:"/example-panel",path:"/example-panel/home",targets:{climate:"/example-panel/climate"},people:[{name:"House",path:"/example-panel/home",icon:"mdi:home-outline"}],climate:"climate.example",zones:[],calendars:[],media:[],lights:[],alerts:[],bins:false,...changes}},html,{location:{search}});
}

test("kiosk fills its dedicated viewer and has a reversible settings escape",()=>{
  const config={kiosk_user_name:"Fixture panel"},user={name:"Fixture panel",is_admin:false};
  const kiosk=scene({},config,user);
  assert.match(kiosk,/--hs-chrome-height:0px/);assert.match(kiosk,/href="\/example-panel\/settings"/);assert.match(kiosk,/>Settings</);
  const escaped=scene({},config,user,"?disable_km");
  assert.match(escaped,/--hs-chrome-height:56px/);assert.match(escaped,/>Panel mode</);
  assert.match(scene({},config,{...user,is_admin:true}),/--hs-chrome-height:56px/);
  assert.match(scene({},config,{name:"Another viewer",is_admin:false}),/--hs-chrome-height:56px/);
});
test("panel taps use native HA navigation without loading a browser document",()=>{
  const actions=[];
  const template=render({states:{},config:{time_zone:"Australia/Sydney"}}, {panel:{base:"/example-panel",targets:{},people:[],zones:[],calendars:[],media:[],lights:[],alerts:[]}}, (strings,...values)=>values, {location:{search:""}}, {runAction:action=>actions.push(action)});
  const click=template.find(value=>typeof value==="function");
  for(const path of ["/example-panel/climate","/example-panel/person-fixture","/example-panel/home?disable_km","/example-panel/home"]) {
    let prevented=false,stopped=false;
    click({target:{closest:()=>({getAttribute:()=>path})},button:0,preventDefault(){prevented=true;},stopPropagation(){stopped=true;}});
    assert.equal(prevented,true);assert.equal(stopped,true);
    assert.deepEqual(actions.at(-1),{action:"navigate",navigation_path:path});
  }
  for(const path of ["https://example.invalid/","//example.invalid/","/example-panel-other/home"]) {
    click({target:{closest:()=>({getAttribute:()=>path})},button:0,preventDefault(){assert.fail("Unrelated link intercepted");},stopPropagation(){}});
  }
  assert.equal(actions.length,4);
});
test("panel renders reported climate, not example temperatures",()=>{
  const html=scene({"climate.example":{state:"cool",attributes:{temperature:23,current_temperature:21.5}}});
  assert.match(html,/>23°</);assert.match(html,/Currently 21.5°/);assert.match(html,/Cool mode/);
});

test("setup tiles open their own status pages without claiming working services",()=>{
  const output=scene({}, {targets:{call:"/example-panel/call",cameras:"/example-panel/cameras"}});
  assert.match(output,/href="\/example-panel\/call"/);
  assert.match(output,/href="\/example-panel\/cameras"/);
  assert.match(output,/Not commissioned/);
  assert.match(output,/Not selected/);
});

test("selected climate mode is distinct from reported activity",()=>{
  for (const state of ["cool","heat"]) {
    const output=scene({"climate.example":{state,attributes:{hvac_action:"idle"}}});
    assert.match(output,/>Idle</);assert.doesNotMatch(output,/>Cooling<|>Heating</);
  }
  assert.match(scene({"climate.example":{state:"cool",attributes:{hvac_action:"cooling"}}}),/>Cooling</);
});
test("enabled zones remain distinct from HVAC operation and inactive accent",()=>{
  const zones=Array.from({length:6},(_,i)=>`climate.zone_${i}`);
  const states=Object.fromEntries(zones.map(id=>[id,{state:"cool",attributes:{}}]));
  const off=scene({...states,"climate.example":{state:"off",attributes:{hvac_action:"cooling"}}},{zones});
  assert.match(off,/>Off</);assert.match(off,/6 of 6 zones enabled/);
  assert.doesNotMatch(off,/zones on|hs-operating/);
  const cooling=scene({...states,"climate.example":{state:"cool",attributes:{hvac_action:"cooling"}}},{zones});
  assert.match(cooling,/hs-climate hs-operating/);assert.match(cooling,/>Cooling</);
  assert.match(cooling,/zones enabled/);
  assert.doesNotMatch(scene({"climate.example":{state:"cool",attributes:{hvac_action:"idle"}}}),/hs-operating/);
  delete states[zones[0]];
  assert.match(scene(states,{zones}),/5 enabled.*5 of 6 zones reporting/);
});
test("household navigation uses saved people and separates display utilities",()=>{
  const output=scene({}, {kiosk_user_name:"Fixture panel",people:[
    {name:"House",path:"/example-panel/home",icon:"mdi:home-outline"},
    {name:"Saved person",path:"/example-panel/person-saved",icon:"mdi:account-circle-outline"}
  ]});
  const household=output.match(/<nav class="hs-household"[^>]*>(.*?)<\/nav>/s)[1];
  assert.match(household,/aria-current="page"/);assert.match(household,/Saved person/);
  assert.doesNotMatch(household,/Ambient|Settings|Grant|Renae|Liam|Mia|Noah/);
  assert.match(output,/<div class="hs-utilities" role="group" aria-label="Display">/);
  assert.match(output,/aria-label="Ambient"/);assert.match(output,/aria-label="Settings"/);
});
test("setup copy stays truthful and secondary without active card styling",()=>{
  const output=scene();
  for(const kind of ["today","call","cameras","media"]) assert.match(output,new RegExp(`hs-${kind} hs-setup`));
  for(const state of ["Not commissioned","Not selected","No speaker selected","No verified commitments to show"]) assert.ok(output.includes(state));
  assert.doesNotMatch(output,/hs-operating/);
  const css=readFileSync("home_starter/server/homestarter/static/panel-layout.css","utf8");
  assert.match(css,/--hs-edge: #41484e/);assert.match(css,/border: 1px solid var\(--hs-edge\)/);
  assert.match(css,/\.hs-nav a\[aria-current\] \{ background: #103e59; color: #70c7ff/);
});
test("offline climate stays honest and native control route remains",()=>{
  const html=scene({"climate.example":{state:"unavailable",attributes:{temperature:23}}});
  assert.match(html,/Connection unavailable/);assert.doesNotMatch(html,/>23°</);assert.match(html,/href="\/example-panel\/climate"/);
});
test("unselected household data never leaks through automatic discovery",()=>{
  const html=scene({"calendar.private":{state:"on",attributes:{message:"Private fixture commitment"}},"media_player.private":{state:"playing",attributes:{media_title:"Private fixture track"}}});
  assert.doesNotMatch(html,/Private fixture/);assert.match(html,/No speaker selected/);
});
test("HTML-valued entity labels and household names are escaped",()=>{
  const html=scene({"media_player.example":{state:"playing",attributes:{friendly_name:'<img src=x>',media_title:'<script>fixture</script>'}}},{media:["media_player.example"],people:[{name:'<img src=x>',path:"/example-panel/home",icon:"mdi:account-circle-outline"}]});
  assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;img/);
});
test("bin attention requires selected service and unexpired projection",()=>{
  const state={state:"current",attributes:{valid_until:new Date(Date.now()+60000).toISOString(),attention:"tonight",summary:"Bins tonight\n\nGreen · Recycling"}};
  assert.doesNotMatch(scene({"sensor.home_starter_bin_source":state}),/Green · Recycling/);
  assert.match(scene({"sensor.home_starter_bin_source":state},{bins:true}),/Green · Recycling/);
  state.attributes.valid_until="2000-01-01T00:00:00Z";
  const stale=scene({"sensor.home_starter_bin_source":state},{bins:true});
  assert.doesNotMatch(stale,/Green · Recycling/);assert.match(stale,/Bin schedule needs checking/);
});


test("unreported zones and lights never become fabricated off counts",()=>{
 const value=scene({}, {zones:['climate.zone_one','climate.zone_two'],lights:['light.one','light.two']});
 assert.match(value,/Zone status unavailable/);assert.doesNotMatch(value,/0 of 2 zones enabled/);
 assert.match(value,/Lighting status unavailable/);assert.doesNotMatch(value,/0 of 2 lights on/);
});

test("expired calendar entries and technical radio cues do not become glance content",()=>{
 const value=scene({'calendar.example':{state:'off',attributes:{message:'Expired fixture event',start_time:'2000-01-01T08:00:00Z',end_time:'2000-01-01T09:00:00Z'}},'media_player.example':{state:'playing',attributes:{friendly_name:'Example room',media_title:'Asset Stop 00:00 2026-10-19T05:20:00Z',media_channel:'Example Radio'}}},{calendars:['calendar.example'],media:['media_player.example']});
 assert.doesNotMatch(value,/Expired fixture|Asset Stop/);assert.match(value,/Example Radio/);assert.match(value,/No verified commitments/);
 const real=scene({'media_player.example':{state:'playing',attributes:{friendly_name:'Example room',media_title:"Don't Stop Me Now"}}},{media:['media_player.example']});
 assert.match(real,/Don&#39;t Stop Me Now/);
});

test("House glance summaries require the same fresh owned projections as their pages",()=>{
 const checked_at=new Date().toISOString(),valid_until=new Date(Date.now()+60000).toISOString();
 const meta={surface_id:'fixture',epoch:1,context_entity:'sensor.context',bindings:{camera:{entity_id:'sensor.camera',revision:'v1',cameras:[{entity_id:'camera.example'}]},call:{entity_id:'sensor.call',revision:'v1'}}};
 const states={'sensor.context':{state:'current',attributes:{checked_at,valid_until,home_starter_context:{surface:'fixture',epoch:1,person_id:null},briefing:[{title:'Example next commitment',when:'Starts 10:00'}]}},'sensor.camera':{state:'current',attributes:{checked_at,valid_until,home_starter_capability:{surface:'fixture',epoch:1,person_id:null,feature:'camera',revision:'v1'},value:{}}},'camera.example':{state:'idle',attributes:{}}};
 let value=scene(states,{summary_json:JSON.stringify(meta)});
 assert.match(value,/Example next commitment/);assert.match(value,/Starts 10:00/);assert.match(value,/1 camera selected/);assert.match(value,/1 reporting/);assert.match(value,/Calling unavailable/);assert.doesNotMatch(value,/<img|data-command=/);
 states['sensor.context'].attributes.home_starter_context.person_id='someone-else';
 states['sensor.camera'].attributes.valid_until='2000-01-01T00:00:00Z';
 value=scene(states,{summary_json:JSON.stringify(meta)});
 assert.doesNotMatch(value,/Example next commitment|1 camera selected/);assert.match(value,/Camera status unavailable/);
});


test("a damaged glance summary leaves the complete House navigation and climate visible",()=>{
 const value=scene({}, {summary_json:'not-json',targets:{climate:'/example-panel/climate',today:'/example-panel/today',rooms:'/example-panel/rooms',music:'/example-panel/music',cameras:'/example-panel/cameras',call:'/example-panel/call'}});
 for(const name of ['Climate','Today','Home','Media','Cameras','Call','House'])assert.ok(value.includes(name));
 assert.match(value,/Connection unavailable/);assert.match(value,/Not commissioned/);
 const dated=scene({'media_player.example':{state:'playing',attributes:{media_title:'2026-10-23 08:00 Morning News'}}},{media:['media_player.example']});
 assert.match(dated,/2026-10-23 08:00 Morning News/);
});

test('Today overview agrees with verified empty and unavailable context destinations',()=>{
 const context={state:'current',attributes:{home_starter_context:{surface:'example_panel',epoch:0},checked_at:new Date().toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),briefing:[]}};
 const config={summary_json:JSON.stringify({surface_id:'example_panel',epoch:0,context_entity:'sensor.example'})};
 assert.match(scene({'sensor.example':context},config),/Nothing upcoming in selected sources/);
 context.state='attention';
 assert.match(scene({'sensor.example':context},config),/Today sources need checking/);
});
