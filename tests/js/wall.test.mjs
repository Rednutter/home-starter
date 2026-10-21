import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const render=new Function("hass","variables","html","window",["decorative.js","wall-wallpaper.js","wall-content.js"].map(name=>readFileSync(new URL("../../home_starter/server/homestarter/static/"+name,import.meta.url),"utf8")).join("\n"));
function scene(model={},attrs={},extraStates={},configChanges={}) {
 const until=new Date(Date.now()+60000).toISOString();
 const config={title:"Example board",surface_id:"wall",epoch:2,context:"sensor.context",...configChanges};
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

test("wall rendering uses the selected local wallpaper without external image URLs",()=>{
 const wallpapers=["morning","day","afternoon","evening","night"].map(period=>({period,id:`${period}-fixture`}));
 const body=scene({}, {}, {}, {wallpapers});
 const id=body.match(/data-wallpaper="([a-z-]+)"/)[1];
 assert.ok(wallpapers.some(row=>row.id===id));
 assert.ok(body.includes(`--wall-landscape:var(--wallpaper-${id})`));
 assert.doesNotMatch(body,/https?:\/\//);
});
test("person cards group real preparation and departures without a generic movement card",()=>{
 const body=scene({next_movement:event,cards:[{kind:"person",title:"Casey",items:[{title:"Sports kit + hat",when:"This morning"},event]}]});
 assert.match(body,/Sports kit \+ hat/);assert.match(body,/Leave /);assert.match(body,/School/);assert.doesNotMatch(body,/<time>This morning/);
});
test("forecast values are real optional data, never an inferred high",()=>{
 const current=scene({weather:{temperature:14,condition:"sunny"}});
 assert.match(current,/14°/);assert.match(current,/Forecast high unavailable/);assert.doesNotMatch(current,/→/);
 const forecast=scene({weather:{temperature:14,high:20,condition:"sunny"}});
 assert.match(forecast,/20°<\/strong><small>High/);assert.match(forecast,/14° now/);assert.doesNotMatch(forecast,/→/);
});
test("missing status is honest and unselected categories leave no empty containers",()=>{
 const body=scene();assert.match(body,/Home/);assert.doesNotMatch(body,/Climate|Security|Lights|Cameras|wall-family-card/);
 assert.match(body,/Status unavailable/);assert.doesNotMatch(body,/All good|All off|Armed/);
});

test("active lights show restrained named outline icons with overflow and no stale or off indicators",()=>{
 const model={household_status:{lights:"5 on",lights_on:[{name:"Reading <lamp>",icon:"mdi:lamp"},...Array.from({length:4},(_,n)=>({name:"Fixture "+n,icon:"mdi:ceiling-light"}))]}};
 const body=scene(model);
 assert.equal((body.match(/class="wall-lit-light"/g)||[]).length,3);
 assert.match(body,/Reading &lt;lamp&gt;/);assert.match(body,/aria-label="2 more on">\+2/);
 assert.doesNotMatch(body,/<strong>5 on<\/strong>/);
 assert.doesNotMatch(scene({household_status:{lights:"All off",lights_on:[]}}),/wall-lights-on/);
 assert.match(scene({household_status:{lights:"All off",lights_on:[]}}),/All off/);
 assert.doesNotMatch(scene(model,{valid_until:new Date(0).toISOString()}),/wall-lights-on|Reading/);
});

test("preview weather uses two lines with inline range labels and no current-observation clutter",()=>{
 const body=scene({focus:{preview:true,mode:"tomorrow_preview"},weather:{preview:true,focus_date:"2026-10-19",temperature:14,low:10,high:20,condition:"rainy",forecast_condition:"sunny"}});
 assert.match(body,/Tomorrow · 10° low · Sunny/);assert.match(body,/10° low/);assert.match(body,/20°<\/strong><small>High/);assert.doesNotMatch(body.match(/<section class="wall-weather"[\s\S]*?<\/section>/)[0],/Monday|Now 14°|→/);
 assert.match(scene({weather:{temperature:14,high:20,condition:"sunny",precipitation_probability:0}}),/<h2>14° now · Sunny<\/h2>/);
 assert.doesNotMatch(scene({weather:{temperature:14,high:20,condition:"sunny",precipitation_probability:0}}),/chance of rain/);
 assert.match(scene({weather:{temperature:14,high:20,condition:"rainy",precipitation_probability:70}}),/wall-weather-impact">70% chance of rain/);
});

test("night removes planning cards and chronology while retaining weather and household status",()=>{
 const school={label:"Tomorrow at school",children:[{person:"fixture",name:"Casey",status:"available",periods:[{subject:"Science",start:"2026-10-19T08:50:00+11:00"}],dated:[],rules:["Confirmed hat requirement"],commitments:[{...event,title:"Training"}]}]};
 const body=scene({focus:{night:true,preview:true,label:"Tomorrow"},school,timeline:{label:"Tomorrow",items:[{title:"School",time:"8:50",people:["Casey"]}]},week:[{label:"Tuesday",items:[event]}]});
 assert.match(body,/data-night="true"/);assert.match(body,/wall-header/);assert.match(body,/wall-weather/);assert.match(body,/wall-household/);
 assert.doesNotMatch(body,/Casey|Confirmed hat requirement|Training|Science|wall-family|wall-agenda|wall-school-periods|Week ahead|wall-secondary/);
 const afterMidnight=scene({focus:{night:true,preview:false,label:"Today"},weather:{focus_date:"2026-10-19",high:23,low:11,temperature:15,forecast_condition:"partlycloudy"}});
 assert.match(afterMidnight,/Today · 11° low · Partly cloudy/);assert.match(afterMidnight,/23°<\/strong><small>High/);assert.doesNotMatch(afterMidnight.match(/<section class="wall-weather"[\s\S]*?<\/section>/)[0],/Tomorrow|Monday|→/);
 const missing=scene({focus:{preview:true},weather:{low:11}});
 assert.match(missing,/11° low/);assert.match(missing,/Forecast high unavailable/);assert.doesNotMatch(missing,/<strong>High<\/strong>|wall-temperature-primary/);
});
test("expired calendar rows disappear independently",()=>{
 const body=scene({cards:[{kind:"person",title:"Casey",items:[{...event,title:"Finished",ends_at:new Date(0).toISOString()}]}],timeline:{label:"Today",items:[{...event,title:"Finished",ends_at:new Date(0).toISOString()}]}});
 assert.doesNotMatch(body,/Finished/);
});

test("quiet night retains one confirmed common school departure without restoring cards",()=>{
 const leave_at=new Date(Date.now()+86400000).toISOString();
 const school={children:Array.from({length:3},()=>({next_departure:{leave_at},periods:[]}))};
 const model={school,focus:{night:true,preview:true,label:"Tomorrow"}};
 const body=scene(model);
 assert.match(body,/wall-night-departure">Tomorrow · School · Leave /);
 assert.doesNotMatch(body,/wall-family|wall-agenda/);
 school.children[0].next_departure=null;
 assert.doesNotMatch(scene(model),/wall-night-departure/);
 school.children.forEach(child=>child.next_departure={leave_at:new Date(0).toISOString()});
 assert.doesNotMatch(scene(model),/wall-night-departure/);
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

test("camera area falls back to fresh playing media without replacing available cameras",()=>{
 const playing={title:'A <song>',artist:'Example artist',room:'Kitchen'};
 const model={household_status:{cameras:[],now_playing:[playing]}};
 let body=scene(model);
 assert.match(body,/aria-label="Now playing"/);assert.match(body,/A &lt;song&gt;/);assert.match(body,/Example artist · Kitchen/);
 model.household_status.cameras=[{entity:'camera.door',name:'Door',available:false}];
 body=scene(model);assert.match(body,/Now playing/);assert.doesNotMatch(body,/Door · Unavailable/);
 model.household_status.cameras[0].available=true;
 body=scene(model);assert.match(body,/>Cameras</);assert.doesNotMatch(body,/Now playing|A &lt;song&gt;/);
 // Night hides ordinary snapshots, but that is not permission to replace configured cameras.
 assert.doesNotMatch(scene({...model,focus:{night:true}}),/Now playing/);
 assert.doesNotMatch(scene(model,{valid_until:new Date(0).toISOString()}),/Example artist|A &lt;song&gt;/);
 assert.doesNotMatch(scene({household_status:{now_playing:[]}}),/Now playing|wall-media-status/);
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
 assert.doesNotMatch(body,/Week ahead/);assert.match(body,/>Tuesday</);
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
 assert.match(body,/<aside class="wall-agenda">[\s\S]*wall-timeline[\s\S]*wall-upcoming/);
 assert.doesNotMatch(body,/wall-school-children/);
});

test("one timeline places compact future days immediately after the detailed focus-day list",()=>{
 const body=scene({timeline:{label:"Today",items:[{...event,id:"today",title:"Today activity",time:"8:30",people:["Casey"],detail:"Leave 8:00",leave_at:null}]},upcoming_days:[{label:"Tomorrow",items:[{...event,id:"tomorrow",title:"Tomorrow activity",time:"9:00",people:["Casey"]}]}]});
 assert.equal((body.match(/class="wall-surface wall-timeline"/g)||[]).length,1);
 assert.match(body,/Today activity[\s\S]*Leave 8:00[\s\S]*class="wall-upcoming"[\s\S]*Tomorrow[\s\S]*Tomorrow activity/);
 assert.doesNotMatch(body,/Week ahead|wall-secondary|wall-week-days/);
 assert.equal((body.match(/class="wall-line-item /g)||[]).length,1);
 assert.equal((body.match(/class="wall-upcoming-row /g)||[]).length,1);
});

test("afternoon school preview is labelled tomorrow while the household timeline stays today",()=>{
 const school={label:"Tomorrow at school",preview:true,children:[{person:"fixture",name:"Casey",periods:[{subject:"Science",start:"2026-10-20T09:00:00+11:00",end:"2026-10-20T10:00:00+11:00"}],dated:[],rules:[],next_departure:{leave_at:"2026-10-20T08:30:00+11:00"}}]};
 const body=scene({focus:{preview:false,label:"Today"},school,timeline:{label:"Today",items:[{...event,title:"Today's training"}]}});
 assert.match(body,/<small>Tomorrow<\/small>Leave 8:30/);
 assert.match(body,/wall-school-periods[\s\S]*Science/);
 assert.match(body,/<h2>Today[\s\S]*Today&#39;s training/);
});

test("lesson cards span native slots and keep slim breaks aligned across children",()=>{
 const starts=['08:50','09:11','10:01','11:10','12:01','13:35','14:26'];
 const ends=['09:10','10:00','10:50','12:00','12:50','14:25','15:15'];
 const subjects=[['Connect','Science','Science','Languages','PE','Maths','Maths'],['Connect','Science','Science','Studies','Maths','English','English'],['Assembly','Core','Core','Core','Core','STEM','STEM']];
 const school={children:subjects.map((subjects,n)=>({person:`fixture${n}`,name:`Example ${n}`,periods:subjects.map((subject,i)=>({subject,start:`2026-10-19T${starts[i]}:00+11:00`,end:`2026-10-19T${ends[i]}:00+11:00`})),rules:[],dated:[]}))};
 const body=scene({school});
 assert.equal((body.match(/grid-row:4\/span 1[^>]*data-period-count="0"[^>]*data-break="true"/g)||[]).length,3);
 assert.equal((body.match(/grid-row:7\/span 1[^>]*data-period-count="0"[^>]*data-break="true"/g)||[]).length,3);
 assert.equal((body.match(/grid-row:2\/span 2/g)||[]).length,3);
 assert.equal((body.match(/grid-row:8\/span 2/g)||[]).length,3);
 assert.equal((body.match(/role="separator" aria-label="Recess"/g)||[]).length,3);
 assert.equal((body.match(/role="separator" aria-label="Lunch"/g)||[]).length,3);
 assert.doesNotMatch(body,/wall-period-meta|wall-period-count|&times;|>Recess<|>Lunch</);
 assert.match(body,/grid-row:5\/span 2[^>]*>[\s\S]*?Core/);
 const night=scene({school,focus:{night:true}});
 assert.doesNotMatch(night,/wall-school-periods|>Recess<|>Lunch</);
});

test("morning readiness promotes confirmed departure and kit while retaining ordered subjects",()=>{
 const school={label:"Today at school",children:[{person:"fixture",name:"Casey",status:"available",importance:"soon",next_departure:{leave_at:event.leave_at},periods:[{subject:"Science",start:"2026-10-19T08:50:00+11:00"},{subject:"PE"}],dated:[],rules:["Confirmed hat requirement"]}]};
 const body=scene({focus:{preview:false,label:"Today"},school,timeline:{label:"Today",items:[{...event,time:"8:50"}]}});
 assert.match(body,/data-importance="soon"/);assert.match(body,/data-departure="true">Leave /);
 assert.match(body,/wall-school-periods[\s\S]*Science[\s\S]*PE[\s\S]*Confirmed hat requirement/);
 assert.match(body,/aria-label="Starts 8:50"><small>Starts<\/small>8:50/);
 school.children[0].next_departure=null;
 assert.match(scene({school}),/Starts 8:50/);
 school.children[0].periods=[];school.children[0].rules=[];school.children[0].fallback="Timetable temporarily unavailable";
 const unavailable=scene({school,issues:["Calendar needs verification"]});
 assert.match(unavailable,/data-incomplete="true"/);assert.match(unavailable,/Timetable temporarily unavailable/);
 assert.match(unavailable,/<aside class="wall-source-note"/);assert.doesNotMatch(unavailable,/School today|at school<\/p>|wall-camera-status|needs verification/);
});

test("priority replaces weather across the header and expires independently",()=>{
 const priority={id:"fixture",title:"School run in 10 minutes",people:["Casey"],action:"Leave 08:30",level:"soon",expires_at:new Date(Date.now()+600000).toISOString()};
 const body=scene({priority,timeline:{label:"Today",items:[event]}});
 assert.match(body,/data-priority="true"/);
 assert.match(body,/wall-priority/);
 assert.match(body,/School run in 10 minutes/);
 assert.match(body,/wall-priority-fallback/);
 assert.doesNotMatch(scene({priority:{...priority,expires_at:new Date(0).toISOString()}}),/data-priority="true"|School run in 10 minutes/);
});
test("schedule days use their own dated forecast and bin identity",()=>{
 const body=scene({timeline:{label:"Today",weather:{high:26,condition:"sunny"},items:[event]},upcoming_days:[{label:"Tomorrow",weather:{high:22,condition:"rainy"},items:[{...event,title:"Bins out tonight",bin_types:["general","recycling"]}]}]});
 assert.match(body,/Forecast high 26 degrees/);
 assert.match(body,/Forecast high 22 degrees/);
 assert.match(body,/data-bin="general"/);
 assert.match(body,/data-bin="recycling"/);
 const bin={...event,title:"Bins out tonight",bin_types:["general","organics"],detail:"Green + General waste"};
 const compact=scene({timeline:{label:"Today",items:[bin]},upcoming_days:[{label:"Tomorrow",items:[bin]}]});
 assert.match(compact,/Bins out tonight/);
 assert.match(compact,/data-bin="organics"/);
 assert.doesNotMatch(compact,/Green \+ General waste|wall-bin-label/);

 assert.match(scene({upcoming_days:[{label:"Next week",items:[event]}]}),/Forecast unavailable/);
});
test("utility slot permits structured replacement with escaped text",()=>{
 const body=scene({utility:{kind:"message",title:"Reminder <text>",body:"Example"}});
 assert.match(body,/data-region="utility" data-content="message"/);
 assert.match(body,/Reminder &lt;text&gt;/);
 assert.doesNotMatch(body,/wall-household/);
});
