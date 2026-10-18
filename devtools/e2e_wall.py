"""Isolated wall sizing acceptance; fictional plans never leave the local browser."""

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "home_starter/server"))
from wall_scenarios import SCENARIOS  # noqa: E402


def main():
    subprocess.run([sys.executable, str(ROOT / "devtools/wall_fixtures.py")], cwd=ROOT, check=True)  # noqa: S603
    source = ROOT / ".runtime/wall-adaptive-fixtures"
    output = ROOT / ".runtime/wall-ambient-review"
    output.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in ((1920, 1080), (1366, 768)):
            page = browser.new_page(viewport={"width": width, "height": height})
            reference_boxes = None
            for name in SCENARIOS:
                page.goto((source / (name + ".html")).as_uri())
                wall = page.locator(".hs-wall")
                assert wall.is_visible(), name
                failures = wall.evaluate(
                    """root=>[...root.querySelectorAll('.wall-header,.wall-family,.wall-family-card,.wall-surface,.wall-school,.wall-week')]
                    .filter(e=>e.clientWidth&&e.clientHeight&&(e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1))
                    .map(e=>e.className)"""
                )
                assert not failures, (name, width, failures)
                for region in (".wall-weather", ".wall-household", ".wall-bottom"):
                    assert wall.locator(region).is_visible(), (name, region)
                assert not wall.locator(".wall-family-card:not(:has(.wall-card-fact,.wall-school-periods,.wall-school-fallback,.wall-school-rules))").count(), (
                    name,
                    "empty information island",
                )
                assert not wall.locator(".wall-surface:not(.wall-household):not(.wall-camera-status):not(:has(.wall-line-item,.wall-week-row))").count(), (
                    name,
                    "empty timeline island",
                )
                borders = wall.locator(".wall-family-card,.wall-surface").evaluate_all("nodes=>nodes.some(e=>parseFloat(getComputedStyle(e).borderTopWidth)>0)")
                assert not borders, (name, "visible fixed card border")
                overlap = wall.locator(".wall-line-item").evaluate_all(
                    """rows=>rows.some(e=>e.querySelector('time').getBoundingClientRect().right>
                    e.querySelector('.wall-dot').getBoundingClientRect().left)"""
                )
                assert not overlap, (name, width, "overlapping event time")
                boxes = wall.locator(".wall-header,.wall-family,.wall-agenda,.wall-bottom").evaluate_all(
                    "nodes=>nodes.map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})"
                )
                if name == "canonical_weekday":
                    reference_boxes = boxes
                    assert wall.locator('.wall-family-card[data-kind="person"]').count() == 3
                    assert wall.locator(".wall-family").get_by_text("Sports kit + hat", exact=True).is_visible()
                    assert wall.locator(".wall-family").get_by_text("Leave 8:30", exact=True).count() == 3
                if name == "canonical_evening":
                    assert wall.get_attribute("data-mode") == "tomorrow_preview"
                    assert wall.locator('.wall-family-card[data-kind="person"]').count() == 3
                    assert wall.locator(".wall-timeline h2").inner_text() == "Tomorrow"
                    assert abs(boxes[1][0] - reference_boxes[1][0]) < 1 and abs(boxes[1][1] - reference_boxes[1][1]) < 70
                if name in ("school_sunday", "school_monday"):
                    assert wall.locator(".wall-school-child").count() == 3
                    assert wall.locator(".wall-school-periods li").count() == 18
                    assert wall.locator(".wall-school-periods li").evaluate_all("nodes=>nodes.reduce((n,e)=>n+Number(e.dataset.periodCount),0)") == 21
                    assert wall.locator(".wall-agenda .wall-week-row").count() >= 4
                    assert wall.locator(".wall-family-card").count() == 3
                    assert wall.locator(".wall-family .wall-avatar").count() == 3
                    assert not wall.locator(".wall-family .wall-week").count()
                    assert wall.locator(".wall-family").get_attribute("aria-label") == ("Tomorrow" if name == "school_sunday" else "Today") + " at school"
                    primary = wall.locator(".wall-timeline").bounding_box()
                    secondary = wall.locator(".wall-week").bounding_box()
                    assert abs(primary["x"] - secondary["x"]) < 1 and secondary["y"] > primary["y"]
                if name in ("school_sunday", "school_monday", "quiet_sunday", "sunday_evening", "canonical_weekday", "canonical_evening"):
                    page.screenshot(path=str(output / (name + "-" + str(width) + ".png")))
                print(f"{name} {width}x{height}: ambient anchors, no empty islands, borders, clipping or overlapping times")
            if width == 1920:
                page.goto((source / "canonical_evening.html").as_uri())
                result = page.evaluate("""async()=>{
                    const body=document.querySelector('.hs-wall').outerHTML;
                    const host=document.createElement('home-starter-ambient-wall');
                    document.body.replaceChildren(host);host.content=body;
                    const template=document.createElement('template');template.innerHTML=body;
                    template.content.querySelector('.wall-family-card').remove();
                    const next=template.content.querySelector('.hs-wall').outerHTML;
                    host.content=next;await host._transition?.finished;
                    const remaining=host.querySelectorAll('.wall-family-card').length;
                    host.content='<main class="hs-wall" data-fresh="false"><p>Household context unavailable</p></main>';
                    return {remaining,cleared:!host.textContent.includes('Casey')&&!host.textContent.includes('Jordan')};
                }""")
                assert result == {"remaining": 2, "cleared": True}, result
                print("Native ambient component: island expiry reflows, stale private content clears immediately")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
