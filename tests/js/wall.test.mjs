import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const render=new Function("hass","variables","html","window",readFileSync(new URL("../../home_starter/server/homestarter/static/wall-content.js",import.meta.url),"utf8"));
function scene(model={},attrs={},extraStates={}) {
 const until=new Date(Date.now()+60000).toISOString();
 const config={title:"Example board",surface_id:"wall",epoch:2,context:"sensor.context"};
 const states={"sensor.context":{attributes:{home_starter_context:{surface:"wall",epoch:2},checked_at:new Date(Date.now()-1000).toISOString(),valid_until:until,wall:{version:1,valid_until:until,day_state:"quiet_daytime",day_summary:"Nothing urgent right now",primary:"quiet",today_items:[],future_attention:[],household_exception:[],active_context:[],issues:[],...model},...attrs}},...extraStates};
 return render({states,connected:true,config:{time_zone:"Australia/Sydney"},locale:{language:"en-AU"}},{wall_json:JSON.stringify(config)},(_,body)=>body,{innerHeight:1080,location:{search:"?kiosk"}});
}
test("quiet wall has no permanent child, camera, device or empty Today cards",()=>{
 const body=scene();assert.match(body,/Nothing urgent right now/);
 assert.doesNotMatch(body,/class="wall-today|class="wall-upcoming|class="wall-context|class="wall-session|href=|onclick=|<button|wall-child|Lights|Cameras/);
});
test("stale or foreign context hides plans and sessions instead of a white screen",()=>{
 for(const attrs of [{valid_until:new Date(0).toISOString()},{home_starter_context:{surface:"other",epoch:2}},{home_starter_context:{surface:"wall",epoch:1}}]){
  const body=scene({today_items:[{title:"Private plan",when:"Now"}],display_session:{title:"Private answer",kind:"answer"}},attrs);
  assert.doesNotMatch(body,/Private/);assert.match(body,/Household context unavailable/);
 }
});
test("interpreted priorities and names render as escaped data without guessing state",()=>{
 const body=scene({day_state:"active_movement",primary:"movement",next_movement:{label:"Leave soon",title:'<img src=x onerror="bad()">',people:["Example"],detail:"Leave by 08:30"}});
 assert.match(body,/data-state="active_movement"/);assert.match(body,/Leave by 08:30/);assert.match(body,/&lt;img/);assert.doesNotMatch(body,/<img/);
});
test("expired temporary sessions disappear; current sessions preserve the underlying board",()=>{
 const model={today_items:[{id:"one",title:"Underlying plan",when:"18:00"}],display_session:{kind:"answer",title:"Answer",body:"Text",expires_at:new Date(Date.now()+30000).toISOString()}};
 assert.match(scene(model),/Underlying plan/);assert.match(scene(model),/Temporary display session/);
 model.display_session.expires_at=new Date(0).toISOString();assert.doesNotMatch(scene(model),/Temporary display session/);
});
test("camera sessions accept only the named native proxy path",()=>{
 const model={display_session:{kind:"camera",title:"Door",camera:"camera.fixture",expires_at:new Date(Date.now()+30000).toISOString()}};
 assert.doesNotMatch(scene(model,{}, {"camera.fixture":{attributes:{entity_picture:"https://example.com/private.jpg"}}}),/<img/);
 assert.match(scene(model,{}, {"camera.fixture":{attributes:{entity_picture:"/api/camera_proxy/camera.fixture?token=example"}}}),/<img/);
});
