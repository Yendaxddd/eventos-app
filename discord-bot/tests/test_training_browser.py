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


async def do_gesture(page, keyboard=False):
    """Answers the gesture QTE on screen like a person would: a real swipe, a real drag, real taps (or the keys)."""
    q = await page.evaluate("(() => { const e = window.__eventos.qtes.find((x) => x.practice && !x.pressed && !x.ended); return e ? { mode: e.q.mode, arena: e.q.arena } : null; })()")
    if not q or q["mode"] not in ("flick", "drag", "mash"):
        return False
    if q["mode"] == "flick":
        if keyboard:
            await page.keyboard.press({"up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight"}[q["arena"]["dir"]])
            return True
        box = await page.locator(".gx-flick").first.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        dx, dy = {"up": (0, -70), "down": (0, 70), "left": (-70, 0), "right": (70, 0)}[q["arena"]["dir"]]
        await page.mouse.move(cx, cy)
        await page.mouse.down()
        await page.mouse.move(cx + dx, cy + dy, steps=4)
        await page.mouse.up()
    elif q["mode"] == "drag":
        pad = await page.locator(".gx-drag").first.bounding_box()
        token = await page.locator(".gx-token").first.bounding_box()
        gx, gy = q["arena"]["to"]
        await page.mouse.move(token["x"] + token["width"] / 2, token["y"] + token["height"] / 2)
        await page.mouse.down()
        await page.mouse.move(pad["x"] + gx * pad["width"], pad["y"] + gy * pad["height"], steps=6)
        await page.mouse.up()
    else:
        for _ in range(q["arena"]["count"]):
            if keyboard:
                await page.keyboard.press("Space")
            else:
                await page.locator(".gx-mash").first.click()
            await asyncio.sleep(0.09)
    return True


@pytest.mark.parametrize("kind", ["flick", "drag", "mash"])
def test_the_new_gesture_qtes_are_answered_with_a_real_swipe_drag_or_taps(kind):
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"kinds": [kind], "difficulties": ["easy"], "count": 2})
        await page.click("[data-testid=training-start]")
        loop = asyncio.get_running_loop()
        end = loop.time() + 30
        while loop.time() < end and await page.locator("[data-testid=training-done]").count() == 0:
            if await page.locator(f"[data-testid=gesture-{kind}]").count():
                await do_gesture(page)
            await asyncio.sleep(0.1)
        await page.wait_for_selector("[data-testid=training-done]")
        assert (await page.locator("[data-testid=sum-ok]").inner_text()).strip() == "2 / 2", kind
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


@pytest.mark.parametrize("kind", ["flick", "mash"])
def test_the_gesture_qtes_can_be_answered_with_the_keyboard(kind):
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"kinds": [kind], "difficulties": ["easy"], "count": 1})
        await page.click("[data-testid=training-start]")
        await page.wait_for_selector(f"[data-testid=gesture-{kind}]", timeout=8000)
        await do_gesture(page, keyboard=True)
        await page.wait_for_selector("[data-testid=training-done]", timeout=8000)
        assert (await page.locator("[data-testid=sum-ok]").inner_text()).strip() == "1 / 1"
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_a_fake_qte_is_won_by_not_touching_it():
    async def scenario(hub, browser, url):
        page = await open_training(browser, url, {"kinds": ["fake"], "difficulties": ["easy"], "count": 1, "speed": 200})
        await page.click("[data-testid=training-start]")
        await page.wait_for_selector("[data-testid=training-done]", timeout=15000)
        assert (await page.locator("[data-testid=sum-ok]").inner_text()).strip() == "1 / 1"
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))
