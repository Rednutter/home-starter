import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const render=new Function("hass","variables","html","window",readFileSync(new URL("../../home_starter/server/homestarter/static/wall-content.js",import.meta.url),"utf8"));
function scene(model={},attrs={},extraStates={}) {
 const until=new Date(Date.now()+60000).toISOString();
 const config={title:"Example board",surface_id:"wall",epoch:2,context:"sensor.context"};
 const states={"sensor.context":{attributes:{home_starter_context:{surface:"wall",epoch:2},checked_at:new Date(Date.now()-1000).toISOString(),valid_until:until,wall:{version:1,valid_until:until,day_state:"quiet_daytime",today_summary:"Quiet Sunday",cards:[],timeline:{label:"Today",items:[]},secondary:{label:"Upcoming",items:[]},household_exception:[],active_context:[],issues:[],...model},...attrs}},...extraStates};
 return render({states,connected:true,config:{time_zone:"Australia/Sydney"},locale:{language:"en-AU"}},{wall_json:JSON.stringify(config)},(_,body)=>body,{innerHeight:1080,location:{search:"?kiosk"}});
}
const event={id:"one",title:"School",time:"8:50",people:["Casey"],leave_at:new Date(Date.now()+3600000).toISOString()};
test("weekday and evening keep stable anchors while omitting empty islands",()=>{
 for(const model of [{cards:[{kind:"person",title:"Casey",items:[event]}],timeline:{label:"Today",items:[event]}},{focus:{preview:true,mode:"tomorrow_preview"},cards:[{kind:"context",title:"Today",summary:"Quiet Sunday",items:[]},{kind:"person",title:"Casey",items:[event]}],timeline:{label:"Tomorrow",items:[event]}}]) {
  const body=scene(model);
  for(const region of ["wall-header","wall-weather","wall-family","wall-agenda","wall-timeline","wall-household","wall-bottom"])assert.match(body,new RegExp(region));
  assert.doesNotMatch(body,/wall-secondary|wall-camera-status|Quiet Sunday/);
  assert.doesNotMatch(body,/Next movement|Nothing urgent right now|wall-movement|data-layout=/);
 }
});
test("person cards group real preparation and departures without a generic movement card",()=>{
 const body=scene({next_movement:event,cards:[{kind:"person",title:"Casey",items:[{title:"Sports kit + hat",when:"This morning"},event]}]});
 assert.match(body,/Sports kit \+ hat/);assert.match(body,/Leave /);assert.match(body,/School/);assert.doesNotMatch(body,/<time>This morning/);
});
test("forecast values are real optional data, never an inferred high",()=>{
 const current=scene({weather:{temperature:14,condition:"sunny"}});
 assert.match(current,/14°/);assert.match(current,/Forecast high unavailable/);assert.doesNotMatch(current,/→/);
 const forecast=scene({weather:{temperature:14,high:20,condition:"sunny"}});
 assert.match(forecast,/→ 20°/);
});
test("missing status is honest and unselected categories leave no empty containers",()=>{
 const body=scene();assert.match(body,/Home/);assert.doesNotMatch(body,/Climate|Security|Lights|Cameras|wall-family-card/);
 assert.match(body,/Status unavailable/);assert.doesNotMatch(body,/All good|All off|Armed/);
});

