"""The real client in a real (headless) Chromium: sign-in, mirrored messages, escaping, clock sync, phone layout.

Skipped when the client has not been built (`npm run build` in activity_client/) or Playwright's Chromium is missing.
"""
import asyncio
import base64
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

WEB = Path(__file__).resolve().parents[1] / "eventos_app" / "activity" / "web"
playwright_api = pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity import ActivityServer, DiscordAuth, Hub  # noqa: E402

WIN = {"evade": [0.0, 4.0], "parry": [2.5, 4.5], "bf": [3.3, 3.7]}
PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
SHOTS = os.environ.get("ACTIVITY_SHOTS")     # a folder: screenshots are saved there when set


def message(mid: str, text: str, name: str = "Ana", **extra) -> dict:
    return {"id": mid, "ts": 1767225600000, "edited": False, "text": text, "attachments": [], "embeds": [],
            "author": {"id": "1", "name": name, "avatar": "", "bot": False, "webhook": False, "ours": False, "color": "#ff8800"},
            **extra}


def _chromium() -> str | None:
    """The Chromium Playwright was set up with (its own version may differ from the library's expectations)."""
    for pattern in ("chromium-*/chrome-linux/chrome",):
        found = sorted(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob(pattern))
        if found:
            return str(found[-1])
    return None


class Actions:
    """What the bridge does for a player, recorded instead of sent to Discord."""

    def __init__(self, hub):
        self.hub, self.said, self.pressed = hub, [], []

    def characters_of(self, user_id):
        return ["Kuro", "Shiro"]

    def me_of(self, user_id):
        return {}

    async def say(self, conn, frame):
        self.said.append(frame)

    async def press(self, conn, frame):
        self.pressed.append(frame)
        await self.hub.send(conn, {"t": "qte_result", "id": frame.get("id"), "ok": True, "ms": 321, "reactions": ["✅"]})


async def with_page(scenario, actions: bool = False):
    hub = Hub()
    hub.channel_name = "qte-evento"
    acts = Actions(hub) if actions else None
    async def media(url):                       # Discord's CDN, replaced by one real 1x1 picture
        hub.media_requests.append(url)
        return "image/png", PIXEL

    hub.media_requests = []
    server = ActivityServer(hub, auth=DiscordAuth(client_id=1, client_secret="x"), authorize=None, web_dir=WEB,
                            client_id=1, port=0, actions=acts, media_fetch=media, media_dir=Path(tempfile.mkdtemp()))
    hub.test_actions = acts
    port = await server.start()
    try:
        async with playwright_api.async_playwright() as p:
            try:
                browser = await p.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
            except Exception as exc:  # noqa: BLE001 - no browser here (e.g. CI): nothing to test
                pytest.skip(f"no Chromium available: {str(exc).splitlines()[0]}")
            try:
                return await scenario(hub, browser, f"http://127.0.0.1:{port}")
            finally:
                await browser.close()
    finally:
        await server.stop()


