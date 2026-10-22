"""A power's picture fills the screen when it is used: on every screen, or only on its user's (the power's «who sees it»)."""
import asyncio
import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import PIXEL, WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from test_activity_gm_browser import run  # noqa: E402


def test_the_picture_of_a_power_shows_for_everybody_or_only_for_who_used_it():
    async def scenario(rig, browser, url):
        user = await open_page(browser, url, name="Luis")
        other = await open_page(browser, url, name="Ana")
        pic = "data:image/png;base64," + base64.b64encode(PIXEL).decode()
        rig.app.character_powers = {"Kuro": {"power1": {"name": "Corte", "type": "destructive", "image_url": pic, "show": "all"},
                                             "power2": {"name": "Calma", "type": "support", "image_url": pic, "show": "self"}}}
        rig.bridge.on_event("power_used", {"user": int(user.me), "character": "Kuro", "slot": 1})
        await user.wait_for_selector("[data-testid=power-show]")
        await other.wait_for_selector("[data-testid=power-show]")
        assert "Corte" in await other.locator("[data-testid=power-show]").inner_text()
        await other.wait_for_selector("[data-testid=power-show]", state="detached", timeout=5000)
        rig.bridge.on_event("power_used", {"user": int(user.me), "character": "Kuro", "slot": 2})
        await user.wait_for_selector("[data-testid=power-show]")
        await asyncio.sleep(0.4)
        assert await other.locator("[data-testid=power-show]").count() == 0
        assert user.errors == [] and other.errors == []

    run(scenario)
