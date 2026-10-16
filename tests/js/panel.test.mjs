import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const render=new Function("hass","variables","html","window","helpers",readFileSync("home_starter/server/homestarter/static/panel-content.js","utf8"));
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
  assert.match(scene(states,{zones}),/5 of 6 zones enabled · some unavailable/);
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
