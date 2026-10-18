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
    output = ROOT / ".runtime/wall-weekday-review"
    output.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in ((1920, 1080), (1366, 768)):
            page = browser.new_page(viewport={"width": width, "height": height})
            for name in SCENARIOS:
                page.goto((source / (name + ".html")).as_uri())
                wall = page.locator(".hs-wall")
                assert wall.is_visible(), name
                failures = wall.evaluate(
                    """root=>[...root.querySelectorAll('.wall-board,.wall-now,.wall-surface,.wall-ahead,.wall-exceptions,.wall-context')]
                    .filter(e=>e.clientWidth&&e.clientHeight&&(e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1))
                    .map(e=>e.className)"""
                )
                assert not failures, (name, width, failures)
                assert not wall.locator(".wall-today:not(:has(h3)):not(:has(.wall-today-summary))").count(), (name, "empty Today")
                overlap = wall.locator(".wall-item:not(.wall-item-note)").evaluate_all(
                    """rows=>rows.some(e=>e.querySelector('time').getBoundingClientRect().right>
                    e.querySelector('div').getBoundingClientRect().left)"""
                )
                assert not overlap, (name, width, "overlapping event time")
                if name == "busy_school_morning":
                    assert wall.locator(".wall-now").bounding_box()["width"] > width * 0.9
                    assert wall.get_by_text("Sports kit and hat", exact=True).is_visible()
                    assert wall.get_by_text("Training", exact=True).is_visible()
                    assert wall.get_by_text("Leave by 08:30", exact=True).is_visible()
                if name in ("quiet_sunday", "sunday_evening", "busy_school_morning", "weekday_morning_horizon"):
                    page.screenshot(path=str(output / (name + "-" + str(width) + ".png")))
                print(f"{name} {width}x{height}: readable regions, no empty Today card or overlapping times")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
