"""Training mode in a real (headless) Chromium: random practice QTEs of the chosen kinds, answered like a player would, with a summary at the end."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page, with_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

FAST = {"kinds": ["single"], "difficulties": ["easy"], "count": 3, "gapMin": 0.3, "gapMax": 0.3, "simultaneous": 1, "speed": 100, "comboLength": 2, "suddenDeath": False}

# a player that answers whatever is on the screen correctly: the opposite arrow, otherwise whichever button is lit
PLAYER = """() => {
    const out = [];
    for (const e of window.__eventos.qtes) {
        if (!e.practice || e.pressed || e.ended) continue;
        if (e.q.mode === 'direction') {
            const opposite = { up: 'down', down: 'up', left: 'right', right: 'left' }[e.q.arrow];
            const b = document.querySelector(`.qw-pad button[data-cmd=${opposite}]:not([disabled])`);
            if (b) { b.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' })); out.push(opposite); }
        }
    }
    for (const b of document.querySelectorAll('.qw-btn:not([disabled])')) {
        b.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' })); out.push(b.dataset.cmd);
    }
    return out;
}"""


def seed(config):
    return f"localStorage.setItem('eventos.training.config', {json.dumps(json.dumps(config))});"


async def open_training(browser, url, config=None):
    page = await open_page(browser, url, width=1100, height=800, init=seed({**FAST, **(config or {})}) if config is not None else None)
    await page.click("[data-testid=menu-button]")
    await page.click("[data-testid=tile-training]")
    await page.wait_for_selector("[data-testid=training-start]")
    return page


async def play(page, until="[data-testid=training-done]", seconds=40, answer=True):
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    seen = 0
    while loop.time() < end and await page.locator(until).count() == 0:
        if answer:
            await page.evaluate(PLAYER)
        seen = max(seen, await page.locator(".qw").count())
        await asyncio.sleep(0.05)
    assert await page.locator(until).count() == 1, f"never reached {until}"
    return seen


@pytest.mark.parametrize("kind", ["single", "group", "direction", "combo", "bf_chain"])
def test_each_kind_of_practice_qte_appears_and_a_correct_player_gets_all_of_them(kind):
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"kinds": [kind]})
        await page.click("[data-testid=training-start]")
        await page.wait_for_selector("[data-testid=training-run]")
        await play(page)
        assert (await page.locator("[data-testid=sum-ok]").inner_text()).strip() == "3 / 3", kind
        assert "100" in await page.locator("[data-testid=sum-accuracy]").inner_text()
        assert hub.test_actions.pressed == []                                  # nothing reached the server
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_the_settings_pick_kinds_difficulty_and_presets_and_never_end_up_empty():
    async def scenario(hub, browser, url):
        page = await open_training(browser, url)
        on = lambda testid: page.locator(f"[data-testid={testid}]").get_attribute("aria-pressed")  # noqa: E731
        assert await on("kind-single") == "true" and await on("kind-bf_chain") == "false"
        await page.click("[data-testid=kind-bf_chain]")
        assert await on("kind-bf_chain") == "true"
        for kind in ("single", "group", "direction", "combo"):                  # turning all the others off keeps the last one
            await page.click(f"[data-testid=kind-{kind}]")
        assert await on("kind-bf_chain") == "true"
        await page.click("[data-testid=diff-medium]")
        assert await on("diff-medium") == "true"                               # the only one: it cannot be turned off
        await page.click("[data-testid=preset-chaos]")
        assert await on("kind-direction") == "true" and await on("diff-impossible") == "true" and await on("diff-easy") == "false"
        await page.click("[data-testid=preset-warmup]")
        assert await on("kind-direction") == "false" and await on("diff-easy") == "true"
        await page.click("[data-testid=training-start]")                       # what was chosen is kept for next time
        await page.wait_for_selector("[data-testid=training-run]")
        saved = json.loads(await page.evaluate("localStorage.getItem('eventos.training.config')"))
        assert saved["difficulties"] == ["easy"] and saved["count"] == 10
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_sudden_death_ends_on_the_first_miss_and_the_summary_says_what_went_wrong():
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"kinds": ["group"], "count": 0, "suddenDeath": True, "speed": 200})
        await page.click("[data-testid=training-start]")
        await play(page, answer=False)                                         # nobody answers: the first QTE runs out
        assert (await page.locator("[data-testid=sum-ok]").inner_text()).strip() == "0 / 1"
        body = await page.locator("[data-testid=training-done]").inner_text()
        assert "fallaste" in body.lower() and "sin pulsar" in body.lower() and "grupal" in body.lower()
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_stopping_early_keeps_what_was_done_and_stopping_at_once_shows_no_summary():
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"count": 0})
        await page.click("[data-testid=training-start]")
        await page.click("[data-testid=training-stop]")                        # before the first QTE: nothing to show
        await page.wait_for_selector("[data-testid=training-note]")
        assert await page.locator("[data-testid=training-done]").count() == 0
        await page.click("[data-testid=training-start]")
        loop = asyncio.get_running_loop()
        end = loop.time() + 20
        while loop.time() < end and int((await page.locator("[data-testid=stat-ok]").inner_text()).strip()) < 3:
            await page.evaluate(PLAYER)
            await asyncio.sleep(0.05)
        await page.click("[data-testid=training-stop]")
        await page.wait_for_selector("[data-testid=training-done]")
        assert int((await page.locator("[data-testid=sum-streak]").inner_text()).strip()) >= 3
        assert await page.locator("[data-testid=training-records]").count() == 1          # three in a row beat the empty records
        await page.click("[data-testid=training-settings]")
        await page.wait_for_selector("[data-testid=training-start]")
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_several_at_once_can_be_on_screen_together_and_leaving_the_page_ends_the_session():
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"simultaneous": 3, "count": 0, "gapMin": 0.3, "gapMax": 0.3})
        await page.click("[data-testid=training-start]")
        loop = asyncio.get_running_loop()
        end = loop.time() + 15
        most = 0
        while loop.time() < end and most < 2:
            most = max(most, await page.evaluate("window.__eventos.qtes.filter((e) => e.practice && !e.pressed).length"))
            await asyncio.sleep(0.05)
        assert most >= 2, "never more than one at a time"
        await page.keyboard.press("Escape")                                    # back to the menu
        await page.wait_for_selector("[data-testid=tile-training]")
        await asyncio.sleep(0.4)
        assert await page.evaluate("window.__eventos.qtes.filter((e) => e.practice).length") == 0
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))
