"""Getting around the Activity in a real (headless) Chromium: the bottom bar on a phone, the top shortcuts on a computer, «Ir a…» with the
keyboard, and the focus landing on each new page."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from test_activity_gm_browser import run  # noqa: E402


def test_a_phone_gets_a_bottom_bar_that_reaches_the_main_places_and_marks_where_you_are():
    async def scenario(rig, browser, url):
        page = await open_page(browser, url, name="Luis", width=390, height=800, mobile=True)
        await page.wait_for_selector("[data-testid=bottom-nav]")
        assert await page.locator("[data-testid=nav-gm]").count() == 0                     # a player has no GM item
        assert await page.locator("[data-testid=nav-event]").get_attribute("aria-current") == "page"
        await page.click("[data-testid=nav-panel]")
        await page.wait_for_selector("[data-testid=panel]")
        assert await page.locator("[data-testid=nav-panel]").get_attribute("aria-current") == "page"
        await page.click("[data-testid=nav-training]")
        await page.wait_for_function("window.__eventos.view === 'training'")
        await page.click("[data-testid=nav-more]")
        await page.wait_for_selector("[data-testid=tile-settings]")
        # the new page's title has the focus (keyboard and screen readers start there)
        assert await page.evaluate("document.activeElement.tagName") == "H1"
        await page.click("[data-testid=nav-event]")
        await page.wait_for_selector("[data-testid=composer]")
        gm = await open_page(browser, url, name="Gus", extra="&gm=1", width=390, height=800, mobile=True)
        await gm.click("[data-testid=nav-gm]")
        await gm.wait_for_selector("[data-testid=gm]")
        assert page.errors == [] and gm.errors == []

    run(scenario)


def test_on_a_computer_the_top_bar_and_ir_a_reach_any_page_and_gm_tab_with_the_keyboard():
    async def scenario(rig, browser, url):
        page = await open_page(browser, url, name="Gus", extra="&gm=1", width=1280, height=760)
        assert await page.locator("[data-testid=bottom-nav]").count() == 0
        await page.click("[data-testid=topnav-panel]")
        await page.wait_for_selector("[data-testid=panel]")
        await page.keyboard.press("Control+k")
        await page.keyboard.type("enemigos")
        await page.keyboard.press("Enter")
        await page.wait_for_selector("[data-testid=gm-mobs]")
        await page.keyboard.press("Control+k")
        await page.keyboard.type("latencia")
        await page.keyboard.press("Enter")
        await page.wait_for_function("window.__eventos.view === 'latency'")
        await page.click("[data-testid=open-palette]")
        await page.keyboard.type("zzz")
        assert "Nada con ese nombre" in await page.locator("[data-testid=palette]").inner_text()
        await page.keyboard.press("Escape")
        await page.wait_for_selector("[data-testid=palette]", state="detached")
        player = await open_page(browser, url, name="Luis", width=1280, height=760)
        await player.keyboard.press("Control+k")
        await player.keyboard.type("jefe")
        assert "GM" not in await player.locator("[data-testid=palette]").inner_text()           # a player is not offered the GM's places
        assert page.errors == [] and player.errors == []

    run(scenario)
