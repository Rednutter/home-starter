"""Preview-only guarded templates in Chromium; fictional states, all network blocked."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "home_starter/server"))
sys.path.insert(0, str(ROOT / "tests"))
from homestarter.panel_preview import prepare, verify  # noqa: E402
from test_panel_preview import example  # noqa: E402

generated = example()
source = generated["config"]
# Exercise non-native DOM consumers and direct stale callbacks as well as real templates.
source["button_card_templates"]["probe"] = {
    "custom_fields": {
        "probe": """[[[
try{hass.callService('climate','turn_off',{})}catch{}
try{hass.callWS({type:'call_service'})}catch{}
try{fetch('/api/camera_proxy/camera.fixture')}catch{}
const mutate=()=>hass.callService('climate','turn_off',{});
const markup='<form action="/mutate"><input autofocus><button data-command="toggle">Control</button></form>'+
'<img src="/api/camera_proxy/camera.fixture" srcset="/camera 2x"><video src="/camera"></video>'+
'<ha-camera-stream camera-entity="camera.fixture"></ha-camera-stream><a href="/lovelace/0">Exit</a>'+
'<a href="/home-starter-example-panel/home">House</a><div style="background:url(/api/camera_proxy/camera.fixture)">Hidden image</div>';
return html`<div @click=${mutate} @change=${mutate} @submit=${mutate} @keydown=${mutate}
.innerHTML=${markup}></div>`;
]]]"""
    }
}
prepared = prepare(source, generated["url_path"])
verify(prepared, source, generated["url_path"])

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    requests = []
    page.route("**/*", lambda route: (requests.append(route.request.url), route.abort()))
    page.set_content('<main id="root"></main>')
    result = page.evaluate(
        r"""prepared=>{
 const config=prepared.config,events=[],calls=[],navigation=[];
 window.fetch=(...args)=>{calls.push(['fetch',...args]);throw Error('Unexpected network');};
 const hass={states:{
 'climate.example':{state:'cool',attributes:{current_temperature:21.5,temperature:22,supported_features:393,entity_picture:'/api/camera_proxy/camera.fixture'}}},
 services:{climate:{set_temperature:{}}},user:{name:'Fixture',id:'fixture'},config:{time_zone:'Australia/Sydney'},locale:{language:'en'},callService:(...args)=>calls.push(args),callWS:(...args)=>calls.push(args)};
 const html=(strings,...values)=>({markup:values.findLast(v=>typeof v==='string') || '',
 events:values.map((v,i)=>({prefix:strings[i],value:v})).filter(row=>typeof row.value==='function' || row.value?.handleEvent)});
 const render=(script,variables)=>{
  if(typeof script!=='string' || !script.startsWith('[[['))return;
  const code=script.replace(/^\[+/,'').replace(/\]+$/,'');
  const host={style:{setProperty(){}},requestUpdate(){}};
  const result=new Function('hass','variables','html','helpers','fetch',code).call(host,hass,variables,html,{runAction:a=>navigation.push(a)},window.fetch);
  const root=document.getElementById('root');root.innerHTML=typeof result==='string' ? result:result?.markup || '';
  if(root.querySelector('img,video,audio,iframe,ha-camera-stream,[src],[srcset],[autofocus]'))throw Error('A network consumer survived');
  if([...root.querySelectorAll('button,input,select')].some(el=>!el.disabled))throw Error('An active control survived');
  if([...root.querySelectorAll('a[href]')].some(el=>!prepared.review.routes.includes(el.getAttribute('href'))))throw Error('An escape link survived');
  for(const row of result?.events || []){
   const type=(row.prefix.match(/@(\w+)=$/) || [,'click'])[1];
   const handler=typeof row.value==='function' ? row.value:row.value.handleEvent;
   root.addEventListener(type,handler,{once:true});
   for(let repeat=0;repeat<3;repeat++){
    const target=root.querySelector('button,input,a') || root;
    target.dispatchEvent(new Event(type,{bubbles:true,cancelable:true}));
   }
   events.push(type);
  }
  // Keyboard activation must not make disabled native HTML controls submit.
  for(const target of root.querySelectorAll('button,input,form')){
   target.click?.();target.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
  }
  return root.textContent;
 };
 const template=config.button_card_templates.home_starter_page;
 let count=0;
 for(const view of config.views){
  const card=view.cards[0],variables={...template.variables,...card.variables};
  if(variables.focus_json){
   for(const name of ['header','body','footer']){
    render(template.custom_fields[name],variables);count++;
    if(name==='footer' && !document.querySelector('#root a[href]'))throw Error('Preview navigation disappeared');
   }
  }
 }
 const home=config.views.find(v=>v.path==='home').cards[0];
 for(const value of Object.values(home.custom_fields || {}))if(typeof value==='string'){render(value,home.variables);count++;}
 // Native replacement cards are guarded too, including nested climate controls.
 const walk=node=>{
  if(Array.isArray(node)){node.forEach(walk);return;}
  if(!node || typeof node!=='object')return;
  if(node.variables?.preview_entity){for(const value of Object.values(node.custom_fields || {})){render(value,node.variables);count++;}}
  Object.values(node).forEach(walk);
 };
 walk(config.views);
 const probe=render(config.button_card_templates.probe.custom_fields.probe,{});
 if(!probe.includes('Image loading disabled in preview'))throw Error('Camera placeholder missing');
 if(calls.length)throw Error('Mutation/network facade escaped: '+JSON.stringify(calls));
 const footerVariables={...template.variables,...config.views.find(v=>v.cards[0].variables?.focus_json).cards[0].variables};
 const footerResult=new Function('hass','variables','html','helpers','fetch',template.custom_fields.footer.replace(/^\[+/,'').replace(/\]+$/,'')).call(
  {style:{setProperty(){}},requestUpdate(){}},hass,footerVariables,html,{runAction:a=>navigation.push(a)},window.fetch);
 const root=document.getElementById('root');root.innerHTML=footerResult.markup;
 for(const row of footerResult.events)if(/@click=$/.test(row.prefix))root.addEventListener('click',row.value);
 window.previewNavigation=navigation;
 root.querySelector('a[href]').focus();
 return {count,events:events.length,calls:calls.length,navigation:navigation.length};
} """,
        prepared,
    )
    before_keyboard = result["navigation"]
    page.keyboard.press("Enter")
    assert page.evaluate("window.previewNavigation.length") > before_keyboard
    page.wait_for_timeout(100)
    assert not requests, "Preview attempted a browser network request"
    assert result["count"] > 10 and result["events"] > 10
    browser.close()
print("View-only preview browser checks passed:", json.dumps(result), "all requests blocked; synthetic only.")
