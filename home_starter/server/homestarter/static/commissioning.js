import { PREPARATION } from "./house.js";
import { musicRuntime } from "./music-runtime.js";

const TITLES = { music: "Music & radio", displays: "Household displays", calendars: "Calendars & events", climate: "Heating & cooling", communications: "Household calling / intercom", cameras: "Cameras & doorbells", presence: "Presence", appliances: "Appliances", lighting: "Lighting & power", waste: "Waste collection / bins", voice: "Voice" };
const STAGES = ["Welcome", "Prepare", "Found", "Household", "Choose", "Configure", "Review", "Verify"];
const phaseStep = { not_started: 0, preparing: 1, scanned: 2, household_defined: 4, capabilities_selected: 5, configuration_incomplete: 5, reviewed: 6, executing: 7, verification_incomplete: 7, commissioned: 7 };
const emptyChoice = () => ({ intent: "later", sources: [], screens: [], answers: {}, permissions: {} });

export async function initCommissioning({ h, api, navigateHA }) {
  const root = document.getElementById("commissioning-body"), panel = document.getElementById("commissioning"), notice = document.getElementById("commissioning-status");
  let data, state, draft, discovery, step = 0, busy = false, timer;
  const btn = (text, run, primary = false) => h("button", { type: "button", class: "btn " + (primary ? "primary" : "ghost"), disabled: busy, onclick: run }, text);
  const field = (label, node) => h("label", { class: "screen-field" }, h("span", {}, label), node);
  const input = (label, value, set) => h("input", { "aria-label": label, value, maxlength: 80, oninput: e => set(e.target.value) });
  const select = (label, options, value, set) => h("select", { "aria-label": label, onchange: e => set(e.target.value) }, options.map(([id, text]) => h("option", { value: id, selected: value === id }, text)));
  const check = (text, selected, set) => h("label", { class: "checklist-row" }, h("input", { type: "checkbox", checked: selected, onchange: e => set(e.target.checked) }), text);
  const checks = (label, options, values, set) => {
    let selected = [...values];
    options = [...options, ...values.filter(value => !options.some(([id]) => id === value)).map(value => [value, "Missing saved reference: " + value])];
    return h("fieldset", {}, h("legend", {}, label), options.map(([id, text]) => check(text, selected.includes(id), yes => { selected = yes ? [...new Set([...selected, id])] : selected.filter(v => v !== id); set(selected); })));
  };
  const details = (title, ...children) => h("details", {}, h("summary", {}, title), ...children);
  const id = prefix => prefix + "_" + (crypto.randomUUID?.() || Math.random().toString(36).slice(2)).replaceAll("-", "").slice(0, 16);
  const row = key => discovery?.rows.find(r => r.id === key);
  const member = person => draft.readiness.members[person.id] ||= { kind: "", rooms: [], devices: [], presence: [], access: "later" };

  function adopt(result) {
    data = { ...data, ...result }; state = result.state; draft = structuredClone(state.draft);
    if (result.discovery) discovery = result.discovery;
    step = phaseStep[state.phase];
  }
  async function action(name, extra = {}) {
    if (busy) return;
    busy = true; notice.textContent = name === "scan" ? "Scanning the prepared house…" : "Saving this step…"; render();
    try {
      const result = await api("api/commissioning/" + name, { method: "POST", body: JSON.stringify({ revision: state.revision, epoch: state.epoch, ...extra }) });
      adopt(result); notice.textContent = "Saved. You can leave and return to this step.";
      if (!state.active && name !== "skip" && name !== "display") { location.reload(); return; }
      return true;
    } catch (error) { notice.textContent = error.message + " Your current answers are retained."; return false; }
    finally { busy = false; render(); }
  }
  function normalize() {
    for (const key of Object.keys(TITLES).filter(k => k !== "displays")) {
      const choice = draft.readiness.choices[key] ||= emptyChoice();
      choice.intent = draft.selected.includes(key) ? "wanted" : choice.intent === "not_wanted" ? "not_wanted" : "later";
    }
    if (!draft.selected.includes("music")) draft.install_music = false;
    if (!draft.selected.includes("displays")) draft.publish_ids = [];
  }
  function save(stage) { normalize(); return action("save", { step: stage, draft }); }
  function back(target) { step = target; render(); }

  function household() {
    let newName = "", newRole = "adult";
    return h("div", {}, h("h2", {}, "Who lives here?"), h("p", {}, "Use preferred names. Include regular occupants; add a guest only when a personal view is useful. No account or access is created here."),
      draft.house.people.map(person => {
        const context = member(person);
        return details(person.name,
          field("Preferred name", input("Preferred name for " + person.id, person.name, value => person.name = value)),
          field("Adult or child", select("Household role for " + person.name, [["", "Choose adult or child"], ["adult", "Adult"], ["child", "Child"]], context.kind, value => { context.kind = value; person.audience = value === "adult" ? "adult" : "everyone"; })),
          field("Home Assistant access", select("HA access for " + person.name, [["later", "Decide later"], ["yes", "Needs access — manage in HA"], ["no", "No HA account needed"]], context.access, value => context.access = value)),
          checks("Rooms for " + person.name, (discovery?.areas || []).map(a => [a.area_id, a.name]), context.rooms, value => context.rooms = value),
          checks("Personal devices for " + person.name, (discovery?.devices || []).map(d => [d.id, d.name]), context.devices, value => context.devices = value),
          checks("Existing person or presence source for " + person.name, (row("presence")?.sources || []).map(s => [s.id, s.name]), context.presence, value => context.presence = value));
      }),
      field("Name or nickname", input("Name or nickname", "", value => newName = value)),
      field("Household role", select("New household role", [["adult", "Adult"], ["child", "Child"]], newRole, value => newRole = value)),
      btn("Add household member", () => {
        if (!newName.trim()) { notice.textContent = "Enter a preferred name first."; return; }
        const person = { id: id("person"), name: newName.trim(), audience: newRole === "adult" ? "adult" : "everyone" };
        draft.house.people.push(person); member(person).kind = newRole; render();
      }),
      h("p", { class: "small muted" }, "Existing presence sources and devices are suggestions to confirm, never imported identities. Home Assistant account permissions remain authoritative."),
      btn("Continue to choices", () => save("household"), true), btn("Back to what was found", () => back(2)));
  }

  function choose() {
    return h("div", {}, h("h2", {}, "What would you like help with?"), h("p", {}, "Choose only what is useful. Recommendations come from this scan; nothing new is selected for you. You can skip everything for now."),
      Object.entries(TITLES).map(([key, title]) => {
        const found = row(key);
        const reason = found?.detected ? `Recommended to review · ${found.sources.length} HA sources found. Configuration and operation still need checking.`
          : key === "waste" ? "Not configured. Choose only if you want collection information and can connect a real source."
          : key === "displays" ? "Create useful views for a phone, tablet, wall, TV or reused device." : "Optional. Choose to explore setup and support.";
        return h("div", { class: "commission-choice" }, check(title, draft.selected.includes(key), yes => { draft.selected = yes ? [...new Set([...draft.selected, key])] : draft.selected.filter(k => k !== key); }), h("p", { class: "small muted" }, reason));
      }), h("p", { class: "small muted" }, "Energy and irrigation: no supported commissioning adapter yet. Existing integrations remain in Home Assistant."),
      btn("Configure selected capabilities", () => save("choose"), true), btn("Back to household", () => back(3)));
  }

  function screens() {
    let name = "", profile = "phone", personId = "", areaId = "";
    return h("div", {}, h("h3", {}, "Household displays"), h("p", {}, "Choose each physical screen's role and location. Wall is display-only; the other roles are interactive. Use a shared tablet role for a TV browser. Existing dashboards are preserved unless selected below."),
      draft.house.surfaces.map(screen => check("Publish or update " + screen.name, draft.publish_ids.includes(screen.id), yes => {
        draft.publish_ids = yes ? [...new Set([...draft.publish_ids, screen.id])] : draft.publish_ids.filter(v => v !== screen.id);
      })),
      field("Screen name", input("Commissioning screen name", "", value => name = value)),
      field("Screen role", select("Commissioning screen role", Object.entries(data.profiles), profile, value => profile = value)),
      field("Intended user", select("Commissioning screen person", [["", "Shared household"], ...draft.house.people.map(p => [p.id, p.name])], personId, value => personId = value)),
      field("Room", select("Commissioning screen room", [["", "Whole house"], ...(discovery?.areas || []).map(a => [a.area_id, a.name])], areaId, value => areaId = value)),
      btn("Add display to plan", () => {
        if (!name.trim()) { notice.textContent = "Name the screen first."; return; }
        const screen = { id: id("screen"), name: name.trim(), profile, person_id: personId || null, area_id: areaId || null, audience: "everyone" };
        draft.house.surfaces.push(screen); draft.publish_ids.push(screen.id); render();
      }));
  }

  function configure() {
    return h("div", {}, h("h2", {}, "Set up your choices"), h("p", {}, "Answers are staged in this plan. The review comes before installation or dashboard publication. Keep passwords and account details in the linked service."),
      !draft.selected.length && h("p", {}, "No optional capabilities selected. You can save a minimal household and add things later."),
      draft.selected.includes("displays") && screens(),
      draft.selected.filter(key => key !== "displays").map(key => {
        const found = row(key), choice = draft.readiness.choices[key] ||= emptyChoice();
        return details(TITLES[key],
          (found?.guide || []).map(text => h("p", {}, text)),
          key === "music" && h("p", {}, "Music Assistant: " + (data.music?.title || state.review?.music_state || "Check the existing service") + ". This does not establish connected providers or successful playback. Apple Music and other services depend on provider support in Music Assistant."),
          key === "music" && check("Run Music Assistant setup after Go if needed", draft.install_music, yes => draft.install_music = yes),
          key === "music" && musicRuntime({ h, api, navigateHA }, data.music?.open_path || data.music?.handoff_path),
          checks("Sources for " + TITLES[key], (found?.sources || []).map(s => [s.id, s.name + (s.available ? "" : " · unavailable")]), choice.sources, value => choice.sources = value),
          checks("Displays for " + TITLES[key], draft.house.surfaces.map(s => [s.id, s.name]), choice.screens, value => choice.screens = value),
          Object.entries(discovery?.answer_options[key] || {}).map(([question, options]) => {
            const label = question.replaceAll("_", " ") + " for " + TITLES[key];
            return ["accounts", "groups", "service", "plan"].includes(question)
              ? field(label, select(label, [["", "Choose"], ...options.map(v => [v, v.replaceAll("_", " ")])], choice.answers[question]?.[0] || "", value => choice.answers[question] = value ? [value] : []))
              : checks(label, options.map(v => [v, v.replaceAll("_", " ")]), choice.answers[question] || [], value => choice.answers[question] = value);
          }),
          key === "communications" && draft.house.people.map(p => checks("Allowed internal destinations for " + p.name, draft.house.people.filter(other => other.id !== p.id).map(other => [other.id, other.name]), choice.permissions[p.id] || [], value => choice.permissions[p.id] = value)),
          h("p", { class: "small muted" }, ["calendars", "waste"].includes(key) ? "Choose one consolidated source. Review reads upcoming events; no schedule is invented." : "This plan does not grant permissions or verify physical operation. Unsupported checks remain incomplete after Go."),
          btn("Open " + TITLES[key] + " setup", () => navigateHA(key === "music" ? data.music?.open_path || data.music?.handoff_path || "/config/apps" : key === "calendars" || key === "waste" ? "/calendar" : "/config/integrations")));
      }),
      h("p", { class: "small muted" }, "Returning from service setup? Save this step, then Scan again if sources were added. Sign-in and manual changes in Home Assistant are actions you control there."),
      btn("Save configuration choices", () => save("configure")), btn("Review setup plan", async () => { if (await save("configure")) await action("review"); }, true),
      btn("Back to choices", () => back(4)), btn("Scan again", () => action("scan")));
  }

  function review() {
    const plan = state.review;
    return h("div", {}, h("h2", {}, "Ready to set up your home"),
      h("p", {}, `${draft.house.people.length} household members · ${draft.selected.length} selected capabilities · ${plan.screens.length} screens selected for publication`),
      h("h3", {}, "Household"), h("ul", {}, draft.house.people.map(person => h("li", {}, `${person.name} · ${draft.readiness.members[person.id].kind} · HA access: ${draft.readiness.members[person.id].access}`))),
      h("p", { class: "small muted" }, "Access is an intention; no Home Assistant account or permission is created."),
      draft.selected.filter(key => key !== "displays").map(key => {
        const choice = draft.readiness.choices[key];
        const sources = choice.sources.map(id => row(key)?.sources.find(s => s.id === id)?.name || id);
        const displays = choice.screens.map(id => draft.house.surfaces.find(s => s.id === id)?.name || id);
        return h("div", {}, h("h3", {}, TITLES[key]),
          h("ul", {}, h("li", {}, "Sources: " + (sources.join(", ") || "Not chosen")), h("li", {}, "Displays: " + (displays.join(", ") || "Not chosen")),
            Object.entries(choice.answers).map(([question, answers]) => h("li", {}, question.replaceAll("_", " ") + ": " + (answers.map(v => v.replaceAll("_", " ")).join(", ") || "Not chosen")))),
          key === "communications" && h("p", {}, "Call plan only: " + draft.house.people.map(person => person.name + " can call " + ((choice.permissions[person.id] || []).map(id => draft.house.people.find(p => p.id === id)?.name || id).join(", ") || "no one until configured")).join("; ")));
      }),
      h("ul", {}, Object.entries(TITLES).map(([key, title]) => h("li", {}, title + " — " + (draft.selected.includes(key) ? "Selected; verification shown separately" : "Skipped")))),
      h("h3", {}, "Will be changed automatically"), h("ul", {}, plan.automatic.map(text => h("li", {}, text))),
      h("h3", {}, "Requires your sign-in or approval"), h("ul", {}, (plan.sign_in.length ? plan.sign_in : ["No sign-in requested by this plan."]).map(text => h("li", {}, text))),
      h("h3", {}, "Manual setup and verification"), h("ul", {}, (plan.manual.length ? plan.manual : ["No additional service configuration selected."]).map(text => h("li", {}, text))),
      Object.entries(plan.checks).map(([key, check]) => h("p", {}, TITLES[key] + " — " + check.detail)),
      details("Review each generated view", plan.screens.length ? plan.screens.map(item => h("div", {}, h("h3", {}, item.generated.surface.name),
        h("p", {}, `${item.generated.admitted.length} source-backed items. Existing edits are protected.`), h("ul", {}, item.generated.admitted.map(entry => h("li", {}, entry.name + ": " + entry.reason))),
        details("Dashboard configuration", h("pre", {}, JSON.stringify(item.generated.config, null, 2))))) : h("p", {}, "No dashboard will be written.")),
      h("p", {}, "Set up my home applies only this reviewed plan. Service or control tests that are unsupported stay incomplete. A failure keeps other saved work."),
      btn("Set up my home", () => action("go", { token: plan.token, confirm: true }), true), btn("Edit plan", () => action("edit")));
  }

  function execution() {
    const done = state.phase === "commissioned";
    return h("div", {}, h("h2", {}, done ? "Setup review complete" : state.phase === "executing" ? "Setting up your home" : "Finish verification"),
      h("p", {}, done ? "Verified items and deliberate skips are listed separately. Home Readiness is where you return as the house changes." : "Saved configuration and working checks are separate. Fix, retry or deliberately skip an optional item."),
      h("ul", { class: "plain" }, Object.entries(state.results).map(([key, result]) => h("li", { class: "commission-result" },
        h("strong", {}, (TITLES[key] || (key.startsWith("display:") ? "Display" : key === "household" ? "Household" : "Execution")) + " — " + result.status), h("p", {}, result.detail),
        result.url_path && btn("Open published screen", () => navigateHA("/" + result.url_path + "/home")),
        !done && result.status === "published" && btn("I opened this screen and it displayed correctly", () => action("display", { key, confirm: true })),
        !done && ["incomplete", "published"].includes(result.status) && !["household", "execution", "music_installer"].includes(key) && btn("Skip " + (TITLES[key] || "this display") + " for now", () => action("skip", { key, confirm: true })),
        !done && result.status === "incomplete" && TITLES[key] && btn("Fix " + TITLES[key] + " now", () => navigateHA(key === "music" ? data.music?.open_path || data.music?.handoff_path || "/config/apps" : "/config/integrations"))))),
      state.phase === "executing" && h("p", { role: "status" }, "Progress is saved after each result. You can return if this page closes."),
      !done && state.phase === "verification_incomplete" && state.results.music?.status === "incomplete" && musicRuntime({ h, api, navigateHA }, data.music?.open_path || data.music?.handoff_path),
      state.phase === "verification_incomplete" && h("div", { class: "actions" }, btn("Retry incomplete checks", () => action("retry")), btn("Edit and review plan", () => action("edit"))),
      done && btn("Go to Home Readiness", () => { location.hash = "#home-readiness"; location.reload(); }, true));
  }

  function render() {
    clearTimeout(timer);
    panel.hidden = false;
    document.body.dataset.commissioning = state.active || state.phase === "commissioned" && step === 7 ? "active" : "maintenance";
    if (!state.active && state.phase !== "commissioned") {
      document.getElementById("house-changes").after(panel);
      root.replaceChildren(h("h2", {}, "Finish setup when useful"), h("p", {}, "Your existing configuration is preserved. Missing commissioning information does not mean your home is unconfigured."), btn("Finish setup", () => action("start")));
      return;
    }
    const progress = h("ol", { class: "commission-progress", "aria-label": "Setup progress" }, STAGES.map((label, index) => h("li", { "aria-current": index === step ? "step" : null }, label)));
    const content = step === 0 ? h("div", {}, h("h2", {}, "Make Home Assistant useful for your household"), h("p", {}, "Prepare the house, discover what is already connected, tell us who lives here and choose what you want help with. Review the plan before Home Starter installs anything or publishes household views."), h("p", {}, "We will verify supported results and keep unfinished service or device tests visible. You can leave and resume setup."), btn("Prepare my home", () => action("start"), true))
      : step === 1 ? h("div", {}, h("h2", {}, "Fresh Batteries"), h("p", {}, "Give Home Assistant a fair chance to see the things you want to use. Do what makes sense for your home; no need to tick everything."), PREPARATION.map(text => check(text, false, () => {})), btn("Scan my home", () => action("scan"), true))
      : step === 2 ? h("div", {}, h("h2", {}, "Here is what we found"), h("ul", { class: "commission-summary" }, Object.entries(state.scan || {}).map(([label, count]) => h("li", {}, `${count} ${label}`))),
        h("p", {}, "Counts describe HA sources, not guaranteed physical devices. Phones, TVs, duplicate devices and room ownership need your confirmation. Minor cleanup can wait."),
        details("Review rooms, unavailable devices and source details", h("p", {}, "Assign rooms in Home Assistant when known; otherwise explicitly ignore or hide unresolved devices below. Unavailable does not prove broken."),
          (discovery?.room_devices || []).map(device => field(device.name, select("Room decision for " + device.name, [["", "Unresolved — revisit later"], ["ignored", "Ignore for household views"], ["hidden", "Hide from household views"]], draft.readiness.devices[device.id] || "", value => { if (value) draft.readiness.devices[device.id] = value; else delete draft.readiness.devices[device.id]; }))),
          btn("Open Home Assistant rooms and devices", () => navigateHA("/config/devices/dashboard"))),
        btn("Tell us about your household", () => back(3), true), btn("Scan again", () => action("scan")))
      : step === 3 ? household() : step === 4 ? choose() : step === 5 ? configure() : step === 6 ? review() : execution();
    root.replaceChildren(...[progress, content, state.legacy && !["executing", "verification_incomplete", "commissioned"].includes(state.phase) ? btn("Return to house status without applying this plan", () => action("leave")) : null].filter(Boolean));
    root.querySelectorAll("input, select, button").forEach(node => node.disabled = busy);
    if (state.phase === "executing") timer = setTimeout(poll, 1500);
  }
  async function poll() {
    try { adopt(await api("api/commissioning")); render(); }
    catch (error) { notice.textContent = error.message + " Saved work is retained. Reload to check progress."; }
  }
  try {
    adopt(await api("api/commissioning"));
    notice.textContent = state.phase === "not_started" && state.active ? "Ready when you are. Start by preparing your home." : "Saved setup loaded. Continue when useful.";
    // Commissioned homes open maintenance; graduation is only shown immediately after Go.
    if (state.phase === "commissioned") { document.body.dataset.commissioning = "maintenance"; panel.hidden = true; return false; }
    render(); return state.active;
  } catch (error) {
    panel.hidden = false; notice.textContent = error.message; root.replaceChildren(btn("Reload saved setup", () => location.reload()));
    return true;
  }
}