def test_the_client_mirrors_the_channel_safely_and_measures_the_clock():
    async def scenario(hub, browser, url):
        hub.backlog.append(message("1", "**negrita** y *cursiva* y `código` y ||secreto|| https://example.com/x"))
        hub.backlog.append(message("2", "<script>window.hacked=1</script><img src=x onerror=window.hacked=1>"))
        page = await browser.new_page(viewport={"width": 1000, "height": 640})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        feed = page.locator("#feed .msg")
        assert await feed.count() == 2
        assert await page.locator("#feed strong").inner_text() == "negrita"
        assert await page.locator("#feed em").inner_text() == "cursiva"
        assert await page.locator("#feed code").inner_text() == "código"
        assert await page.locator("#feed a").get_attribute("href") == "https://example.com/x"
        text2 = await feed.nth(1).locator(".text").inner_text()
        assert "<script>" in text2 and await page.evaluate("window.hacked") is None      # shown as text, never run
        assert await page.locator("#feed script, #feed img[src='x']").count() == 0

        spoiler = page.locator("#feed .spoiler")
        assert "open" not in (await spoiler.get_attribute("class"))
        await spoiler.click()
        assert "open" in (await spoiler.get_attribute("class"))

        await hub.push_message(message("3", "en vivo"))
        await page.wait_for_function("document.querySelectorAll('#feed .msg').length === 3")
        await hub.edit_message(message("3", "editado", edited=True))
        await page.wait_for_function("document.querySelector('#feed .msg:last-child .text').textContent === 'editado'")
        await hub.delete_message("1")
        await page.wait_for_function("document.querySelectorAll('#feed .msg').length === 2")

        await page.wait_for_function("window.__eventos.samples.length >= 8", timeout=5000)
        sync = await page.locator("#sync").inner_text()
        assert "ms · reloj" in sync
        offset = await page.evaluate("window.__eventos.offset")
        assert abs(offset) < 50                       # same machine: the clocks agree within a few ms
        stats = hub.stats()
        assert stats[0]["rtt_ms"] is not None and stats[0]["rtt_ms"] < 100 and abs(stats[0]["offset_ms"]) < 50

        other = await browser.new_page(viewport={"width": 1000, "height": 640})
        await other.goto(f"{url}/?dev=Luis")
        await other.wait_for_selector("body[data-state=connected]")
        await page.wait_for_function("document.querySelectorAll('#users li').length === 2")
        assert await other.locator("#feed .msg").count() == 2          # the backlog arrives with the welcome
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-desktop.png"))
        assert errors == []

    asyncio.run(with_page(scenario))


def test_the_phone_layout_fits_and_a_page_opened_outside_discord_says_what_to_do():
    async def scenario(hub, browser, url):
        for i in range(12):
            hub.backlog.append(message(str(i), f"mensaje largo número {i} " + "palabra " * 30, name="Jugador con un nombre largo"))
        phone = await browser.new_page(viewport={"width": 375, "height": 700}, device_scale_factor=2, is_mobile=True)
        await phone.goto(f"{url}/?dev=Ana")
        await phone.wait_for_selector("body[data-state=connected]")
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")   # no sideways scroll
        feed_box = await phone.locator("#feed").bounding_box()
        assert feed_box["height"] > 300 and feed_box["width"] <= 375
        if SHOTS:
            await phone.screenshot(path=str(Path(SHOTS) / "activity-phone.png"))

        plain = await browser.new_page()
        await plain.goto(f"{url}/")                                     # no ?dev, not inside Discord
        await plain.wait_for_selector("body[data-state=error]")
        assert "desde Discord" in await plain.locator("#banner").inner_text()

    asyncio.run(with_page(scenario))


def qte(hub, qid, me, mode="single", difficulty="easy", offset_ms=0, **extra):
    """A QTE frame as the bridge makes it (for this very player unless `target` is given)."""
    commands = {"single": ["evade", "parry", "save", "adapt"], "group": ["evade", "parry"], "combo": ["evade", "parry"],
                "direction": ["up", "down", "left", "right"], "bf_chain": ["parry"]}[mode]
    frame = {"id": str(qid), "mode": mode, "difficulty": difficulty, "target": {"id": me, "name": "Ana"}, "participants": [],
             "tGo": hub.now_ms() - offset_ms, "timeout": 6.0, "windows": WIN, "commands": commands}
    frame.update(extra)
    return frame

async def settle_after(page, count):
    await page.wait_for_function(f"window.__eventos.qtes.size >= {count} && [...window.__eventos.qtes.values()].every(e => e.seen !== null)")


async def settle(page):
    await page.wait_for_function("[...window.__eventos.qtes.values()].every(e => e.seen !== null)")




