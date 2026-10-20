"""Render generated fictional touch surfaces; decorations never overlap copy or taps."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "home_starter/server"), str(ROOT / "tests")]
from homestarter.surfaces import generate  # noqa: E402
from test_panel import fixture  # noqa: E402


def main():
    house, surface, items, areas = fixture()
    generated = generate(house, surface, items, areas, policy={"landscape_panel": True})
    config = generated["config"]
    overview = config["views"][0]["cards"][0]
    template = config["button_card_templates"]["home_starter_page"]
    person = next(v["cards"][0] for v in config["views"] if v["path"] == "person-" + b"example".hex())
    output = ROOT / ".runtime/wall-reference-review"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in ((1280, 800), (390, 844)):
            page = browser.new_page(viewport={"width": width, "height": height})
            for name, root, variables, selector in (
                ("overview", overview, overview["variables"], ".hs-tile.hs-media"),
                ("person", template, {**template["variables"], **person["variables"]}, ".hs-person-summary"),
            ):
                page.set_content("<style>body{margin:0;background:#0b1013}</style><div id='card'><div id='fixture'></div></div>")
                page.add_style_tag(content=root["extra_styles"].replace(":host", ":root"))
                page.evaluate(
                    """({source,variables})=>{
                    const render=new Function('hass','variables','html','window','helpers',source);
                    const html=(strings,...values)=>({markup:values.findLast(v=>typeof v==='string')});
                    const hass={states:{},connected:true,services:{},user:{},config:{time_zone:'Australia/Sydney'},locale:{language:'en-AU'}};
                    const result=render.call(document.querySelector('#fixture'),hass,variables,html,window,{runAction(){}});
                    document.querySelector('#fixture').innerHTML=result.markup;
                }""",
                    {"source": root["custom_fields"].get("body", root["custom_fields"].get("panel", ""))[3:-3], "variables": variables},
                )
                card = page.locator(selector)
                assert card.count() == 1
                geometry = card.evaluate("""card=>{
                    const s=getComputedStyle(card,'::after'),r=card.getBoundingClientRect();
                    const w=parseFloat(s.width),h=parseFloat(s.height),right=r.right-parseFloat(s.right);
                    const top=s.top==='auto'?r.bottom-parseFloat(s.bottom)-h:r.top+parseFloat(s.top);
                    const egg={left:right-w,right,top,bottom:top+h};
                    const overlaps=[...card.querySelectorAll('h2,h3,p,a,.hs-tile-copy')].some(e=>{
                      const b=e.getBoundingClientRect();return b.width&&b.height&&b.left<egg.right&&b.right>egg.left&&b.top<egg.bottom&&b.bottom>egg.top;});
                    return {overlaps,asset:s.backgroundImage.includes('data:image/webp;base64,'),pointer:s.pointerEvents,
                      inside:egg.left>=r.left&&egg.right<=r.right&&egg.top>=r.top&&egg.bottom<=r.bottom};
                }""")
                assert geometry == {"overlaps": False, "asset": True, "pointer": "none", "inside": True}, (name, width, geometry)
                page.screenshot(path=str(output / f"decor-{name}-{width}.png"))
                print(f"{name} {width}: local discovery visible, contained and clear of copy/controls")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
