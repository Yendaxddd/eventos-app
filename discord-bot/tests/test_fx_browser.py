"""Effects of powers in a real (headless) Chromium: a game master gives a power its look in the Effects tab (it saves by itself), the power is
used, and every screen draws it; a player can soften or switch the effects off."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity.fx import FxBook  # noqa: E402
from test_activity_gm_browser import gm_page, run, until  # noqa: E402

POWER = {"Kuro": {"power1": {"name": "Corte vacío", "type": "destructive", "effect": "damage:50"}}}
USED = {"user": 1, "character": "Kuro", "slot": 1, "name": "Corte vacío", "type": "destructive", "effect": "damage:50"}


async def drawn(page):
    return await page.evaluate("window.__eventos.vfxLog.map((p) => p.k)")


def test_a_game_master_gives_a_power_its_look_and_every_screen_draws_it_when_it_is_used(tmp_path):
    async def scenario(rig, browser, url):
        rig.bridge.fx.book = FxBook(tmp_path / "fx.json")
        rig.app.character_powers = POWER
        player = await open_page(browser, url, name="Luis")
        page = await gm_page(browser, url, tab="fx")

        # by default a destructive power looks like an explosion
        await page.wait_for_selector("[data-testid=gm-fx]")
        power = "power-Kuro-1"
        assert "Por defecto: Explosión" in await page.locator(f"[data-testid=fx-sum-{power}]").inner_text()
        rig.bridge.on_event("power_used", USED)
        await until(lambda: True, "nothing")
        await player.wait_for_function("window.__eventos.vfxLog.length >= 4", timeout=3000)
        kinds = await drawn(player)
        assert "burst" in kinds and "ring" in kinds and "banner" in kinds, kinds                  # the explosion, with the power's name

        # the game master changes it: a slash, in red, with a sound-less banner; it saves by itself
        await page.click(f"[data-testid=fx-edit-{power}]")
        await page.click(f"[data-testid=fx-preset-{power}-slash]")
        await page.fill(f"[data-testid=fx-banner-{power}]", "¡Tajo!")
        await page.wait_for_selector(f"[data-testid=fx-editor-{power}] .save-state[data-state=saved]", timeout=4000)
        await until(lambda: rig.bridge.fx.book.powers.get("Kuro|1", {}).get("banner") == "¡Tajo!", "the saved look")
        assert rig.bridge.fx.book.powers["Kuro|1"]["preset"] == "slash"
        await player.evaluate("window.__eventos.vfxLog.length = 0")
        rig.bridge.on_event("power_used", USED)
        await player.wait_for_function("window.__eventos.vfxLog.length >= 3", timeout=3000)
        await player.wait_for_selector(".vfx-banner", timeout=3000)
        assert "¡tajo!" in (await player.locator(".vfx-banner").inner_text()).lower()           # drawn in capitals
        assert "slash" in await drawn(player) and "burst" not in await drawn(player)

        # an effect that does nothing is not saved, and says why
        await page.click(f"[data-testid=fx-preset-{power}-ninguno]")
        await page.fill(f"[data-testid=fx-banner-{power}]", "")
        await page.locator(f"[data-testid=fx-editor-{power}] input[type=checkbox]").uncheck()                          # no name as a banner either
        await page.wait_for_selector(f"[data-testid=fx-editor-{power}] .save-state[data-state=invalid]", timeout=3000)
        assert rig.bridge.fx.book.powers["Kuro|1"]["preset"] == "slash"

        # a player can soften the effects (no shaking) or switch them off
        await page.click(f"[data-testid=fx-preset-{power}-explosion]")
        await page.wait_for_selector(f"[data-testid=fx-editor-{power}] .save-state[data-state=saved]", timeout=4000)
        await until(lambda: rig.bridge.fx.book.powers["Kuro|1"]["preset"] == "explosion", "explosion saved")
        await player.evaluate("window.__eventos.setPrefs({ vfx: 'soft' }); window.__eventos.vfxLog.length = 0")
        rig.bridge.on_event("power_used", USED)
        await player.wait_for_function("window.__eventos.vfxLog.length >= 3", timeout=3000)
        assert "shake" not in await drawn(player)
        await player.evaluate("window.__eventos.setPrefs({ vfx: 'off' }); window.__eventos.vfxLog.length = 0")
        rig.bridge.on_event("power_used", USED)
        await asyncio.sleep(0.8)
        assert await drawn(player) == []
        assert page.errors == [] and player.errors == []

    run(scenario)