def test_the_player_writes_with_the_chosen_identity_and_answers_a_qte_with_a_timed_button():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        acts = hub.test_actions

        # writing: Enter sends, the box is cleared, the identity selector offers the characters
        assert not await page.locator("#input").is_disabled()
        assert await page.locator("#as option").all_inner_texts() == ["Ana (prueba local)", "Kuro", "Shiro"]
        await page.select_option("#as", "Kuro")
        await page.fill("#input", "  hola desde la actividad  ")
        await page.press("#input", "Enter")
        await page.wait_for_function("document.querySelector('#input').value === ''")
        await page.fill("#input", "   ")
        await page.press("#input", "Enter")                         # blank: nothing is sent
        for _ in range(40):
            if acts.said:
                break
            await asyncio.sleep(0.05)
        assert acts.said == [{"t": "say", "text": "hola desde la actividad", "as": "Kuro"}]

        # a QTE for somebody else: no evade, but this player can save them
        await hub.qte_start(qte(hub, 5, "999", target={"id": "999", "name": "Luis"}))
        card = page.locator('.qcard[data-id="5"]')
        await card.wait_for()
        assert "Para Luis" in await card.locator(".who").inner_text()
        await settle(page)
        assert await card.locator('.act[data-cmd=evade]').count() == 0
        assert not await card.locator('.act[data-cmd=save]').is_disabled()
        await hub.qte_end("5")
        await page.wait_for_selector('.qcard[data-id="5"]', state="detached")

        # a QTE for this player: press Evade with the keyboard; the screen's own stopwatch is what is sent
        me = await page.evaluate("window.__eventos.you.id")
        await hub.qte_start(qte(hub, 6, me))
        mine = page.locator('.qcard[data-id="6"]')
        await mine.wait_for()
        await settle(page)
        assert not await mine.locator('.act[data-cmd=evade]').is_disabled()
        await asyncio.sleep(0.35)
        await page.keyboard.press("Alt+e")                                    # still typing in the box: Alt+letter works
        await page.wait_for_selector('.qcard[data-id="6"][data-result=ok]')
        assert "321 ms" in await mine.locator(".res").inner_text()
        assert await mine.locator('.act[data-cmd=evade]').is_disabled()      # one answer per QTE
        press = acts.pressed[0]
        assert press["command"] == "evade" and press["id"] == "6" and 300 <= press["dt"] < 1500, press
        await page.keyboard.press("Alt+p")                                    # parry is not offered inline (it floats): nothing sent
        await hub.qte_end("6")
        assert len(acts.pressed) == 1

        await page.fill("#input", "")
        await page.keyboard.type("aqe")                                       # letters typed in the box are letters
        assert len(acts.pressed) == 1 and await page.locator("#input").input_value() == "aqe"
        assert errors == []

    asyncio.run(with_page(scenario, actions=True))



def test_the_mirror_shows_replies_reactions_stickers_and_rich_embeds_and_the_read_only_mode_says_so():
    async def scenario(hub, browser, url):
        rich = message("9", "mira esto", reply={"author": "Luis", "text": "¿qué pasó?"},
                       reactions=[{"emoji": {"name": "✅"}, "count": 3}, {"emoji": {"name": "x", "id": "123", "animated": False}, "count": 1}],
                       stickers=[{"name": "hi", "url": "https://media.discordapp.net/stickers/1.png"}])
        rich["embeds"] = [{"title": "Mesmerizer Miku", "url": "https://klipy.com/x", "description": "un **gif**", "color": "#5865f2",
                           "image": "", "thumb": "https://media.discordapp.net/external/a/thumb.png", "video": "https://media.discordapp.net/external/a/clip.mp4",
                           "author": "Klipy", "footer": "pie", "fields": [{"name": "HP", "value": "10", "inline": True}]}]
        hub.backlog.append(rich)
        page = await browser.new_page(viewport={"width": 1000, "height": 700})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        assert "Luis: ¿qué pasó?" in await page.locator("#feed .reply").inner_text()
        chips = await page.locator("#feed .reactions span").all_inner_texts()
        assert chips == ["✅3", "1"]
        assert await page.locator("#feed img.sticker").count() == 1
        assert await page.locator("#feed .embed .et a").get_attribute("href") == "https://klipy.com/x"
        assert await page.locator("#feed .embed video").count() == 1 and await page.locator("#feed .embed strong").inner_text() == "gif"
        assert await page.locator("#feed .embed .fields b").inner_text() == "HP"
        assert await page.locator("#input").is_disabled() and "Solo lectura" in (await page.locator("#input").get_attribute("placeholder"))
        assert await page.locator('#actions .act[data-cmd=adapt]').count() == 0 or await page.locator('#actions .act[data-cmd=adapt]').is_disabled()
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-rich.png"))

    asyncio.run(with_page(scenario))



