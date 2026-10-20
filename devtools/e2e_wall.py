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
                if name == "school_unavailable":
                    assert wall.locator(".wall-family").get_attribute("data-incomplete") == "true"
                    assert wall.locator(".wall-school-child").count() == 3
                    assert not wall.locator(".wall-camera-status").count()
                    assert wall.locator(".wall-source-note").is_visible()
                    assert wall.locator(".wall-family-card").evaluate_all("nodes=>nodes.every(e=>e.clientHeight<320&&e.clientWidth<500)")
                    assert "School today" not in wall.inner_text()
                for region in (".wall-weather", ".wall-household", ".wall-bottom"):
                    assert wall.locator(region).is_visible(), (name, region)
                labels_inline = wall.locator(".wall-temperature").evaluate_all(
                    """nodes=>nodes.every(e=>{const number=e.firstElementChild.getBoundingClientRect(),label=e.lastElementChild.getBoundingClientRect();
                    return label.left>=number.right&&label.top<number.bottom&&label.bottom>number.top;})"""
                )
                assert labels_inline, (name, width, "temperature label stacked below number")
                label_tops = wall.locator(".wall-temperature small").evaluate_all("nodes=>nodes.map(e=>e.getBoundingClientRect().top)")
                assert not label_tops or max(label_tops) - min(label_tops) < 2, (name, width, "weather labels have different baselines")
                sizes = wall.locator(".wall-temperature > :first-child").evaluate_all("nodes=>nodes.map(e=>getComputedStyle(e).fontSize)")
                assert len(set(sizes)) <= 1, (name, width, "forecast temperature demoted")
                assert not wall.locator(
                    ".wall-family-card:not(:has(.wall-card-fact,.wall-school-periods,.wall-school-fallback,.wall-school-rules,.wall-night-summary,.wall-night-rule))"
                ).count(), (
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
                if name in ("school_sunday", "school_sunday_late", "school_monday", "school_monday_night"):
                    night = name in ("school_sunday_late", "school_monday_night")
                    if night:
                        assert wall.get_attribute("data-night") == "true"
                        assert not wall.locator(".wall-family,.wall-agenda,.wall-school-periods,.wall-week").count()
                    else:
                        assert wall.locator(".wall-school-child").count() == 3
                        school_row = wall.locator(".wall-timeline .wall-line-item").filter(has=page.get_by_role("heading", name="School", exact=True))
                        assert school_row.count() >= 1 and "Casey" in school_row.all_inner_texts()[0]
                        assert wall.locator(".wall-school-periods li").evaluate_all("nodes=>nodes.reduce((n,e)=>n+Number(e.dataset.periodCount),0)") == 21
                        assert wall.locator(".wall-family .wall-avatar").count() == 3
                        assert wall.locator(".wall-family").get_attribute("aria-label") == ("Today" if name == "school_monday" else "Tomorrow") + " at school"
                        upcoming = wall.locator(".wall-upcoming")
                        if upcoming.count():
                            assert upcoming.bounding_box()["y"] > wall.locator(".wall-timeline").bounding_box()["y"]
                if name in (
                    "school_sunday",
                    "school_sunday_late",
                    "school_monday",
                    "school_monday_night",
                    "quiet_sunday",
                    "sunday_evening",
                    "canonical_weekday",
                    "canonical_evening",
                ):
                    page.screenshot(path=str(output / (name + "-" + str(width) + ".png")))
                print(f"{name} {width}x{height}: ambient anchors, no empty islands, borders, clipping or overlapping times")
            page.goto((source / "canonical_weekday.html").as_uri())
            fitted = page.evaluate("""async()=>{
                const host=document.querySelector('home-starter-ambient-wall'),panel=host.querySelector('.wall-timeline');
                panel.querySelector(':scope > ol').innerHTML='';
                let future=panel.querySelector('.wall-upcoming');
                if(!future){future=document.createElement('div');future.className='wall-upcoming';panel.append(future);}
                future.innerHTML=Array.from({length:18},(_,n)=>`<section class="wall-upcoming-day"><h3>Day ${n+1}</h3>
                  <ol><li class="wall-upcoming-row"><span class="wall-dot"></span><time>9:00</time><p>Activity ${n+1}</p></li></ol></section>`).join('');
                const fit=async()=>{host._fitAgenda();await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);};
                await fit();
                const count=()=>[...future.querySelectorAll('li')].filter(e=>!e.hidden).length;
                const full=count(),last=[...future.querySelectorAll('li')].filter(e=>!e.hidden).at(-1);
                const inside=last.getBoundingClientRect().bottom<=panel.getBoundingClientRect().bottom;
                panel.style.maxHeight='350px';await fit();const compact=count();
                panel.style.maxHeight='';await fit();
                return {full,compact,restored:count(),inside};
            }""")
            assert fitted["full"] > 6 and fitted["compact"] < fitted["full"], (width, fitted)
            assert fitted["restored"] == fitted["full"] and fitted["inside"], (width, fitted)
            print(f"Measured agenda {width}: {fitted['full']} future days fit; resize restores full rows without clipping")
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
