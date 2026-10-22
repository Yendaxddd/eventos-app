"""Mini enemies in a real (headless) Chromium: the game master fills the bestiary and sends them in; players see them and hit them."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from test_activity_gm_browser import gm_page, run, until, wait_toast  # noqa: E402
from test_gm_deck_browser import gm_event_page  # noqa: E402


def test_a_game_master_makes_an_enemy_sends_it_in_and_a_player_beats_it():
    async def scenario(rig, browser, url):
        rig.app.power_charges = {}
        gm = await gm_page(browser, url, tab="mobs", width=1200, height=1000)
        await gm.click("[data-testid=mob-new]")
        await gm.fill("[data-testid=mob-name]", "Rata gigante")
        await gm.fill("[data-testid=mob-hp]", "15")
        await gm.fill("[data-testid=mob-every]", "600")
        await gm.fill("[data-testid=mob-charge]", "30")
        await gm.click("[data-testid=mob-attack-mash]")
        assert "15 PV" in await gm.locator("[data-testid=mob-editor]").inner_text()
        await gm.click("[data-testid=mob-save]")
        await gm.wait_for_selector("[data-testid=mob-template]")
        template = next(iter(rig.bridge.mobs.bestiary.items.values()))
        assert template["name"] == "Rata gigante" and template["attack"] == "mash" and template["hp"] == 15

        player = await open_page(browser, url, name="Luis", width=420, height=800)
        assert await player.locator("[data-testid=mob]").count() == 0
        await gm.click("[data-testid=mob-spawn]")
        await player.wait_for_selector("[data-testid=mob]")
        await gm.wait_for_selector("[data-testid=mob-live]")
        card = player.locator("[data-testid=mob]")
        assert "Rata gigante" in await card.inner_text() and "15/15" in await card.inner_text()
        await card.click()
        await player.wait_for_selector(".mob-dmg")
        await until(lambda: next(iter(rig.bridge.mobs.live.values()))["hp"] == 5, "the first hit")
        await player.wait_for_function("document.querySelector('[data-testid=mob]').innerText.includes('5/15')")
        await player.wait_for_selector("[data-testid=mob].cooling", state="detached", timeout=4000)     # one hit every two seconds
        await card.click()                                                       # the last blow: it falls and gives charge
        await player.wait_for_selector("[data-testid=mob]", state="detached")
        await wait_toast(player, "Derrotaste a Rata gigante")
        uid = next(u for u in rig.app.power_charges)
        assert rig.app.power_charges[uid]["power1"] == 30
        await gm.wait_for_selector("[data-testid=mob-live]", state="detached")
        assert gm.errors == [] and player.errors == []

    run(scenario)


def test_the_deck_sends_enemies_in_and_pauses_them():
    async def scenario(rig, browser, url):
        rig.bridge.mobs.bestiary.put({"name": "Lobo", "hp": 50, "every": 600})
        page = await gm_event_page(browser, url, width=1100, height=1300)
        await page.wait_for_selector("[data-testid=deck-mob-spawn]")
        await page.click("[data-testid=deck-mob-spawn]")
        await page.wait_for_selector("[data-testid=mob]")
        await page.click("[data-testid=deck-mob-pause]")
        await until(lambda: rig.bridge.mobs.paused, "the pause")
        await page.wait_for_function("document.querySelector('[data-testid=mob]').innerText.includes('en pausa')")
        await page.click("[data-testid=deck-mob-clear]")
        await page.click("[data-testid=deck-mob-clear-yes]")
        await page.wait_for_selector("[data-testid=mob]", state="detached")
        assert rig.bridge.mobs.live == {} and page.errors == []

    run(scenario)
