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

        # a QTE for somebody else: the timed buttons stay off, the rest are on
        await hub.qte_start({"id": "5", "mode": "single", "difficulty": "hard", "target": {"id": "999", "name": "Luis"},
                             "participants": [], "tGo": hub.now_ms(), "timeout": 4.0, "commands": ["evade", "parry", "adapt"]})
        await page.wait_for_selector("#qte[data-active=true]")
        assert "Luis" in await page.locator("#qte-sub").inner_text()
        assert await page.locator('.act[data-cmd=evade]').is_disabled() and not await page.locator('.act[data-cmd=adapt]').is_disabled()
        await hub.qte_end("5")
        await page.wait_for_selector("#qte[data-active=false]")

        # a QTE for this player: press Evade with the keyboard; the screen's own stopwatch is what is sent
        me = await page.evaluate("window.__eventos.you.id")
        await hub.qte_start({"id": "6", "mode": "single", "difficulty": "easy", "target": {"id": me, "name": "Ana"},
                             "participants": [], "tGo": hub.now_ms(), "timeout": 6.0, "windows": WIN, "commands": ["evade", "parry", "adapt"]})
        await page.wait_for_function("window.__eventos.qte && window.__eventos.qte.seen !== null")
        assert not await page.locator('.act[data-cmd=evade]').is_disabled()
        await asyncio.sleep(0.35)
        await page.keyboard.press("Alt+e")                                    # still typing in the box: Alt+letter works
        await page.wait_for_selector("#qte[data-result=ok]")
        assert "321 ms" in await page.locator("#qte-sub").inner_text()
        assert await page.locator('.act[data-cmd=evade]').is_disabled()      # one answer per QTE
        press = acts.pressed[0]
        assert press["command"] == "evade" and press["id"] == "6" and 300 <= press["dt"] < 1500, press
        await page.keyboard.press("Alt+p")                                    # parry is off now: nothing sent
        await hub.qte_end("6")
        assert len(acts.pressed) == 1

        typing_keys = len(acts.pressed)
        await page.fill("#input", "")
        await page.keyboard.type("aqe")                                       # letters typed in the box are letters
        assert len(acts.pressed) == typing_keys and await page.locator("#input").input_value() == "aqe"
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
        assert await page.locator('.act[data-cmd=adapt]').is_disabled()
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
        await hub.qte_start({"id": "1", "mode": "single", "difficulty": "hard", "target": {"id": me, "name": "Ana"},
                             "participants": [], "tGo": hub.now_ms(), "timeout": 5.0, "windows": WIN, "commands": ["evade", "parry", "adapt"]})
        await phone.wait_for_selector("#qte[data-active=true]")
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for selector in ("#qte", "#actions", "#input", "#send", '.act[data-cmd=evade]'):
            box = await phone.locator(selector).bounding_box()
            assert box and box["y"] >= 0 and box["y"] + box["height"] <= 667 and box["x"] >= 0 and box["x"] + box["width"] <= 375, (selector, box)
        evade = await phone.locator('.act[data-cmd=evade]').bounding_box()
        assert evade["height"] >= 44 and evade["width"] >= 60                # a thumb-sized target
        assert (await phone.locator("#feed").bounding_box())["height"] > 150
        if SHOTS:
            await phone.screenshot(path=str(Path(SHOTS) / "activity-phone-qte.png"))

    asyncio.run(with_page(scenario, actions=True))


def test_the_time_bar_shows_the_windows_and_the_cursor_starts_where_the_engine_is():
    async def scenario(hub, browser, url):
        page = await browser.new_page(viewport={"width": 900, "height": 700})
        await page.goto(f"{url}/?dev=Ana")
        await page.wait_for_selector("body[data-state=connected]")
        me = await page.evaluate("window.__eventos.you.id")
        windows = {"evade": [0.0, 4.0], "parry": [2.5, 4.5], "bf": [3.3, 3.7]}
        await hub.qte_start({"id": "1", "mode": "single", "difficulty": "hard", "target": {"id": me, "name": "Ana"}, "participants": [],
                             "tGo": hub.now_ms() - 2000, "timeout": 5.0, "windows": windows, "commands": ["evade", "parry", "adapt"]})
        await page.wait_for_function("window.__eventos.qte && window.__eventos.qte.seen !== null")
        assert await page.locator("#qte-track").is_visible() and await page.locator("#qte-legend").is_visible()
        boxes = {}
        for name in ("evade", "parry", "bf"):
            boxes[name] = await page.locator(f"#z-{name}").evaluate("e => [e.style.left, e.style.width]")
        assert boxes["evade"] == ["0%", "80%"] and boxes["parry"] == ["50%", "40%"] and boxes["bf"][0] == "66%"
        first = float(await page.locator("#qte-cursor").evaluate("e => parseFloat(getComputedStyle(e).left) / e.parentElement.clientWidth * 100"))
        assert first >= 38                                      # 2 s of the 5 s had already gone by when the frame arrived
        await asyncio.sleep(0.6)
        later = float(await page.locator("#qte-cursor").evaluate("e => parseFloat(getComputedStyle(e).left) / e.parentElement.clientWidth * 100"))
        assert later > first + 5
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-bar.png"))
        await hub.qte_end("1")
        await hub.qte_start({"id": "2", "mode": "combo", "difficulty": "easy", "target": {"id": me, "name": "Ana"}, "participants": [],
                             "tGo": hub.now_ms(), "timeout": 15.0, "windows": None, "commands": []})
        await page.wait_for_selector("#qte[data-active=true]")
        assert not await page.locator("#qte-track").is_visible()
        assert "chat" in await page.locator("#qte-sub").inner_text() and await page.locator('.act[data-cmd=evade]').is_disabled()

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
