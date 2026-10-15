// Council-backed household context; no address form or synthetic calendar events.
export function initWaste({h, api}) {
  const section=document.getElementById("waste-collection"),root=document.getElementById("waste-body"),status=document.getElementById("waste-status");
  let data,proposal,token,busy=false,selected=new Set();
  const button=(label,fn)=>h("button",{type:"button",class:"btn ghost",disabled:busy,onclick:fn},label);
  const date=value=>new Intl.DateTimeFormat(undefined,{weekday:"long",day:"numeric",month:"short",timeZone:"Australia/Melbourne"}).format(new Date(value+"T12:00:00+11:00"));
  const next=(value,services)=>value ? date(value.date)+" · "+value.types.map(t=>services.find(s=>s.id===t)?.label||t).join(" · ") : "Not verified";
  async function load() {
    if(busy)return;
    busy=true;status.textContent="Reading saved waste service…";
    try{data=await api("api/waste");selected=new Set(data.screens);status.textContent=data.message;}
    catch(error){status.textContent=error.message;}
    finally{busy=false;render();}
  }
  async function action(action,extra={}) {
    if(busy)return;
    busy=true;render();status.textContent=action==="preview"?"Checking Council collection information…":"Checking the confirmed waste action…";
    try{
      const result=await api("api/waste",{method:"POST",body:JSON.stringify(action==="preview"?{action,...extra}:{action,revision:data.revision,epoch:data.epoch,confirm:true,...extra})});
      if(action==="preview"){proposal=result.proposal;token=result.preview_token;status.textContent="Review the collection day, next bins and displays before confirming.";}
      else{data=result;proposal=null;token=null;selected=new Set(data.screens);status.textContent=result.message;document.dispatchEvent(new CustomEvent("home-starter-saved"));}
    }catch(error){status.textContent=error.message+" Your existing schedule is preserved. Refresh saved state before retrying a write.";}
    finally{busy=false;render();}
  }
  function render() {
    if(!data){root.replaceChildren();return;}
    const shown=proposal||data;
    const day=h("select",{"aria-label":"Known collection day"},h("option",{value:""},"Use HA home location locally"),["Monday","Tuesday","Wednesday","Thursday","Friday"].map((d,n)=>h("option",{value:String(n)},d)));
    root.replaceChildren(...[
      h("h3",{},"Wodonga Council"),
      h("p",{},shown.day?"Collection day: "+shown.day:"Collection day not yet confirmed"),
      h("p",{},"Green weekly · Recycling/General alternating"),
      h("p",{},(proposal?"Proposed next: ":"Next: ")+next(shown.next,shown.services)),
      shown.following&&h("p",{class:"small muted"},"Following: "+next(shown.following,shown.services)),
      shown.configured&&h("p",{},shown.status.replaceAll("_"," ")+(shown.verified_at?" · Last verified "+new Date(shown.verified_at).toLocaleString():"")),
      shown.summary&&h("p",{class:"house-context-reminder"},shown.summary),
      shown.renewal_due&&h("p",{},"Next year's Council calendar is still needed. This year's pattern will not be extended."),
      data.entity_issue&&h("p",{},data.entity_issue),
      h("p",{class:"small muted"},"HA's home point is matched on this server against Council's public collection areas. Coordinates and addresses are neither sent to Council nor saved here."),
      h("div",{class:"screen-fields"},h("label",{class:"screen-field"},h("span",{},"Collection day, if you already know it"),day)),
      proposal&&h("fieldset",{},h("legend",{},"Screens for bin context"),data.screen_choices.map(s=>h("label",{class:"screen-physical-check"},
        h("input",{type:"checkbox",checked:selected.has(s.id),onchange:e=>{if(e.target.checked)selected.add(s.id);else selected.delete(s.id);}}),s.name))),
      proposal&&h("p",{},"Confirming saves this service and creates six native bin/status helpers plus one expiring data source. HA can record their bin dates and provenance; no address is included. No calendar events or automations are created."),
      h("div",{class:"actions"},
        button("Check Wodonga collection service",()=>action("preview",{day:day.value===""?null:Number(day.value)})),
        proposal&&button("Confirm service and create bin entities",()=>action("confirm",{preview_token:token,screens:[...selected]})),
        data.configured&&button("Refresh Council schedule",()=>action("refresh")),
        data.configured&&!data.entities_ready&&button("Confirm prepare missing bin entities",()=>action("prepare")),
        button("Refresh saved waste state",load)),
      h("p",{class:"small muted"},"Reminders appear from 6pm the evening before until 6am on collection day, then leave active attention. This is expiry, not a claim that bins were collected. Council says public holidays keep normal collection days."),
      h("p",{class:"small muted"},"Existing dashboards are preserved. Selected screens gain conditional bin context when you explicitly generate, review and publish them; already-published contextual walls can refresh without a dashboard rewrite."),
      h("details",{},h("summary",{},"Schedule sources and currentness"),h("p",{},"Checked daily. A temporary outage retains the last verified answer for up to seven days within its annual validity, clearly labelled. Expired or conflicting evidence requires checking."),
        h("pre",{},JSON.stringify(shown.sources,null,2)))
    ].filter(Boolean));
    if(busy)root.querySelectorAll("input,select,button").forEach(el=>el.disabled=true);
  }
  section.addEventListener("toggle",()=>{if(section.open&&!data)load();});
}
