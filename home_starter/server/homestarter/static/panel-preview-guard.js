// Preview-only execution facade. Production templates do not load this file.
// This prevents UI side effects; it does not change the signed-in user's HA rights.
const previewPaths = new Set(PREVIEW_PATHS);
const previewDenied = () => { throw Error("Controls are disabled in this view-only preview."); };
const previewStates = Object.fromEntries(Object.entries(hass.states || {}).map(([id,s])=>[id,{state:s.state,attributes:Object.fromEntries(Object.entries(s.attributes || {}).filter(([key])=>!/(picture|image|url|token|stream)/i.test(key)))}]));
const previewHass = {states:previewStates,config:{time_zone:hass.config.time_zone},locale:{language:hass.locale?.language},user:{id:hass.user?.id,name:hass.user?.name,is_admin:hass.user?.is_admin},services:{},callService:previewDenied,callWS:previewDenied};
const previewHelpers = {runAction:action=>{
 if(action?.action === "navigate" && previewPaths.has(action.navigation_path)) helpers.runAction({action:"navigate",navigation_path:action.navigation_path});
}};
const previewNavigate = event => {
 event.preventDefault();event.stopPropagation();
 const path=event.target.closest?.("a[href]")?.getAttribute("href");
 if(previewPaths.has(path))previewHelpers.runAction({action:"navigate",navigation_path:path});
};
const previewStop = event => {event.preventDefault();event.stopPropagation();};
const previewMarkup = markup => {
 const template=document.createElement("template");template.innerHTML=markup;
 // No custom elements can introduce their own actions or network consumers.
 for(const el of template.content.querySelectorAll("*")) {
  if(!el.parentNode)continue;
  if(!["HA-ICON","DIV","SPAN","P","SECTION","ARTICLE","ASIDE","HEADER","FOOTER","NAV","H1","H2","H3","H4","TIME","STRONG","EM","SMALL","LABEL","A","BUTTON","INPUT","SELECT","OPTION","FORM","BR","UL","LI"].includes(el.tagName)){el.replaceWith(document.createTextNode(el.tagName==="IMG" ? "Image loading disabled in preview":""));continue;}
  for(const attribute of [...el.attributes]) {
   if(attribute.name.startsWith("on") || ["src","srcset","action","formaction","target","ping","is","autofocus"].includes(attribute.name) || attribute.name.startsWith("data-"))el.removeAttribute(attribute.name);
   if(attribute.name==="style" && /url\s*\(|image-set\s*\(|@import/i.test(attribute.value))el.removeAttribute("style");
  }
  if(el.tagName==="A" && !previewPaths.has(el.getAttribute("href")))el.removeAttribute("href");
  if(["BUTTON","INPUT","SELECT","OPTION"].includes(el.tagName)){el.disabled=true;el.setAttribute("aria-disabled","true");}
  if(el.tagName==="FORM")el.setAttribute("inert","");
 }
 for(const paragraph of template.content.querySelectorAll("p"))if(paragraph.textContent==="Camera image unavailable")paragraph.textContent="Camera image loading disabled in preview";
 if(template.content.querySelector(".hs-header,.hs-panel")) {
  const notice=document.createElement("aside");notice.textContent="View-only preview · controls disabled";
  notice.setAttribute("role","note");notice.style.cssText="position:fixed;top:58px;right:12px;z-index:1000;padding:6px 10px;background:#18232b;color:#fff;border-radius:8px;pointer-events:none;font-size:13px";
  template.content.append(notice);
 }
 return template.innerHTML;
};
const previewHTML = (strings,...values) => html(strings,...values.map((value,index)=>typeof value==="string" ? previewMarkup(value):typeof value==="function" ? (/@click=$/.test(strings[index]) ? previewNavigate:previewStop):value && typeof value.handleEvent==="function" ? {handleEvent:previewStop,capture:true}:value));
const previewVariables=JSON.parse(JSON.stringify(variables));
if(previewVariables.common_json){const common=JSON.parse(previewVariables.common_json);common.music_backend=null;previewVariables.common_json=JSON.stringify(common);}
