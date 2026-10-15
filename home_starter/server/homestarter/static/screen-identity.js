// Administration only. Native HA owns users, passwords and display sessions.
export function initScreenIdentity({h, api, navigateHA}) {
  const section = document.getElementById("screen-identity"), root = document.getElementById("screen-identity-body");
  const status = document.getElementById("screen-identity-status");
  let data, selected = "", busy = false, review = false;
  const when = value => value ? new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(value)) : "not verified";
  const button = (label, action, disabled=false) => h("button", {type:"button",class:"btn ghost",disabled:busy||disabled,onclick:action},label);
  const field = (label, control) => h("label",{class:"screen-field"},h("span",{},label),control);
  const select = (label, options, value, onchange) => h("select",{"aria-label":label,onchange},options.map(([id,name])=>h("option",{value:id,selected:id===value},name)));
  async function load() {
    if(busy)return;
    busy=true;render();status.textContent="Reading native HA users and dashboard evidence…";
    try { data=await api("api/screens/identity");if(!data.screens.some(s=>s.id===selected&&s.required))selected=data.screens.find(s=>s.required)?.id||"";
      status.textContent=data.issue||"Display checks read. Dashboard publication and physical commissioning are separate."; }
    catch(error){status.textContent=error.message+". Existing screen choices are preserved.";}
    finally{busy=false;render();}
  }
  async function action(name,extra={}) {
    if(busy||!data)return;
    busy=true;render();status.textContent="Checking the confirmed display action…";
    try {data=await api("api/screens/identity",{method:"POST",body:JSON.stringify({revision:data.revision,epoch:data.epoch,surface:selected,action:name,confirm:true,...extra})});
      status.textContent="Display commissioning state saved and read back.";review=name!=="select"&&name!=="restrict";document.dispatchEvent(new CustomEvent("home-starter-display-checked"));}
    catch(error){status.textContent=error.message+" Refresh before retrying; an uncertain helper creation is not repeated automatically.";}
    finally{busy=false;render();}
  }
  function render() {
    if(!data){root.replaceChildren();return;}
    const screen=data.screens.find(s=>s.id===selected), record=screen?.record;
    const candidates=data.users.filter(u=>!u.issue||u.can_prepare), choice=record?.user_id||"";
    const account=select("Dedicated display account",[["","Choose an existing dedicated account"],...candidates.map(u=>[u.id,`${u.name} · ${u.permission==="read_only"?"read-only":"non-admin controls"}`])],choice);
    const check=(label,id)=>h("label",{class:"screen-physical-check"},h("input",{type:"checkbox",id}),label);
    const restart=select("Restart actually checked",[["","Choose"],["browser","Normal browser restart"],["app","Normal app restart"],["device","Normal device restart"]],"");
    root.replaceChildren(...[
      h("p",{},"Publishing saves the dashboard. Commissioning checks its dedicated HA account, then its use and login after restart on the physical display."),
      field("Fixed/shared screen",select("Display to commission",data.screens.filter(s=>s.required).map(s=>[s.id,s.name]),selected,e=>{selected=e.target.value;review=false;render();})),
      !screen&&h("p",{},"No fixed/shared screen is saved. Add the intended panel or wall under Screens first. Personal phones keep their own account setup."),
      screen&&h("div",{},h("h4",{},screen.name),h("p",{},`State: ${screen.stage}`),h("p",{class:"muted"},screen.issue||"Saved evidence matches the current account, screen and dashboard."),
        h("ul",{},h("li",{},`HA account: ${record ? data.users.find(u=>u.id===record.user_id)?.name||"unavailable" : "not confirmed"}`),
          h("li",{},`Authentication check: ${when(record?.session?.at)}`),h("li",{},`Restart login check: ${when(record?.restart?.at)}`),
          h("li",{},`Physical use: ${record?.physical ? "owner-confirmed "+when(record.physical.at) : "not verified"}`))),
      screen&&h("details",{},h("summary",{},"Dedicated account and permissions"),
        h("p",{},"In HA: Settings → People → Users → Add user. Use this screen's name, leave Administrator off and enable local-only access. Enter and keep its password in HA; Home Starter never asks for it. You can also reuse a suitable display account below."),
        h("p",{class:"small muted"},"Your authenticated administrator session can create a user without entering the owner password. If HA requests reauthentication, follow its prompt. Stop if the password is unavailable; do not guess repeatedly."),
        button("Open HA user management",()=>navigateHA("/config/users")),
        h("a",{href:"https://www.home-assistant.io/docs/locked_out/",target:"_blank",rel:"noopener noreferrer"},"Supported HA password recovery"),
        h("p",{class:"small muted"},"A normal non-admin HA user can control ordinary household entities; a dashboard does not restrict that access. A passive wall should prefer read-only. Accounts linked to household members are excluded. A reviewed, untracked display/other Person record may remain."),
        h("div",{class:"screen-fields"},field("Dedicated display account",account)),
        h("p",{class:"small muted"},screen.expected_permission==="read_only"?"This passive wall expects a native read-only account. Read-only users cannot press the current native session check; that verification remains unresolved, and this wall cannot be marked commissioned here.":"This interactive panel expects a local non-admin account with household control permissions."),
        button("Confirm this dedicated account",()=>action("select",{user_id:account.value,permission:screen.expected_permission}),!!data.issue),
        h("p",{class:"small muted"},"Confirming the same valid account keeps its checks. A different account, or changed account/dashboard settings, requires fresh session, restart and physical checks."),
        candidates.some(u=>u.can_prepare)&&button("Confirm enable local-only access and use selected display account",()=>action("local_only",{user_id:account.value,user_signature:data.users.find(u=>u.id===account.value)?.signature||""}),!!data.issue),
        candidates.some(u=>u.can_prepare)&&h("p",{class:"small muted"},"This explicit preparation only restricts the selected display account to local-network login. It preserves its password, permissions and any reviewed display-only Person record."),
        screen.expected_permission==="read_only"&&button("Confirm restrict selected account to local-only, read-only access",()=>action("restrict",{user_id:account.value,user_signature:data.users.find(u=>u.id===account.value)?.signature||""}),!!data.issue),
        data.users.some(u=>u.issue)&&h("details",{},h("summary",{},"Accounts not suitable for a dedicated display"),data.users.filter(u=>u.issue).map(u=>h("p",{class:"small muted"},`${u.name}: ${u.issue}`))),
        button("Refresh accounts and display checks",load)),
      screen&&h("details",{open:review},h("summary",{},"Verify on the physical display"),
        h("p",{},"Sign into HA on the AirTouch/tablet using its dedicated account. In that display's Profile → Appearance, select its intended default dashboard. Keep normal HA login persistence; clearing browser data or signing out removes the session."),
        button("Open intended dashboard",()=>navigateHA(screen.dashboard_path)),
        h("p",{},"Start the check below on this administrator device. On the physical display, open the check-page address shown, press Verify this display session, then return here and read the result. The same account on another device is not physical-screen proof."),
        h("p",{class:"small muted"},"Starting a check adds one native button helper and one separate native check dashboard. It operates no household equipment, stores no password/token and does not change the intended dashboard. The resources remain for future checks."),
        button("Confirm prepare session check",()=>{review=true;action("begin",{stage:"session"});},!record||!!data.issue),
        record?.page&&h("p",{},"Open this HA address on the physical display: ",h("code",{},`${window.location.origin}/${record.page.url_path}/home`)),
        record?.attempt&&h("p",{},`Waiting for ${record.attempt.stage==="restart"?"the new press after restart":"the first signed-in press"}. This attempt expires after 15 minutes.`),
        button("Read display session check",()=>{review=true;action("observe");},!record?.attempt||!!data.issue),
        h("p",{},"After the first verified press: start the restart check here, then restart the actual display's browser, app or device normally. Confirm its normal landing dashboard, operate the required controls (climate for AirTouch), and press the check page again without signing in again."),
        button("Start restart login check",()=>{review=true;action("begin",{stage:"restart"});},!record?.session||!!data.issue),
        h("fieldset",{},h("legend",{},"Confirm only what you checked on the physical screen"),
          check("The intended dashboard opened on that physical screen","display-dashboard-opened"),
          check("Its normal landing/default dashboard is the intended one","display-default-set"),
          check("Its required controls worked without admin access; I restored any test changes","display-controls-worked"),field("Restart actually checked",restart)),
        h("p",{class:"small muted"},"Physical use and the restart method are your report. HA proves the account that pressed the helper, not which piece of hardware was used. Session revocation and future browser-data clearing are not monitored."),
        button("Confirm physical screen commissioning",()=>action("physical",{dashboard_opened:document.getElementById("display-dashboard-opened").checked,
          default_set:document.getElementById("display-default-set").checked,controls_worked:document.getElementById("display-controls-worked").checked,restart_kind:restart.value}),!record?.restart||!!data.issue)),
    ].filter(Boolean));
    if(busy)root.querySelectorAll("button,input,select").forEach(el=>el.disabled=true);
  }
  section.addEventListener("toggle",()=>{if(section.open&&!data)load();});
  document.addEventListener("home-starter-saved",()=>{data=null;if(section.open)load();});
}