def test_the_phone_layout_keeps_the_buttons_and_the_writing_box_on_screen():
    async def scenario(hub, browser, url):
        for i in range(15):
            hub.backlog.append(message(str(i), f"mensaje {i} " + "palabra " * 20))
        phone = await browser.new_page(viewport={"width": 375, "height": 667}, device_scale_factor=2, is_mobile=True, has_touch=True)
        await phone.goto(f"{url}/?dev=Ana")
        await phone.wait_for_selector("body[data-state=connected]")
        me = await phone.evaluate("window.__eventos.you.id")
        await hub.qte_start(qte(hub, 1, me, difficulty="hard"))
        await phone.wait_for_selector(".qcard")
        await settle(phone)
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for selector in ("#dock", "#actions", "#input", "#send", '.qcard .act[data-cmd=evade]'):
            box = await phone.locator(selector).bounding_box()
            assert box and box["y"] >= 0 and box["y"] + box["height"] <= 667 and box["x"] >= 0 and box["x"] + box["width"] <= 375, (selector, box)
        evade = await phone.locator('.qcard .act[data-cmd=evade]').bounding_box()
        assert evade["height"] >= 44 and evade["width"] >= 60                # a thumb-sized target
        assert (await phone.locator("#feed").bounding_box())["height"] > 100
        if SHOTS:
            await phone.screenshot(path=str(Path(SHOTS) / "activity-phone-qte.png"))

    asyncio.run(with_page(scenario, actions=True))




def test_the_time_bar_shows_the_windows_and_the_cursor_starts_where_the_engine_is():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 900, "height": 700})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        me = await page.evaluate("window.__eventos.you.id")
        await hub.qte_start(qte(hub, 1, me, difficulty="hard", offset_ms=2000, timeout=5.0))
        await settle_after(page, 1)
        card = page.locator('.qcard[data-id="1"]')
        assert await card.locator(".track").is_visible() and await page.locator("#legend").is_visible()
        boxes = {name: await card.locator(f".zone.{name}").evaluate("e => [e.style.left, e.style.width]") for name in ("evade", "parry", "bf")}
        assert boxes["evade"] == ["0%", "80%"] and boxes["parry"] == ["50%", "40%"] and boxes["bf"][0] == "66%"
        read = "e => parseFloat(getComputedStyle(e).left) / e.parentElement.clientWidth * 100"
        first = float(await card.locator(".cursor").evaluate(read))
        assert first >= 38                                      # 2 s of the 5 s had already gone by when the frame arrived
        await asyncio.sleep(0.6)
        later = float(await card.locator(".cursor").evaluate(read))
        assert later > first + 5
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-bar.png"))
        await hub.qte_end("1")

        # a combo shows the step it wants now; a fake QTE has no buttons and does not say who it is for
        await hub.qte_start(qte(hub, 2, me, mode="combo", windows=None, timeout=15.0, combo={"length": 5, "index": 0, "step": "parry"}))
        combo = page.locator('.qcard[data-id="2"]')
        await combo.wait_for()
        assert "1/5" in await combo.locator(".combo").inner_text() and "Parry" in await combo.locator(".combo").inner_text()
        assert await combo.locator(".track").count() == 0 and await combo.locator('.act[data-cmd=parry]').count() == 1   # combos keep the parry inline
        await hub.send(next(iter(hub.conns.values())), {"t": "qte_step", "id": "2", "index": 1, "step": "evade"})
        await page.wait_for_function("document.querySelector('.qcard[data-id=\"2\"] .combo').textContent.includes('2/5')")
        await hub.qte_start(qte(hub, 3, me, mode="combo", windows=None, target=None, commands=[]))
        fake = page.locator('.qcard[data-id="3"]')
        await fake.wait_for()
        assert await fake.locator(".act").count() == 0

    asyncio.run(with_page(scenario, actions=True))



