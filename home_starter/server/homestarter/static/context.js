// Explicit date rules and event links; the calendar remains the source of events.
export function initContext({h, api}) {
  const section = document.getElementById("household-context");
  const root = document.getElementById("context-body"), status = document.getElementById("context-status");
  let data, draft, dirty = false, busy = false;
  const button = (name, action) => h("button", {type:"button",class:"btn ghost",disabled:busy,onclick:action}, name);
  const field = (name, control) => h("label", {class:"screen-field"}, h("span",{},name),control);
  function input(name, value, change, type="text") {
    return h("input", {type,value:value ?? "","aria-label":name,onchange:e=>{change(e.target.value);dirty=true;}});
  }
  function people(value, change) {
    return h("fieldset",{},h("legend",{},"Applies to (leave empty for household)"),Object.entries(data.people).map(([id,name])=>h("label",{},
      h("input",{type:"checkbox",checked:value.includes(id),onchange:e=>{change(e.target.checked?[...value,id]:value.filter(p=>p!==id));dirty=true;render();}}),name)));
  }
  async function refresh() {
    if(busy || dirty) {status.textContent="Save or discard the current changes before refreshing.";return;}
    busy=true;status.textContent="Reading the chosen calendar and household rules…";
    try {data=await api("api/context");draft=structuredClone(data.settings);render();status.textContent="Current context read. Calendar event contents are not saved in Home Starter settings.";}
    catch(error){status.textContent=error.message+". Saved choices are preserved.";}
    finally{busy=false;render();}
  }
  async function save() {
    busy=true;render();
    try {data=await api("api/context",{method:"POST",body:JSON.stringify({revision:data.revision,epoch:data.epoch,settings:draft})});draft=structuredClone(data.settings);dirty=false;status.textContent="Context choices saved. Published wall context refreshes within a minute.";}
    catch(error){status.textContent=error.message+". Your draft remains here.";}
    finally{busy=false;render();status.focus();}
  }
  function render() {
    if(!data)return;
    const warnings = data.issues.length ? h("p",{},data.issues.join(" · ")):h("p",{},"Selected calendar read successfully.");
    root.replaceChildren(warnings,h("p",{class:"small muted"},"Use one consolidated calendar in Home Readiness. No school, sport or work service is inferred from an event title."),
      h("a",{href:"#home-readiness",class:"btn ghost",onclick:()=>{for(let n=document.getElementById("home-readiness");n;n=n.parentElement)if(n.tagName==="DETAILS")n.open=true;}},"Review calendar source and displays"),
      h("details",{},h("summary",{},"Current context"),h("pre",{},data.near+"\n\n"+data.ahead)));
    for(const rule of draft.rules) {
      const days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
      root.append(h("details",{class:"house-row"},h("summary",{},rule.text || "New morning rule"),
        field("Morning rule",input("Morning rule "+rule.id,rule.text,v=>rule.text=v)),
        people(rule.people,v=>rule.people=v),
        h("div",{class:"screen-fields"},
          field("Applies from",input("Rule starts "+rule.id,rule.start,v=>rule.start=v,"date")),
          field("Applies through",input("Rule ends "+rule.id,rule.end,v=>rule.end=v,"date"))),
        h("fieldset",{},h("legend",{},"Applicable mornings"),days.map((day,d)=>h("label",{},h("input",{type:"checkbox",checked:rule.weekdays.includes(d),onchange:e=>{rule.weekdays=e.target.checked?[...rule.weekdays,d]:rule.weekdays.filter(n=>n!==d);dirty=true;}}),day))),
        button("Remove rule",()=>{draft.rules=draft.rules.filter(r=>r!==rule);dirty=true;render();})));
    }
    root.append(button("Add date-scoped morning rule",()=>{draft.rules.push({id:"rule_"+Date.now().toString(36),text:"",people:[],start:"",end:"",weekdays:[]});dirty=true;render();}));
    const choose=h("select",{"aria-label":"Event to link"},h("option",{value:""},"Choose a current event"),data.events.filter(e=>!e.all_day).map(e=>h("option",{value:e.key},e.title+" · "+new Date(e.start).toLocaleString())));
    root.append(h("details",{},h("summary",{},"People and departures for a chosen event"),field("Event",choose),
      h("p",{class:"small muted"},"Only explicit travel minutes, practical margin and an earlier preferred routine are used. Leave by is rounded earlier to five or ten minutes. Event changes reopen the link; no travel estimate is invented."),
      button("Link selected event",()=>{if(!choose.value)return;draft.events[choose.value] ||= {people:[],travel_minutes:null,buffer_minutes:0,round_minutes:5,routine_time:null};dirty=true;render();})));
    for(const [key,link] of Object.entries(draft.events)) {
      const event=data.events.find(e=>e.key===key);
      root.append(h("details",{class:"house-row"},h("summary",{},event?.title || "Event no longer in the verified horizon"),
        people(link.people,v=>link.people=v),
        h("div",{class:"screen-fields"},
          field("Travel minutes (known, optional)",input("Travel minutes "+key,link.travel_minutes,v=>link.travel_minutes=v===""?null:Number(v),"number")),
          field("Practical margin in minutes",input("Departure margin "+key,link.buffer_minutes,v=>link.buffer_minutes=Number(v),"number")),
          field("Preferred routine departure (optional)",input("Routine departure "+key,link.routine_time,v=>link.routine_time=v||null,"time")),
          field("Round earlier to",h("select",{"aria-label":"Departure rounding "+key,onchange:e=>{link.round_minutes=Number(e.target.value);dirty=true;}},[5,10].map(n=>h("option",{value:n,selected:link.round_minutes===n},n+" minutes"))))),
        button("Remove event link",()=>{delete draft.events[key];dirty=true;render();})));
    }
    root.append(h("p",{class:"small muted"},"Save changes records only these explicit rules and event links. It does not modify the calendar, people or dashboards. Wall publication separately permits displayed context in HA state/recorder; HA account access still applies."),
      button("Save context choices",save),button("Discard draft",()=>{draft=structuredClone(data.settings);dirty=false;render();}),button("Refresh context",refresh));
    root.querySelectorAll("input, select, button").forEach(control=>{control.disabled=busy;});
  }
  section.addEventListener("toggle",()=>{if(section.open&&!data)refresh();});
}
