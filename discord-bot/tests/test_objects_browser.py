"""The game master's object editor in a real (headless) Chromium: a new object from the form, with its steps, and given to a player."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from test_activity_gm import OTHER  # noqa: E402
from test_activity_gm_browser import gm_page, run, until  # noqa: E402


def test_a_game_master_creates_an_object_with_steps_and_gives_it_to_a_player():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url, tab="data", width=1200, height=1100)
        await page.click("[data-testid=gm-section-objects]")
        await page.click("[data-testid=gm-obj-new]")
        await page.wait_for_selector("[data-testid=obj-form]")
        await page.fill("[data-testid=obj-name]", "Hoja lunar")
        await page.fill("[data-testid=obj-id]", "hoja_lunar")
        await page.fill("[data-testid=obj-description]", "Corta la noche.")
        await page.click("[data-testid=obj-steps-add]")
        await page.click("[data-testid=obj-steps-add-effect-0]")
        await page.select_option("[data-testid=obj-steps-effect-0-0]", "guaranteed_counter")
        await page.click("[data-testid=obj-save]")
        await until(lambda: "hoja_lunar" in rig.app.special_objects_manager.objects, "the new object")
        obj = rig.app.special_objects_manager.objects["hoja_lunar"]
        assert obj["name"] == "Hoja lunar" and obj["thresholds"] == [{"spins": 5, "effects": ["guaranteed_counter"]}]
        await page.wait_for_selector("[data-testid=obj-form]", state="detached")
        await page.click("[data-testid=gm-approved-form-hoja_lunar]")
        await page.wait_for_selector("[data-testid=obj-owners]")
        await page.select_option("[data-testid=obj-give-to]", str(OTHER))
        await page.click("[data-testid=obj-give]")
        await until(lambda: "hoja_lunar" in rig.app.special_objects_manager.player_inventory.get(OTHER, []), "the object to be given")
        assert "Mina" in await page.locator("[data-testid=obj-owners]").inner_text()
        assert page.errors == []

    run(scenario)