def test_the_hud_shows_the_boss_the_players_hp_and_your_charges():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 900, "height": 700})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        me = await page.evaluate("window.__eventos.you.id")
        assert await page.locator("#hud").is_hidden()          # nothing to show yet
        hub.state = {"boss": {"name": "Sukuna", "hp": 650, "max": 1000}, "fight": True, "players": [
            {"id": me, "name": "Ana", "hp": 20, "max": 100, "revenge": True}, {"id": "9", "name": "Luis", "hp": 90, "max": 100, "revenge": False}]}
        await hub.broadcast({"t": "state", "s": hub.state})
        await hub.broadcast({"t": "me", "me": {"charges": {"power1": 100.0, "power2": 30.0}, "cost": 100, "streak": 4}})
        await page.wait_for_selector("#hud:not([hidden])")
        assert await page.locator("#boss-text").inner_text() == "650 / 1000" and "Sukuna" in await page.locator("#boss-name").inner_text()
        assert "20 / 100 · REVENGE" == await page.locator("#me-hp-text").inner_text()
        assert await page.locator("#me-hp-fill").get_attribute("data-level") == "low"
        assert await page.locator("#players li").count() == 2 and await page.locator("#players li.you").count() == 1
        assert "ready" in await page.locator("#ch1-fill").evaluate("e => e.parentElement.className")
        assert "ready" not in await page.locator("#ch2-fill").evaluate("e => e.parentElement.className")
        assert "4" in await page.locator("#streak").inner_text()
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-hud.png"))
        phone = await browser.new_page(viewport={"width": 375, "height": 667}, is_mobile=True, has_touch=True)
        await phone.goto(f"{url}/?dev=Luis")
        await phone.wait_for_selector("body[data-state=connected]")
        await phone.wait_for_selector("#hud:not([hidden])")
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert await phone.locator("#players").is_hidden()      # the phone keeps the compact strip only

    asyncio.run(with_page(scenario, actions=True))


def test_pictures_load_through_the_app_and_a_name_in_maths_letters_keeps_its_first_letter():
    async def scenario(hub, browser, url):
        hub.backlog.append(message("1", "con foto", name="Ana", **{}))
        hub.backlog[-1]["author"]["avatar"] = "https://cdn.discordapp.com/avatars/1/a.png"
        hub.backlog[-1]["attachments"] = [{"url": "https://cdn.discordapp.com/attachments/1/2/x.png", "name": "x.png", "image": True}]
        hub.backlog.append(message("2", "sin foto", name="𝙋𝙖𝙣𝙘𝙤𝙣𝙦𝙪𝙚𝙨𝙤"))
        page = await browser.new_page(viewport={"width": 900, "height": 700})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        await page.wait_for_function("document.querySelectorAll('#feed img.avatar, #feed .attach img').length === 2 && "
                                     "[...document.querySelectorAll('#feed img.avatar, #feed .attach img')].every(i => i.complete && i.naturalWidth > 0)")
        sources = await page.locator("#feed img").evaluate_all("els => els.map(e => e.getAttribute('src'))")
        assert all(src.startswith("/media?u=https%3A%2F%2Fcdn.discordapp.com%2F") for src in sources), sources
        assert len(hub.media_requests) == 2
        letter = await page.locator("#feed .msg:nth-child(2) .avatar").inner_text()
        assert letter == "𝙋"                                     # not the broken half of a surrogate pair

    asyncio.run(with_page(scenario))


