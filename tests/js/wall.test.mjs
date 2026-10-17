import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../home_starter/server/homestarter/static/wall-content.js", import.meta.url), "utf8");
const render = new Function("hass", "variables", "html", "window", source);
function scene(states={}, changes={}) {
  const cfg={title:"Example wall",surface_id:"wall",epoch:2,context:"sensor.context",children:[
    {id:"one",native_id:"native-one",name:"Example A"},{id:"two",native_id:"native-two",name:"Example B"},{id:"three",native_id:"native-three",name:"Example C"}
  ],climate:"climate.fixture",weather:"weather.fixture",lights:[],security:[],alerts:[],...changes};
  return render({states,config:{time_zone:"Australia/Sydney"},locale:{language:"en-AU"}},{wall_json:JSON.stringify(cfg)},(_,body)=>body,{location:{search:"?kiosk"}});
}
function context(rows, changes={}) {
  return {state:"ready",attributes:{home_starter_context:{surface:"wall",epoch:2},checked_at:new Date(Date.now()-1000).toISOString(),valid_until:new Date(Date.now()+60000).toISOString(),near:"Shared plans",briefing:rows,...changes}};
}

test("family wall has the morning reference composition without operating controls or invented facts",()=>{
  const body=scene();
  for(const label of ["wall-clock","wall-weather","wall-children","wall-today","wall-later","wall-footer"])assert.ok(body.includes(label));
  for(const name of ["Example A","Example B","Example C"])assert.ok(body.includes(name));
  assert.match(body,/Calendar connection pending/);
  assert.doesNotMatch(body,/href=|onclick=|<button|Year 8|PE UNIFORM|School drop-off|All good|Armed/);
  assert.match(body,/Camera views aren’t connected yet/);
});

test("wall uses only fresh owned household briefing and explicit person annotations",()=>{
  const row={title:"Bring sports kit",when:"This morning",detail:"",proximity:"now",people:["native-one"]};
  const body=scene({"sensor.context":context([row])});
  const child=name=>body.split(`aria-label="${name} plans"`)[1].split("</article>")[0];
  assert.match(child("Example A"),/Bring sports kit/);
  assert.doesNotMatch(child("Example B"),/Bring sports kit/);
  for(const attrs of [{valid_until:new Date(Date.now()-1).toISOString()},{home_starter_context:{surface:"other",epoch:2}},{home_starter_context:{surface:"wall",epoch:1}}]) {
    assert.doesNotMatch(scene({"sensor.context":context([row],attrs)}),/Bring sports kit/);
  }
  assert.doesNotMatch(scene({"calendar.unselected":{state:"on",attributes:{message:"Unselected private appointment"}}}),/Unselected private appointment/);
});

test("calendar titles, names and reminders remain escaped text on the shared wall",()=>{
  const row={title:'<img src=x onerror="alert(1)">',when:"Today",detail:"<script>bad</script>",proximity:"now",people:[]};
  const body=scene({"sensor.context":context([row])},{children:[{id:"one",name:"<b>Example</b>"}]});
  assert.match(body,/&lt;img/);assert.match(body,/&lt;b&gt;Example/);
  assert.doesNotMatch(body,/<img|<script>|<b>Example/);
});

test("critical alerts and actual climate readings survive the decorative composition",()=>{
  const body=scene({"binary_sensor.smoke":{state:"on"},"climate.fixture":{state:"off",attributes:{current_temperature:21.4}}},{alerts:[{entity:"binary_sensor.smoke",name:"Smoke alarm",alarm:false}]});
  assert.match(body,/role="alert"/);assert.match(body,/Smoke alarm needs attention/);assert.match(body,/21°/);assert.match(body,/>Off</);
});
