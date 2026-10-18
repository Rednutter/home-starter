import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const render=new Function("hass","variables","html","window",readFileSync(new URL("../../home_starter/server/homestarter/static/wall-content.js",import.meta.url),"utf8"));
function scene(model={},attrs={},extraStates={},viewport={innerHeight:1080,location:{search:"?kiosk"}}) {
 const until=new Date(Date.now()+60000).toISOString();
 const config={title:"Example board",surface_id:"wall",epoch:2,context:"sensor.context"};
const states={"sensor.context":{attributes:{home_starter_context:{surface:"wall",epoch:2},checked_at:new Date(Date.now()-1000).toISOString(),valid_until:until,wall:{version:1,valid_until:until,day_state:"quiet_daytime",day_summary:"Quiet day",today_summary:"Quiet day",primary:"quiet",today_items:[],future_attention:[],household_exception:[],active_context:[],issues:[],...model},...attrs}},...extraStates};
 return render({states,connected:true,config:{time_zone:"Australia/Sydney"},locale:{language:"en-AU"}},{wall_json:JSON.stringify(config)},(_,body)=>body,viewport);
}

test("week capacity preserves different days before adding rows to a busy day",()=>{
 const groups=["Tuesday","Wednesday","Thursday","Friday"].map(label=>({label,items:[1,2,3].map(n=>({time:"5:00 pm",title:label+n}))}));
 const kiosk=scene({ahead_groups:groups},{},{},{innerHeight:768,location:{search:"?kiosk"}});
 for(const day of groups)assert.match(kiosk,new RegExp(day.label+"1"));
 assert.doesNotMatch(kiosk,/Tuesday2/);
 const chrome=scene({ahead_groups:groups},{},{},{innerHeight:768,location:{search:""}});
 assert.doesNotMatch(chrome,/Friday1/);
 const detailed=scene({ahead_groups:groups.map(g=>({...g,items:g.items.map(r=>({...r,people:["Example"],detail:"Leave by 16:30"}))}))},{},{},{innerHeight:768,location:{search:"?kiosk"}});
 assert.match(detailed,/Tuesday1/);assert.match(detailed,/Wednesday1/);assert.doesNotMatch(detailed,/Thursday1|Tuesday2/);
});

test("evening preparation shows confirmed facts with escaped text only",()=>{
 const model={phase:"evening",tomorrow_label:"Monday",tomorrow_preparation:[{title:"Bring <kit>",people:["Example"]}]};
 assert.match(scene(model),/Get ready for Monday/);assert.match(scene(model),/Bring &lt;kit&gt; · Example/);
 assert.doesNotMatch(scene({...model,phase:"morning"}),/Get ready|Bring/);
});
test("quiet wall keeps Today compact without a giant empty-state region or fixed device cards",()=>{
 const body=scene({today_summary:"Quiet Sunday"});assert.match(body,/Quiet Sunday/);
 assert.match(body,/wall-today-compact/);
 assert.doesNotMatch(body,/Nothing urgent right now|class="wall-quiet"|class="wall-upcoming|class="wall-context|class="wall-session|href=|onclick=|<button|wall-child|Lights|Cameras/);
});

test("weekday movement reclaims unused columns and omits an empty Today card",()=>{
 const movement={id:"school",title:"School",label:"Leave soon",detail:"Leave by 08:30"};
 const solo=scene({next_movement:movement,today_items:[{...movement,when:"08:50"}]});
 assert.match(solo,/data-horizon="hidden"/);assert.match(solo,/data-current="single"/);
 assert.doesNotMatch(solo,/class="wall-today /);
 const paired=scene({next_movement:movement,today_items:[{title:"Sports kit",when:"This morning"}]});
 assert.match(paired,/data-current="paired"/);assert.match(paired,/wall-item-note/);
 assert.doesNotMatch(paired,/<time>This morning/);
});

test("expired future facts release their space and sparse cards declare their content count",()=>{
 const expired=scene({tomorrow_items:[{title:"Finished",ends_at:new Date(0).toISOString()}]});
 assert.match(expired,/data-horizon="hidden"/);assert.doesNotMatch(expired,/class="wall-tomorrow/);
 const sparse=scene({tomorrow_items:[{title:"Exercise",time:"7:00"}]});
 assert.match(sparse,/class="wall-tomorrow wall-surface" data-count="1"/);
 const today=scene({layout:"today",today_items:[{title:"Appointment",time:"2:00 pm"}]});
 assert.match(today,/data-layout="today"/);assert.doesNotMatch(today,/wall-today-compact/);
});
test("quiet horizon gives Tomorrow and nonempty week groups the reclaimed space",()=>{
 const body=scene({layout:"tomorrow",tomorrow_label:"Monday",tomorrow_items:[{id:"one",time:"07:00",title:"Exercise",location:"Example Fitness"}],ahead_groups:[{label:"Tuesday",items:[{time:"16:00",title:"Music lesson"}]},{label:"Wednesday",items:[]}]});
 assert.match(body,/data-layout="tomorrow"/);assert.match(body,/wall-tomorrow/);assert.match(body,/Monday/);assert.match(body,/Week ahead/);assert.match(body,/Music lesson/);assert.doesNotMatch(body,/Wednesday|Nothing urgent/);
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