def test_several_qtes_at_once_each_with_its_own_card_and_buttons():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 1000, "height": 800})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        acts = hub.test_actions
        me = await page.evaluate("window.__eventos.you.id")
        await hub.qte_start(qte(hub, 1, me, difficulty="easy"))
        await hub.qte_start(qte(hub, 2, me, difficulty="hard"))
        await hub.qte_start(qte(hub, 3, "999", target={"id": "999", "name": "Luis"}))
        await settle_after(page, 3)
        assert await page.locator(".qcard").count() == 3 and await page.locator(".qcard .track").count() == 3
        # answer the SECOND one first: the press names its QTE and the first keeps its buttons
        await page.locator('.qcard[data-id="2"] .act[data-cmd=evade]').dispatch_event("pointerdown", {"button": 0, "pointerType": "mouse"})
        for _ in range(40):
            if acts.pressed:
                break
            await asyncio.sleep(0.05)
        assert [(p["id"], p["command"]) for p in acts.pressed] == [("2", "evade")]
        assert await page.locator('.qcard[data-id="2"] .act[data-cmd=evade]').is_disabled()
        assert not await page.locator('.qcard[data-id="1"] .act[data-cmd=evade]').is_disabled()
        # the keyboard answers the oldest QTE that still can
        await page.keyboard.press("e")
        for _ in range(40):
            if len(acts.pressed) == 2:
                break
            await asyncio.sleep(0.05)
        assert [(p["id"], p["command"]) for p in acts.pressed] == [("2", "evade"), ("1", "evade")]
        # and it is a rescue for the one that is not mine
        await page.locator('.qcard[data-id="3"] .act[data-cmd=save]').dispatch_event("pointerdown", {"button": 0, "pointerType": "mouse"})
        for _ in range(40):
            if len(acts.pressed) == 3:
                break
            await asyncio.sleep(0.05)
        assert acts.pressed[2]["command"] == "save" and acts.pressed[2]["id"] == "3"
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-multi.png"))

    asyncio.run(with_page(scenario, actions=True))


def test_the_parry_button_appears_at_a_random_place_when_its_window_opens_unless_switched_off():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 1000, "height": 800})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        acts = hub.test_actions
        me = await page.evaluate("window.__eventos.you.id")
        window = {"evade": [0.0, 4.0], "parry": [0.5, 3.0], "bf": [1.5, 1.9]}
        spots = []
        for qid in (1, 2, 3, 4):
            await hub.qte_start(qte(hub, qid, me, windows=window))
            await settle_after(page, 1)
            assert await page.locator(".float-parry").count() == 0              # not before the window opens
            assert await page.locator(f'.qcard[data-id="{qid}"] .act[data-cmd=parry]').count() == 0    # and never inline
            await page.wait_for_selector(".float-parry", timeout=3000)
            box = await page.locator(".float-parry").bounding_box()
            feed = await page.locator("#feed").bounding_box()
            assert feed["x"] <= box["x"] and box["x"] + box["width"] <= feed["x"] + feed["width"] + 1
            assert feed["y"] <= box["y"] and box["y"] + box["height"] <= feed["y"] + feed["height"] + 1
            spots.append((round(box["x"]), round(box["y"])))
            if qid == 1:
                await page.locator(".float-parry").dispatch_event("pointerdown", {"button": 0, "pointerType": "mouse"})
                for _ in range(40):
                    if acts.pressed:
                        break
                    await asyncio.sleep(0.05)
                assert acts.pressed[0]["command"] == "parry" and acts.pressed[0]["id"] == "1"
                assert await page.locator(".float-parry").count() == 0          # pressed: it goes away
            await hub.qte_end(str(qid))
            await page.wait_for_selector(f'.qcard[data-id="{qid}"]', state="detached")
            assert await page.locator(".float-parry").count() == 0
        assert len(set(spots)) > 1                                              # it does not sit in one place

        await page.uncheck("#float-parry")                                      # the player prefers it fixed
        await hub.qte_start(qte(hub, 9, me, windows=window))
        await page.locator('.qcard[data-id="9"] .act[data-cmd=parry]').wait_for()
        assert await page.locator(".float-parry").count() == 0
        assert await page.evaluate("localStorage.getItem('eventos.floatParry')") == "0"

    asyncio.run(with_page(scenario, actions=True))