test("Monday preview weather uses tomorrow's range and keeps current weather secondary",()=>{
 const body=scene({focus:{preview:true,mode:"tomorrow_preview"},weather:{preview:true,focus_date:"2026-10-19",temperature:14,low:10,high:20,condition:"rainy",forecast_condition:"sunny"}});
 assert.match(body,/MON/);assert.match(body,/10°/);assert.match(body,/→ 20°/);assert.match(body,/Tomorrow · Sunny/);assert.match(body,/Now 14°/);
});
test("expired calendar rows disappear independently",()=>{
 const body=scene({cards:[{kind:"person",title:"Casey",items:[{...event,title:"Finished",ends_at:new Date(0).toISOString()}]}],timeline:{label:"Today",items:[{...event,title:"Finished",ends_at:new Date(0).toISOString()}]}});
 assert.doesNotMatch(body,/Finished/);
});
test("stale and foreign context hides private plans, snapshots, answers and status",()=>{
 for(const attrs of [{valid_until:new Date(0).toISOString()},{home_starter_context:{surface:"other",epoch:2}},{home_starter_context:{surface:"wall",epoch:1}}]){
  const body=scene({cards:[{kind:"person",title:"Private",items:[event]}],display_session:{title:"Private answer",kind:"answer"},household_status:{home:"Private state"}},attrs);
  assert.doesNotMatch(body,/Private|Casey|School/);assert.match(body,/Household context unavailable/);
 }
});
test("people, event names, notes and status remain escaped data",()=>{
 const unsafe='<img src=x onerror="bad()">';
 const body=scene({cards:[{kind:"person",title:unsafe,items:[{title:unsafe,when:"Now"}]}],household_status:{home:unsafe}});
 assert.match(body,/&lt;img/);assert.doesNotMatch(body,/<img/);
});
test("expired temporary sessions disappear without replacing the canonical board",()=>{
 const model={cards:[{kind:"person",title:"Casey",items:[event]}],display_session:{kind:"answer",title:"Answer",body:"Text",expires_at:new Date(Date.now()+30000).toISOString()}};
 assert.match(scene(model),/Temporary display session/);assert.match(scene(model),/wall-family/);
 model.display_session.expires_at=new Date(0).toISOString();assert.doesNotMatch(scene(model),/Temporary display session/);
});
test("camera sessions and bottom snapshots accept only their named native proxy",()=>{
 const camera={entity:"camera.fixture",name:"Door",available:true};
 const model={household_status:{cameras:[camera]},display_session:{kind:"camera",title:"Door",camera:camera.entity,expires_at:new Date(Date.now()+30000).toISOString()}};
 for(const path of ["https://example.com/private.jpg","/api/camera_proxy/camera.other"])assert.doesNotMatch(scene(model,{}, {[camera.entity]:{state:"idle",attributes:{entity_picture:path}}}),/<img/);
 assert.match(scene(model,{}, {[camera.entity]:{state:"idle",attributes:{entity_picture:"/api/camera_proxy/camera.fixture?token=example"}}}),/<img/);
});
test("portraits accept selected native image paths rather than external URLs",()=>{
 const model={cards:[{kind:"person",title:"Casey",avatar_entity:"person.fixture",items:[event]}]};
 assert.doesNotMatch(scene(model,{}, {"person.fixture":{attributes:{entity_picture:"https://example.com/portrait.jpg"}}}),/<img/);
 assert.match(scene(model,{}, {"person.fixture":{attributes:{entity_picture:"/api/image/serve/fixture/512x512"}}}),/<img/);
});

test("school subjects render in order without invented kit; stale data hides them",()=>{
 const school={label:"Tomorrow at school",children:[{person:"fixture",name:"Casey",periods:[{subject:"PE"},{subject:"Science"},{subject:"PE"}],dated:[],rules:[],fallback:"School tomorrow",sources:[{entity:"calendar.private_source"}]}]};
 const body=scene({school,week:[{label:"Tuesday",items:[{...event,title:"Fictional next event"}]}]});
 assert.match(body,/Tomorrow at school/);assert.match(body,/<li>PE<\/li><li>Science<\/li><li>PE<\/li>/);
 assert.doesNotMatch(body,/uniform|equipment|calendar.private_source|School tomorrow|wall-family-card/);
 assert.match(body,/Week ahead/);assert.match(body,/Tuesday/);
 assert.doesNotMatch(scene({school},{valid_until:new Date(0).toISOString()}),/Casey|Science|PE/);
 school.children[0].periods=[];
 assert.match(scene({school}),/School tomorrow/);
});
