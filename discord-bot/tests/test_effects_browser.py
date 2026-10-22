"""Damage and healing as numbers rising over the bars, whatever caused them, and the boss's status effects as icons."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from test_activity_gm_browser import run  # noqa: E402


def test_the_boss_losing_life_shows_the_number_and_its_burn_shows_as_an_icon():
    async def scenario(rig, browser, url):
        rig.app.active_boss = {"name": "Rey", "hp_current": 900, "hp_max": 1000}
        page = await open_page(browser, url, name="Luis")
        await rig.bridge.push_state()
        await page.wait_for_selector("[data-testid=boss]")
        rig.app.active_boss["hp_current"] = 820
        rig.app.boss_status_effects = {"Rey": {"burn": {"stacks": 1, "end_time": time.time() + 10}}}
        await rig.bridge.push_state()
        await page.wait_for_selector("[data-testid=boss] .hp-pop.dmg")
        assert (await page.locator("[data-testid=boss] .hp-pop").first.inner_text()).strip() == "-80"
        assert "🔥" in await page.locator("[data-testid=boss] .effect-icons").inner_text()
        assert page.errors == []

    run(scenario)