def test_the_cooldowns_of_saves_parry_counter_and_powers_count_down_on_the_buttons():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 1000, "height": 800})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        me = await page.evaluate("window.__eventos.you.id")
        now = hub.now_ms()
        await hub.broadcast({"t": "me", "me": {
            "charges": {"power1": 100.0, "power2": 30.0}, "cost": 100, "streak": 0,
            "saves": {"left": 0, "limit": 2, "until": now + 20000}, "parryUntil": now + 15000, "counterUntil": now + 4000,
            "powers": {"Kuro": {"power1": {"name": "Rayo", "until": None, "paused": None}, "power2": {"name": "Escudo", "until": now + 30000, "paused": None}}},
            "domain": True}})
        attack = page.locator('#actions .act[data-cmd=attack]')
        await page.wait_for_function("document.querySelector('#actions .act[data-cmd=attack]').classList.contains('hot')")
        assert " s" in await attack.locator(".cd").inner_text()                 # the counter window is open: seconds left
        assert await page.locator('#actions .act[data-cmd=domain]').count() == 1
        assert await page.locator('#actions .act[data-cmd=power1] b').inner_text() == "Poder 1"    # as yourself: generic
        await page.select_option("#as", "Kuro")                                 # as a character: its own powers
        assert await page.locator('#actions .act[data-cmd=power1] b').inner_text() == "Rayo"
        assert "100" in await page.locator('#actions .act[data-cmd=power1] .cd').inner_text()
        assert "ready" in await page.locator('#actions .act[data-cmd=power1]').get_attribute("class")
        assert "⏱" in await page.locator('#actions .act[data-cmd=power2] .cd').inner_text()          # on cooldown
        # a QTE: parry is locked while the parry cooldown runs, and saving while there are no saves left
        window = {"evade": [0.0, 4.0], "parry": [0.2, 3.0], "bf": None}
        await hub.qte_start(qte(hub, 1, me, windows=window))
        await hub.qte_start(qte(hub, 2, "999", target={"id": "999", "name": "Luis"}))
        await settle_after(page, 2)
        await page.uncheck("#float-parry")
        await hub.qte_end("1")
        await hub.qte_start(qte(hub, 3, me, windows=window))
        await settle_after(page, 2)
        parry = page.locator('.qcard[data-id="3"] .act[data-cmd=parry]')
        assert await parry.is_disabled() and "⏱" in await parry.locator(".cd").inner_text()
        save = page.locator('.qcard[data-id="2"] .act[data-cmd=save]')
        assert await save.is_disabled() and "⏱" in await save.locator(".cd").inner_text()
        await hub.broadcast({"t": "me", "me": {"charges": {"power1": 0, "power2": 0}, "cost": 100, "streak": 0, "saves": {"left": 2, "limit": 2, "until": None},
                                              "parryUntil": None, "counterUntil": None, "powers": {}, "domain": False}})
        await page.wait_for_function("!document.querySelector('.qcard[data-id=\"3\"] .act[data-cmd=parry]').disabled")
        assert not await save.is_disabled() and "2/2" in await save.locator(".cd").inner_text()
        assert await page.locator('#actions .act[data-cmd=domain]').count() == 0
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-cooldowns.png"))

    asyncio.run(with_page(scenario, actions=True))


def test_a_direction_qte_shows_the_arrow_and_a_pad_and_a_bf_chain_only_the_parry():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 1000, "height": 800})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        acts = hub.test_actions
        me = await page.evaluate("window.__eventos.you.id")
        await hub.qte_start(qte(hub, 1, me, mode="direction", windows={"evade": [0.0, 4.0], "bf": None}, timeout=4.0, arrow="⬆️"))
        card = page.locator('.qcard[data-id="1"]')
        await card.wait_for()
        await settle_after(page, 1)
        assert "⬆️" in await card.locator(".dirhint").inner_text()
        assert await card.locator(".act").count() == 4
        await page.keyboard.press("ArrowDown")                                   # the opposite of the arrow shown
        for _ in range(40):
            if acts.pressed:
                break
            await asyncio.sleep(0.05)
        assert acts.pressed[0]["command"] == "down" and acts.pressed[0]["id"] == "1"
        await hub.qte_end("1")
        await hub.qte_start(qte(hub, 2, me, mode="bf_chain", windows={"parry": [0.0, 3.0], "bf": [1.2, 1.5]}, timeout=3.0, chain=2))
        await page.wait_for_selector(".float-parry", timeout=3000)
        assert "BLACK FLASH" in await page.locator('.qcard[data-id="2"] .qhead strong').inner_text()

    asyncio.run(with_page(scenario, actions=True))
