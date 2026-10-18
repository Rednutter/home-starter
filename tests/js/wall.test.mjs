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
 assert.match(forecast,/20°<\/span><small>High/);assert.match(forecast,/14°<\/strong><small>Now/);assert.doesNotMatch(forecast,/→/);
});
test("missing status is honest and unselected categories leave no empty containers",()=>{
 const body=scene();assert.match(body,/Home/);assert.doesNotMatch(body,/Climate|Security|Lights|Cameras|wall-family-card/);
 assert.match(body,/Status unavailable/);assert.doesNotMatch(body,/All good|All off|Armed/);
});

test("preview weather uses two lines with inline range labels and no current-observation clutter",()=>{
 const body=scene({focus:{preview:true,mode:"tomorrow_preview"},weather:{preview:true,focus_date:"2026-10-19",temperature:14,low:10,high:20,condition:"rainy",forecast_condition:"sunny"}});
 assert.match(body,/Tomorrow · Sunny/);assert.match(body,/10°<\/span><small>Low/);assert.match(body,/20°<\/strong><small>High/);assert.doesNotMatch(body,/Monday|Now 14°|→/);
 assert.match(scene({weather:{temperature:14,high:20,condition:"sunny",precipitation_probability:0}}),/<h2>Sunny<\/h2>/);
 assert.doesNotMatch(scene({weather:{temperature:14,high:20,condition:"sunny",precipitation_probability:0}}),/chance of rain/);
 assert.match(scene({weather:{temperature:14,high:20,condition:"rainy",precipitation_probability:70}}),/wall-weather-impact">70% chance of rain/);
});

test("night keeps compact identities, confirmed requirements and household chronology without classes or week clutter",()=>{
 const school={label:"Tomorrow at school",children:[{person:"fixture",name:"Casey",status:"available",periods:[{subject:"Science",start:"2026-10-19T08:50:00+11:00"}],dated:[],rules:["Confirmed hat requirement"],commitments:[{...event,title:"Training"}]}]};
 const body=scene({focus:{night:true,preview:true,label:"Tomorrow"},school,timeline:{label:"Tomorrow",items:[{title:"School",time:"8:50",people:["Casey"]}]},week:[{label:"Tuesday",items:[event]}]});
 assert.match(body,/data-night="true"/);assert.match(body,/wall-avatar/);assert.match(body,/School · 8:50/);assert.match(body,/Confirmed hat requirement/);assert.match(body,/Training/);
 assert.doesNotMatch(body,/Science|wall-school-periods|Week ahead|wall-secondary/);
 const afterMidnight=scene({focus:{night:true,preview:false,label:"Today"},weather:{focus_date:"2026-10-19",high:23,low:11,temperature:15,forecast_condition:"partlycloudy"}});
 assert.match(afterMidnight,/Today · Partly cloudy/);assert.match(afterMidnight,/23°<\/strong><small>High/);assert.doesNotMatch(afterMidnight,/Tomorrow|Monday|→/);
 const missing=scene({focus:{preview:true},weather:{low:11}});
 assert.match(missing,/11°<\/span><small>Low/);assert.match(missing,/Forecast high unavailable/);assert.doesNotMatch(missing,/<strong>High<\/strong>|wall-temperature-primary/);
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
 assert.match(body,/Tomorrow at school/);assert.match(body,/<span>PE<\/span>[\s\S]*<span>Science<\/span>[\s\S]*<span>PE<\/span>/);
 assert.doesNotMatch(body,/uniform|equipment|calendar.private_source|School tomorrow/);
 assert.match(body,/Week ahead/);assert.match(body,/>Tue</);
 assert.doesNotMatch(scene({school},{valid_until:new Date(0).toISOString()}),/Casey|Science|PE/);
 school.children[0].periods=[];
 assert.match(scene({school}),/School tomorrow/);
});

test("reference school cards restore avatar identity and preserve adjacent period counts",()=>{
 const school={label:"Tomorrow at school",children:[{person:"fictional",name:"Casey",periods:[{subject:"Science"},{subject:"Science"},{subject:"PE"},{subject:"Science"}],dated:[],rules:[]}]};
 const body=scene({focus:{preview:true},school,week:[{label:"Tuesday",items:[{...event,title:"Fictional appointment"}]}]});
 assert.match(body,/wall-family-card wall-school-child wall-tone-0/);assert.match(body,/wall-avatar/);
 assert.match(body,/Tomorrow at school/);assert.match(body,/data-period-count="2"/);
 assert.equal((body.match(/data-period-count="1"/g)||[]).length,2);
 assert.match(body,/<aside class="wall-agenda">[\s\S]*wall-week wall-secondary/);
 assert.doesNotMatch(body,/wall-school-children/);
});
