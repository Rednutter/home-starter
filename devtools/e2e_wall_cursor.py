"""Kiosk cursor coverage across HA-like shadow roots, reload and interactive routes."""

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

MOUNT = """() => {
 const body=document.querySelector('.hs-wall').outerHTML;
 document.body.innerHTML='<div id="root"><div id="app"></div></div>';
 document.body.style.cursor='default';
 const shell=document.createElement('div');document.querySelector('#app').append(shell);
 const shadow=shell.attachShadow({mode:'open'});
 shadow.innerHTML='<a href="#">Interactive link</a><button style="cursor:pointer">Button</button>';
 const host=document.createElement('home-starter-ambient-wall');shadow.append(host);host.content=body;
 window.cursorTestHost=host;
 const nested=document.createElement('div');shadow.append(nested);
 nested.attachShadow({mode:'open'}).innerHTML='<style>a:hover{cursor:pointer}button{cursor:default}</style>'
  +'<a href="#">Nested link</a><button>Nested button</button>';
} """

INSPECT = """() => {
 const cursors=[],styles=[];
 function visit(root){
  styles.push(...root.querySelectorAll('[data-home-starter-wall-cursor]'));
  for(const element of root.querySelectorAll('*')){
   if(!['STYLE','SCRIPT','META','TITLE','HEAD'].includes(element.tagName))cursors.push(getComputedStyle(element).cursor);
   if(element.shadowRoot)visit(element.shadowRoot);
  }
 }
 visit(document);return {bad:cursors.filter(c=>c!=='none'),count:cursors.length,styles:styles.length};
} """


def main():
    subprocess.run([sys.executable, str(ROOT / "devtools/wall_fixtures.py")], check=True, cwd=ROOT)  # noqa: S603
    html = (ROOT / ".runtime/wall-adaptive-fixtures/school_sunday.html").read_text(encoding="utf-8")
    # The fixture puts wall CSS in document.head; native HA confines it to the
    # button-card shadow root. Keep fixture-local CSS local for this scope test.
    html = html.replace(":host,html,body,#root,#app,* { cursor:none !important; }", ".hs-wall,.hs-wall * { cursor:none !important; }")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.route("http://wall.test/**", lambda route: route.fulfill(body=html, content_type="text/html"))
        for attempt in range(2):
            page.goto("http://wall.test/home-starter-example_wall/home?kiosk") if not attempt else page.reload()
            page.evaluate(MOUNT)
            page.wait_for_function("(" + INSPECT + ")().styles >= 3")
            for x, y in ((1, 1), (1800, 20), (700, 200), (400, 600), (1700, 800), (10, 1070)):
                page.mouse.move(x, y)
                result = page.evaluate(INSPECT)
                assert result["count"] > 100 and result["styles"] >= 3 and not result["bad"], result
            print("Kiosk cursor: html/body, wall, links/buttons and nested/dynamic shadow roots remain none after pointer motion/reload")
        for route in ("example_tablet", "example_phone"):
            page.evaluate("path=>{history.pushState({},'',path);dispatchEvent(new Event('location-changed'));}", "/home-starter-" + route + "/home?kiosk")
            assert page.evaluate(INSPECT)["styles"] == 0
            assert page.evaluate("getComputedStyle(document.body).cursor") == "default"
            assert page.locator("button").first.evaluate("e=>getComputedStyle(e).cursor") == "pointer"
        page.evaluate("history.pushState({},'','/home-starter-example_wall/home?kiosk');dispatchEvent(new Event('location-changed'))")
        assert not page.evaluate(INSPECT)["bad"]
        page.evaluate("history.pushState({},'','/home-starter-example_wall/home?kiosk&disable_km');dispatchEvent(new Event('location-changed'))")
        assert page.evaluate(INSPECT)["styles"] == 0
        page.evaluate("history.pushState({},'','/home-starter-example_wall/home?kiosk');dispatchEvent(new Event('location-changed'));cursorTestHost.remove()")
        assert page.evaluate(INSPECT)["styles"] == 0
        print("Interactive phone/tablet routes, kiosk escape and detached wall: original cursor styles restored")
        browser.close()


if __name__ == "__main__":
    main()
