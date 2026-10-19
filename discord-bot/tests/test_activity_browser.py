"""The real client in a real (headless) Chromium: sign-in, the mirrored channel, the floating QTE buttons (evade turning into
parry, several at once, never overlapping), settings, the latency test and the tutorial.

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

# short windows so the tests do not wait for seconds: evade until 2.0 s, parry from 0.8 s to 2.6 s, Black Flash band 1.5–1.9 s
WIN = {"evade": [0.0, 2.0], "parry": [0.8, 2.6], "bf": [1.5, 1.9]}
RULES = {"times": {"medium": {"evade": 2.5, "parry": [1.5, 3.1], "perfect": 2.3, "timeout": 3.6},
                   "easy": {"evade": 6.0, "parry": [4.0, 7.0], "perfect": 5.5, "timeout": 6.75}},
         "bfWindow": 0.2, "chainWindow": 0.15, "counterWindow": 5.0, "saveLimit": 2, "saveWindow": 60, "ultimateCost": 100}
PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
SHOTS = os.environ.get("ACTIVITY_SHOTS")     # a folder: screenshots are saved there when set


def message(mid: str, text: str, name: str = "Ana", **extra) -> dict:
    return {"id": mid, "ts": 1767225600000, "edited": False, "text": text, "attachments": [], "embeds": [],
            "author": {"id": "1", "name": name, "avatar": "", "bot": False, "webhook": False, "ours": False, "color": "#ff8800"},
            **extra}


def _chromium() -> str | None:
    """The Chromium Playwright was set up with (its own version may differ from the library's expectations)."""
    found = sorted(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome"))
    return str(found[-1]) if found else None


class Actions:
    """What the bridge does for a player, recorded instead of sent to Discord."""

    def __init__(self, hub):
        self.hub, self.said, self.pressed = hub, [], []
        self.prefs = None                     # the last settings the client sent
        self.latency = None                   # the last latency test result
        self.tutorial_done = True
        self.me = {}
        self.result_ms = 321
        self.hold = False                     # keep the verdict back (a slow server), to see the screen while it waits

    def characters_of(self, user_id):
        return ["Kuro", "Shiro"]

    def me_of(self, user_id):
        return self.me

    async def welcome_extras(self, conn):
        return {"perms": {"gm": bool(conn.gm)}, "prefs": {"tutorialDone": self.tutorial_done, **(self.prefs or {})}, "calib": None,
                "comp": {"net": 24.0, "device": 0.0, "cap": 300}, "rules": RULES, "charAvatars": {}}

    async def save_prefs(self, conn, prefs):
        self.prefs = prefs

    async def save_latency(self, conn, result):
        self.latency = result
        return result, {"net": 21.0, "device": float((result or {}).get("device") or 0), "cap": 300}

    async def say(self, conn, frame):
        self.said.append(frame)

    async def press(self, conn, frame):
        self.pressed.append(frame)
        if self.hold:
            return
        await self.hub.send(conn, {"t": "qte_result", "id": frame.get("id"), "ok": True, "ms": self.result_ms, "reactions": ["✅"]})


async def with_page(scenario, actions: bool = False, fast_ping: bool = False):
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


async def open_page(browser, url, name="Ana", width=1100, height=760, mobile=False, init=None, extra=""):
    context = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2 if mobile else 1,
                                        is_mobile=mobile, has_touch=mobile)
    page = await context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    if init:
        await page.add_init_script(init)
    await page.goto(f"{url}/?dev={name}{extra}")
    await page.wait_for_selector("[data-testid=composer]")
    page.me = await page.evaluate("window.__eventos.you.id")
    return page


def qte(hub, qid, me, mode="single", difficulty="medium", ago=0.0, **extra):
    """A QTE frame as the bridge makes it (for this very player unless `target` is given)."""
    commands = {"single": ["evade", "parry", "save", "adapt"], "group": ["evade"], "combo": ["evade", "parry"],
                "direction": ["up", "down", "left", "right"], "bf_chain": ["parry"]}[mode]
    frame = {"id": str(qid), "mode": mode, "difficulty": difficulty, "target": {"id": me, "name": "Ana"}, "participants": [],
             "tGo": hub.now_ms() - ago * 1000, "timeout": 3.0, "windows": WIN, "commands": commands}
    frame.update(extra)
    return frame


async def widgets(page):
    return await page.evaluate("""() => [...document.querySelectorAll('[data-testid=qte-widget]')].map((el) => {
        const r = el.getBoundingClientRect();
        return { id: el.dataset.qte, kind: el.dataset.kind, state: el.dataset.state, phase: el.dataset.phase, lead: el.dataset.lead,
                 result: el.dataset.result || null, x: r.x, y: r.y, w: r.width, h: r.height,
                 rank: (el.querySelector('.qw-rank') || {}).textContent || '', cmd: (el.querySelector('.qw-btn') || {}).dataset ? el.querySelector('.qw-btn').dataset.cmd : null };
    })""")


def widget(page, qid):
    return page.locator(f'[data-testid=qte-widget][data-qte="{qid}"]')


async def tap(locator):
    """A press the way the client listens for it (pointer down, like a finger)."""
    await locator.dispatch_event("pointerdown", {"button": 0, "pointerType": "mouse"})


async def wait_presses(acts, count, seconds=2.0):
    for _ in range(int(seconds / 0.05)):
        if len(acts.pressed) >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected {count} presses, got {acts.pressed}")


def overlap(a, b):
    return a["x"] < b["x"] + b["w"] and a["x"] + a["w"] > b["x"] and a["y"] < b["y"] + b["h"] and a["y"] + a["h"] > b["y"]


# ======================================================================================================================
def test_the_client_mirrors_the_channel_safely_and_measures_the_clock():
    async def scenario(hub, browser, url):
        hub.backlog.append(message("1", "**negrita** y *cursiva* y `código` y ||secreto|| https://example.com/x"))
        hub.backlog.append(message("2", "<script>window.hacked=1</script><img src=x onerror=window.hacked=1>"))
        hub.backlog.append(message("2b", "# Un título\n> una cita\n- uno\n- dos\n```\ncódigo en bloque\n```"))
        page = await open_page(browser, url, width=1200, height=640)
        feed = page.locator(".feed .msg")
        assert await feed.count() == 3
        assert await page.locator(".feed strong").first.inner_text() == "negrita"
        assert await page.locator(".feed em").inner_text() == "cursiva"
        assert await page.locator(".feed code").inner_text() == "código"
        assert await page.locator(".feed a").get_attribute("href") == "https://example.com/x"
        text2 = await feed.nth(1).locator(".msg-text").inner_text()
        assert "<script>" in text2 and await page.evaluate("window.hacked") is None      # shown as text, never run
        assert await page.locator(".feed script, .feed img[src='x']").count() == 0
        assert await page.locator(".md-h1").inner_text() == "Un título" and await page.locator(".feed blockquote").count() == 1
        assert await page.locator(".feed li").count() == 2 and "código en bloque" in await page.locator(".feed pre").inner_text()

        spoiler = page.locator(".feed .spoiler")
        assert "open" not in (await spoiler.get_attribute("class"))
        await spoiler.click()
        assert "open" in (await spoiler.get_attribute("class"))

        await hub.push_message(message("3", "en vivo"))
        await page.wait_for_function("document.querySelectorAll('.feed .msg').length === 4")
        await hub.edit_message(message("3", "editado", edited=True))
        await page.wait_for_function("document.querySelector('.feed .msg:last-child .msg-text').textContent.startsWith('editado')")
        assert "(editado)" in await page.locator(".feed .msg:last-child").inner_text()
        await hub.delete_message("1")
        await page.wait_for_function("document.querySelectorAll('.feed .msg').length === 3")

        await page.wait_for_function("window.__eventos.link.samples >= 8", timeout=5000)
        assert "ms" in await page.locator("[data-testid=conn-badge]").inner_text()
        stats = hub.stats()
        assert stats[0]["rtt_ms"] is not None and stats[0]["rtt_ms"] < 100 and abs(stats[0]["offset_ms"]) < 50

        other = await open_page(browser, url, name="Luis", width=1200, height=640)
        await page.wait_for_function("document.querySelectorAll('[data-testid=players-panel] .online li').length === 2")
        assert await other.locator(".feed .msg").count() == 3                      # the backlog arrives with the welcome
        assert page.errors == [] and other.errors == []

    asyncio.run(with_page(scenario))


def test_the_server_measures_each_players_round_trip_itself(monkeypatch):
    import eventos_app.activity.hub as hub_module
    monkeypatch.setattr(hub_module, "PING_EVERY", 0.15)

    async def scenario(hub, browser, url):
        page = await open_page(browser, url)
        await page.wait_for_function("true")
        conn = next(iter(hub.conns.values()))
        for _ in range(60):
            if len(conn.rtts) >= 3:
                break
            await asyncio.sleep(0.1)
        assert len(conn.rtts) >= 3 and conn.net_ms < 50          # the server's own figure, same machine: a few ms
        assert hub.stats()[0]["net_ms"] == round(conn.net_ms, 1)
        assert page.errors == []

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
        page = await open_page(browser, url, width=1000, height=700)
        assert "Luis: ¿qué pasó?" in await page.locator(".feed .msg-reply").inner_text()
        assert await page.locator(".feed .reaction").all_inner_texts() == ["✅\n3", "1"]
        assert await page.locator(".feed img.sticker").count() == 1
        assert await page.locator(".feed .embed .e-title a").get_attribute("href") == "https://klipy.com/x"
        assert await page.locator(".feed .embed video").count() == 1 and await page.locator(".feed .embed .e-desc strong").inner_text() == "gif"
        assert await page.locator(".feed .embed .e-fields b").inner_text() == "HP"
        composer = page.locator("[data-testid=composer] textarea")
        assert await composer.is_disabled() and "Solo lectura" in (await composer.get_attribute("placeholder"))
        assert await page.locator("[data-testid=actions] .act").first.is_disabled()
        assert page.errors == []

    asyncio.run(with_page(scenario))


def test_pictures_load_through_the_app_and_a_name_in_maths_letters_keeps_its_first_letter():
    async def scenario(hub, browser, url):
        hub.backlog.append(message("1", "con foto", name="Ana"))
        hub.backlog[-1]["author"]["avatar"] = "https://cdn.discordapp.com/avatars/1/a.png"
        hub.backlog[-1]["attachments"] = [{"url": "https://cdn.discordapp.com/attachments/1/2/x.png", "name": "x.png", "image": True}]
        hub.backlog.append(message("2", "sin foto", name="𝙋𝙖𝙣𝙘𝙤𝙣𝙦𝙪𝙚𝙨𝙤"))
        page = await open_page(browser, url, width=1000, height=700)
        await page.wait_for_function("[...document.querySelectorAll('.feed .avatar img, .feed .attach img')].length === 2 && "
                                     "[...document.querySelectorAll('.feed .avatar img, .feed .attach img')].every(i => i.complete && i.naturalWidth > 0)")
        sources = await page.locator(".feed .avatar img, .feed .attach img").evaluate_all("els => els.map(e => e.getAttribute('src'))")
        assert all(src.startswith("/media?u=https%3A%2F%2Fcdn.discordapp.com%2F") for src in sources), sources
        assert len(hub.media_requests) == 2
        letter = await page.locator(".feed .msg:nth-child(2) .avatar").inner_text()
        assert letter == "𝙋"                                     # not the broken half of a surrogate pair

    asyncio.run(with_page(scenario))


def test_the_phone_layout_fits_and_a_page_opened_outside_discord_says_what_to_do():
    async def scenario(hub, browser, url):
        for i in range(12):
            hub.backlog.append(message(str(i), f"mensaje largo número {i} " + "palabra " * 30, name="Jugador con un nombre largo"))
        phone = await open_page(browser, url, width=375, height=667, mobile=True)
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")   # no sideways scroll
        me = phone.me
        await hub.qte_start(qte(hub, 1, me, difficulty="hard"))
        await phone.wait_for_selector("[data-testid=qte-widget]")
        await asyncio.sleep(0.4)
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for selector in ("[data-testid=composer]", "[data-testid=actions]", ".qw-btn", "[data-testid=mini-hud]"):
            box = await phone.locator(selector).first.bounding_box()
            assert box and box["y"] >= 0 and box["y"] + box["height"] <= 667 + 1 and box["x"] >= 0 and box["x"] + box["width"] <= 375 + 1, (selector, box)
        evade = await phone.locator(".qw-btn").bounding_box()
        assert evade["height"] >= 80 and evade["width"] >= 80                    # a thumb-sized target
        feed_box = await phone.locator(".feed").bounding_box()
        assert feed_box["height"] > 150 and feed_box["width"] <= 375
        assert await phone.locator("[data-testid=players-panel]").count() == 0     # the phone keeps the compact strip
        if SHOTS:
            await phone.screenshot(path=str(Path(SHOTS) / "activity-phone-qte.png"))

        plain = await browser.new_page()
        await plain.goto(f"{url}/")                                     # no ?dev, not inside Discord
        await plain.wait_for_selector("[data-testid=splash]")
        assert "desde Discord" in await plain.locator("[data-testid=splash]").inner_text()

    asyncio.run(with_page(scenario, actions=True))


def test_the_player_writes_with_the_chosen_identity_and_a_blank_message_is_not_sent():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url)
        acts = hub.test_actions
        box = page.locator("[data-testid=composer] textarea")
        assert not await box.is_disabled()
        await page.click("[data-testid=as-picker]")                                   # the identity selector offers the characters
        assert await page.locator(".as-menu [role=option] .ellipsis").all_inner_texts() == ["Ana (prueba local)", "Kuro", "Shiro"]
        await page.locator(".as-menu [role=option]", has_text="Kuro").click()
        await box.fill("  hola desde la actividad  ")
        await box.press("Enter")
        await page.wait_for_function("document.querySelector('[data-testid=composer] textarea').value === ''")
        await box.fill("   ")
        await box.press("Enter")                                                       # blank: nothing is sent
        await box.fill("línea uno")
        await box.press("Shift+Enter")                                                 # a new line, not a send
        await box.type("línea dos")
        assert await box.input_value() == "línea uno\nlínea dos"
        await asyncio.sleep(0.3)
        assert acts.said == [{"t": "say", "text": "hola desde la actividad", "as": "Kuro"}]
        await page.reload()
        await page.wait_for_selector("[data-testid=composer]")
        assert "Kuro" in await page.locator("[data-testid=as-picker]").inner_text()   # remembered
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


# ======================================================================================================================
def test_a_qte_starts_as_evade_and_turns_into_parry_with_its_timer_on_top():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=760)
        acts = hub.test_actions
        await hub.qte_start(qte(hub, 1, page.me))
        await page.wait_for_selector("[data-testid=qte-widget]")
        await asyncio.sleep(0.35)                                                          # the button has finished popping in
        first = (await widgets(page))[0]
        assert first["kind"] == "evade" and first["phase"] == "evade" and first["state"] == "live"
        assert (await widget(page, 1).locator(".qw-btn").inner_text()).lower() == "esquivar\ne"
        timer = widget(page, 1).locator(".qw-timer")
        assert await timer.is_visible()
        timer_box, button_box = await timer.bounding_box(), await widget(page, 1).locator(".qw-btn").bounding_box()
        assert timer_box["y"] + timer_box["height"] <= button_box["y"] + 1               # the timer is ABOVE the button
        assert float(await timer.locator(".qw-secs").inner_text()) <= 0.8
        # the evade phase drains
        await asyncio.sleep(0.2)
        assert await widget(page, 1).locator(".qw-fill").count() == 1

        # the parry window opens: the widget becomes PARRY, in the very place the Evade button was, with a window bar and the Black Flash band
        await page.wait_for_function("document.querySelector('[data-testid=qte-widget]').dataset.phase === 'parry'", timeout=3000)
        second = (await widgets(page))[0]
        assert second["kind"] == "parry" and (await widget(page, 1).locator(".qw-btn").inner_text()).lower() == "parry\np"
        assert abs(second["x"] - first["x"]) <= 2 and abs(second["y"] - first["y"]) <= 2, (first, second)       # nothing moves under a finger
        assert await widget(page, 1).locator(".qw-zone").count() == 1 and await widget(page, 1).locator(".qw-cursor").count() == 1
        area = await page.locator("[data-arena]").bounding_box()                          # it lands on the chat
        assert area["x"] <= second["x"] and second["x"] + second["w"] <= area["x"] + area["width"] + 1
        assert area["y"] <= second["y"] and second["y"] + second["h"] <= area["y"] + area["height"] + 1

        await tap(widget(page, 1).locator(".qw-btn"))
        await wait_presses(acts, 1)
        press = acts.pressed[0]
        assert press["command"] == "parry" and press["id"] == "1" and 700 <= press["dt"] <= 2700, press     # the screen's own stopwatch
        await page.wait_for_selector('[data-testid=qte-widget][data-result=ok]')
        assert "321" in await widget(page, 1).locator(".qw-result").inner_text() or "0.32" in await widget(page, 1).locator(".qw-result").inner_text()
        await hub.qte_end("1")
        await page.wait_for_selector("[data-testid=qte-widget]", state="detached")
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_pressing_evade_early_answers_with_evade_and_the_widget_shows_the_verdict():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url)
        acts = hub.test_actions
        await hub.qte_start(qte(hub, 5, page.me))
        await page.wait_for_selector("[data-testid=qte-widget]")
        await asyncio.sleep(0.25)
        await tap(widget(page, 5).locator(".qw-btn"))
        await wait_presses(acts, 1)
        assert acts.pressed[0]["command"] == "evade" and 200 <= acts.pressed[0]["dt"] < 790, acts.pressed
        await page.wait_for_selector('[data-testid=qte-widget][data-result=ok]')
        assert "esquivado" in (await widget(page, 5).locator(".qw-result").inner_text()).lower()
        assert await widget(page, 5).locator(".qw-btn").is_disabled()                    # one answer per QTE
        await tap(widget(page, 5).locator(".qw-btn"))
        await asyncio.sleep(0.3)
        assert len(acts.pressed) == 1
        # a refused answer brings the button back
        await hub.qte_end("5")
        await hub.qte_start(qte(hub, 6, page.me))
        await page.wait_for_selector('[data-testid=qte-widget][data-qte="6"]')
        await tap(widget(page, 6).locator(".qw-btn"))
        await wait_presses(acts, 2)
        assert acts.pressed[1]["id"] == "6"

    asyncio.run(with_page(scenario, actions=True))


def test_several_qtes_never_overlap_are_ranked_by_urgency_and_each_button_answers_its_own_qte():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=800)
        acts = hub.test_actions
        for qid, timeout in ((1, 6.0), (2, 3.0), (3, 4.5), (4, 5.0)):
            await hub.qte_start(qte(hub, qid, page.me, timeout=timeout, windows={"evade": [0, 2.0], "parry": [1.9, 2.5], "bf": None}))
        await page.wait_for_function("document.querySelectorAll('[data-testid=qte-widget]').length === 4")
        boxes = await widgets(page)
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert not overlap(a, b), (a, b)                                          # never on top of each other
        ranks = {w["id"]: w["rank"] for w in boxes}
        assert ranks == {"2": "1", "3": "2", "4": "3", "1": "4"}                          # the one about to run out is first
        assert {w["id"] for w in boxes if w["lead"] == "true"} == {"2"}
        # answer the second one first: the press names its QTE
        await tap(widget(page, 3).locator(".qw-btn"))
        await wait_presses(acts, 1)
        assert (acts.pressed[0]["id"], acts.pressed[0]["command"]) == ("3", "evade")
        assert await widget(page, 3).locator(".qw-btn").is_disabled() and not await widget(page, 2).locator(".qw-btn").is_disabled()
        # Space answers the most urgent one
        await page.keyboard.press("Space")
        await wait_presses(acts, 2)
        assert (acts.pressed[1]["id"], acts.pressed[1]["command"]) == ("2", "evade")
        await page.keyboard.press("e")                                                    # then the next most urgent that can
        await wait_presses(acts, 3)
        assert acts.pressed[2]["id"] == "4"
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-multi.png"))
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_a_key_answers_only_the_lead_qte_and_the_timer_goes_away_the_moment_you_press():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=800)
        acts = hub.test_actions
        acts.hold = True                                                                   # the server is slow: no verdict yet
        await hub.qte_start(qte(hub, 1, page.me, timeout=6.0))
        await hub.qte_start(qte(hub, 2, page.me, timeout=3.0))
        await page.wait_for_function("document.querySelectorAll('[data-testid=qte-widget]').length === 2")
        await asyncio.sleep(0.3)
        assert {w["id"] for w in await widgets(page) if w["lead"] == "true"} == {"2"}
        assert await widget(page, 2).locator(".kbd").count() == 1 and await widget(page, 1).locator(".kbd").count() == 0      # only the lead shows its key
        await page.keyboard.press("p")                                                    # the lead is still in its evade phase: a parry key must not fall through to anything else
        await asyncio.sleep(0.3)
        assert acts.pressed == []
        await page.keyboard.press("e")
        await wait_presses(acts, 1)
        assert [(f["id"], f["command"]) for f in acts.pressed] == [("2", "evade")]       # ONE answer, for the lead
        await asyncio.sleep(0.3)
        assert len(acts.pressed) == 1
        assert await widget(page, 2).locator(".qw-timer").count() == 0                   # answered: its bar is gone before any verdict
        assert await widget(page, 1).locator(".qw-timer").count() == 1                   # the other one is still running
        assert {w["id"] for w in await widgets(page) if w["lead"] == "true"} == {"1"}     # and now leads
        assert await widget(page, 1).locator(".kbd").count() == 1
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_a_crowded_phone_screen_shrinks_the_newest_button_instead_of_overlapping():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=375, height=667, mobile=True)
        for qid in range(1, 6):
            await hub.qte_start(qte(hub, qid, page.me, timeout=4.0 + qid * 0.1))
        await page.wait_for_function("document.querySelectorAll('[data-testid=qte-widget]').length === 5")
        boxes = await widgets(page)
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert not overlap(a, b), (a, b)
        assert min(w["w"] for w in boxes) < max(w["w"] for w in boxes)                   # some had to be made smaller
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    asyncio.run(with_page(scenario, actions=True))


def test_somebody_elses_qte_offers_a_rescue_that_respects_the_saves_left():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url)
        acts = hub.test_actions
        await hub.qte_start(qte(hub, 3, "999", target={"id": "999", "name": "Luis"}))
        chip = page.locator("[data-testid=rescue-chip]")
        await chip.wait_for()
        assert "rescatar a luis" in (await chip.inner_text()).lower() and await page.locator("[data-testid=qte-widget]").count() == 0
        assert not await chip.is_disabled()
        await hub.broadcast({"t": "me", "now": hub.now_ms(), "me": {"charges": {"power1": 0, "power2": 0}, "cost": 100, "streak": 0,
                                                                       "saves": {"left": 0, "limit": 2, "until": hub.now_ms() + 20000}, "powers": {}, "domain": False}})
        await page.wait_for_function("document.querySelector('[data-testid=rescue-chip]').disabled")
        assert "sin rescates" in (await chip.inner_text()).lower()
        await hub.broadcast({"t": "me", "now": hub.now_ms(), "me": {"charges": {"power1": 0, "power2": 0}, "cost": 100, "streak": 0,
                                                                       "saves": {"left": 2, "limit": 2, "until": None}, "powers": {}, "domain": False}})
        await page.wait_for_function("!document.querySelector('[data-testid=rescue-chip]').disabled")
        await tap(chip)
        await wait_presses(acts, 1)
        assert (acts.pressed[0]["id"], acts.pressed[0]["command"]) == ("3", "save")
        # the evade window is over: saving late would hurt the saver, so the chip is switched off
        await hub.qte_end("3")
        await hub.qte_start(qte(hub, 4, "999", target={"id": "999", "name": "Luis"}, ago=2.3))
        await page.wait_for_function("document.querySelector('[data-testid=rescue-chip]') && document.querySelector('[data-testid=rescue-chip]').disabled")
        assert "tarde" in (await page.locator("[data-testid=rescue-chip]").inner_text()).lower()

    asyncio.run(with_page(scenario, actions=True))


def test_parry_cooldown_locks_the_parry_button_and_the_counter_window_has_its_own_button():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=800)
        acts = hub.test_actions
        now = hub.now_ms()
        await hub.broadcast({"t": "me", "now": now, "me": {
            "charges": {"power1": 100.0, "power2": 30.0}, "cost": 100, "streak": 0,
            "saves": {"left": 2, "limit": 2, "until": None}, "parryUntil": now + 15000, "counterUntil": now + 4000,
            "powers": {"Kuro": {"power1": {"name": "Rayo", "until": None, "paused": None}, "power2": {"name": "Escudo", "until": now + 30000, "paused": None}}},
            "domain": True}})
        counter = page.locator("[data-testid=counter-widget]")
        await counter.wait_for()
        assert "atacar" in (await counter.inner_text()).lower() and 3.0 <= float(await counter.locator(".qw-secs").inner_text()) <= 4.0
        attack = page.locator("[data-testid=actions] .act[data-cmd=attack]")
        assert "hot" in await attack.get_attribute("class")
        await tap(counter.locator(".qw-btn"))
        await wait_presses(acts, 1)
        assert acts.pressed[0] == {"t": "press", "id": "", "command": "attack", "as": "me"}
        # powers of the character you are playing as, with their cooldowns
        assert (await page.locator("[data-testid=actions] .act[data-cmd=power1] b").inner_text()).lower() == "poder 1"       # as yourself: generic
        await page.click("[data-testid=as-picker]")
        await page.locator(".as-menu [role=option]", has_text="Kuro").click()
        assert (await page.locator("[data-testid=actions] .act[data-cmd=power1] b").inner_text()).lower() == "rayo"
        assert "ready" in await page.locator("[data-testid=actions] .act[data-cmd=power1]").get_attribute("class")
        assert " s" in await page.locator("[data-testid=actions] .act[data-cmd=power2] small").inner_text()          # on cooldown
        assert await page.locator("[data-testid=actions] .act[data-cmd=domain]").count() == 1
        # the parry cooldown locks the parry button when it comes
        await hub.qte_start(qte(hub, 1, page.me, ago=1.0))
        await page.wait_for_function("document.querySelector('[data-testid=qte-widget]').dataset.phase === 'parry'")
        locked = page.locator('[data-testid=qte-widget][data-qte="1"]')
        assert await locked.get_attribute("data-state") == "locked" and await locked.locator(".qw-btn").is_disabled()
        assert "s" in await locked.locator(".sub").inner_text()
        await hub.broadcast({"t": "me", "now": hub.now_ms(), "me": {"charges": {"power1": 0, "power2": 0}, "cost": 100, "streak": 0,
                                                                       "saves": {"left": 2, "limit": 2, "until": None}, "parryUntil": None, "counterUntil": None,
                                                                       "powers": {}, "domain": False}})
        await page.wait_for_function("document.querySelector('[data-testid=qte-widget]').dataset.state === 'live'")
        await page.wait_for_selector("[data-testid=counter-widget]", state="detached")
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_direction_combo_black_flash_chain_and_group_qtes_each_have_their_own_buttons():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=800)
        acts = hub.test_actions
        me = page.me
        # direction: the arrow shown and a pad; the answer is the opposite
        await hub.qte_start(qte(hub, 1, me, mode="direction", windows={"evade": [0.0, 3.0], "bf": None}, timeout=3.0, arrow="⬆️"))
        pad = page.locator(".qw-pad")
        await pad.wait_for()
        assert "OPUESTA" in await page.locator(".qw-hint").inner_text() and await pad.locator("button").count() == 4
        await page.keyboard.press("ArrowDown")
        await wait_presses(acts, 1)
        assert (acts.pressed[0]["command"], acts.pressed[0]["id"]) == ("down", "1")
        await hub.qte_end("1")
        await page.wait_for_selector("[data-testid=qte-widget]", state="detached")

        # combo: the step to do now, pips, and the next step arrives after each answer
        await hub.qte_start(qte(hub, 2, me, mode="combo", windows=None, timeout=15.0,
                                combo={"length": 3, "index": 0, "step": "parry", "limits": [5.0, 10.0, 15.0]}))
        combo = page.locator('[data-testid=qte-widget][data-qte="2"]')
        await combo.wait_for()
        assert await combo.locator(".qw-pips i").count() == 3 and (await combo.locator(".qw-btn").inner_text()).lower() == "parry\np"
        await tap(combo.locator(".qw-btn"))
        await wait_presses(acts, 2)
        assert (acts.pressed[1]["command"], acts.pressed[1]["id"]) == ("parry", "2")
        await hub.send(next(iter(hub.conns.values())), {"t": "qte_step", "id": "2", "index": 1, "step": "evade"})
        await page.wait_for_function("document.querySelector('[data-testid=qte-widget] .qw-btn').dataset.cmd === 'evade'")
        assert await page.locator('[data-testid=qte-widget] .qw-pips i.done').count() == 1
        await hub.qte_end("2")

        # a fake QTE shows nothing
        await hub.qte_start(qte(hub, 3, me, mode="combo", windows=None, target=None, commands=[]))
        await asyncio.sleep(0.3)
        assert await page.locator("[data-testid=qte-widget]").count() == 0 or all(w["id"] != "3" for w in await widgets(page))
        await hub.qte_end("3")

        # a Black Flash chain waits for its window and then offers only the parry
        await hub.qte_start(qte(hub, 4, me, mode="bf_chain", windows={"parry": [0.7, 3.0], "bf": [1.2, 1.5]}, timeout=3.0, chain=2))
        chain = page.locator('[data-testid=qte-widget][data-qte="4"]')
        await chain.wait_for()
        assert await chain.get_attribute("data-state") == "wait" and await chain.locator(".qw-btn").is_disabled()
        await page.wait_for_function("document.querySelector('[data-qte=\"4\"]').dataset.state === 'live'")
        assert await chain.get_attribute("data-kind") == "bf" and "black flash" in (await chain.locator(".qw-meta").inner_text()).lower()
        await hub.qte_end("4")

        # a group QTE: only evade, even though the frame came with a parry window
        await hub.qte_start(qte(hub, 5, me, mode="group", target=None, participants=[me, "999"], windows={"evade": [0.0, 2.0], "bf": None}, commands=["evade"]))
        group = page.locator('[data-testid=qte-widget][data-qte="5"]')
        await group.wait_for()
        await asyncio.sleep(1.0)
        assert await group.get_attribute("data-phase") == "evade" and (await group.locator(".qw-btn").inner_text()).lower() == "esquivar\ne"
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_the_hud_shows_the_boss_the_players_hp_and_your_charges_and_flashes_when_you_are_hurt():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=760)
        me = page.me
        assert await page.locator("[data-testid=boss]").count() == 0                      # nothing to show yet
        hub.state = {"boss": {"name": "Sukuna", "hp": 650, "max": 1000}, "fight": True, "players": [
            {"id": me, "name": "Ana", "hp": 20, "max": 100, "revenge": True}, {"id": "9", "name": "Luis", "hp": 90, "max": 100, "revenge": False}]}
        await hub.broadcast({"t": "state", "s": hub.state})
        await hub.broadcast({"t": "me", "now": hub.now_ms(), "me": {"charges": {"power1": 100.0, "power2": 30.0}, "cost": 100, "streak": 4, "powers": {}, "domain": False}})
        await page.wait_for_selector("[data-testid=boss]")
        boss = await page.locator("[data-testid=boss]").inner_text()
        assert "Sukuna" in boss and "650 / 1000" in boss and "En combate" in boss
        card = page.locator("[data-testid=me-card]")
        assert "20/100" in await card.inner_text() and "REVENGE" in await card.inner_text() and "LISTO" in await card.inner_text() and "30 %" in await card.inner_text()
        assert await card.locator(".bar > i[data-level=low]").count() == 1
        assert await page.locator("[data-testid=players-panel] .player").count() == 2 and await page.locator("[data-testid=players-panel] .player.is-me").count() == 1
        assert "4" in await card.locator(".streak").inner_text()
        # losing HP flashes the screen; healing flashes it green
        hub.state = {**hub.state, "players": [{**hub.state["players"][0], "hp": 12}, hub.state["players"][1]]}
        await hub.broadcast({"t": "state", "s": hub.state})
        await page.wait_for_selector(".fx-hit")
        hub.state = {**hub.state, "players": [{**hub.state["players"][0], "hp": 60}, hub.state["players"][1]]}
        await hub.broadcast({"t": "state", "s": hub.state})
        await page.wait_for_selector(".fx-heal")
        if SHOTS:
            await page.screenshot(path=str(Path(SHOTS) / "activity-hud.png"))
        phone = await open_page(browser, url, name="Luis", width=375, height=667, mobile=True)
        await phone.wait_for_selector("[data-testid=mini-hud]")
        assert await phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.errors == [] and phone.errors == []

    asyncio.run(with_page(scenario, actions=True))


# ======================================================================================================================
def test_settings_apply_at_once_are_remembered_and_sent_to_the_server():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1100, height=800)
        acts = hub.test_actions
        await page.click("[data-testid=settings-button]")
        await page.wait_for_selector("[data-testid=page]")
        root = "document.documentElement"
        await page.locator(".segmented[aria-label=Tema] button", has_text="Muy oscuro").click()
        assert await page.evaluate(f"{root}.dataset.theme") == "oled"
        await page.locator(".segmented[aria-label=Paleta] button", has_text="Daltonismo").click()
        assert await page.evaluate(f"{root}.dataset.palette") == "cb"
        await page.locator(".segmented[aria-label=Espaciado] button", has_text="Compacto").click()
        assert float(await page.evaluate(f"getComputedStyle({root}).getPropertyValue('--density')")) < 1
        slider = page.locator("input[aria-label='Tamaño del texto']")
        await slider.evaluate("el => { el.value = 120; el.dispatchEvent(new Event('input', { bubbles: true })); }")
        assert await page.evaluate(f"{root}.style.getPropertyValue('--text-scale')") == "1.2"
        await page.locator(".segmented[aria-label=Animaciones] button", has_text="Reducidas").click()
        assert await page.evaluate(f"{root}.dataset.motion") == "reduced"
        await page.locator(".segmented[aria-label=Posición] button", has_text="Abajo").click()
        await page.locator("button[role=switch][aria-label='Mantener esquivar']").click()
        await page.locator("button[role=switch][aria-label='Fotos de perfil']").click()
        for _ in range(40):                                                            # sent to the server a moment after the last change
            if acts.prefs:
                break
            await asyncio.sleep(0.1)
        assert acts.prefs["theme"] == "oled" and acts.prefs["palette"] == "cb" and acts.prefs["textScale"] == 120 and acts.prefs["keepEvade"] is True
        assert acts.prefs["buttonPlacement"] == "bottom" and acts.prefs["showAvatars"] is False and acts.prefs["motion"] == "reduced"
        stored = await page.evaluate("JSON.parse(localStorage.getItem('eventos.prefs'))")
        assert stored["theme"] == "oled" and stored["density"] == "compact"

        # fixed at the bottom, with the small evade button kept in the parry phase, and the timer still moving with reduced motion
        await page.click("[data-testid=back-button]")                                    # back to where the gear was pressed: the event
        await page.wait_for_selector("[data-testid=composer]")
        await hub.qte_start(qte(hub, 1, page.me, ago=1.0))
        await page.wait_for_selector("[data-testid=qte-widget]")
        await page.wait_for_function("document.querySelector('[data-testid=qte-widget]').dataset.phase === 'parry'")
        box = (await widgets(page))[0]
        area = await page.locator("[data-arena]").bounding_box()
        assert box["y"] > area["y"] + area["height"] / 2                                   # low on the screen
        assert abs((box["x"] + box["w"] / 2) - (area["x"] + area["width"] / 2)) < 30     # and centred
        assert await page.locator(".qw-alt").count() == 1                                  # evade stays while its window is still open
        duration = await page.locator(".qw-cursor").evaluate("el => getComputedStyle(el).animationDuration")
        assert duration != "0.001s" and duration != "1e-3s"                                # reduced motion does not freeze the timer

        # a reload keeps the look before the server even answers
        await page.reload()
        await page.wait_for_selector("[data-testid=composer]")
        assert await page.evaluate(f"{root}.dataset.theme") == "oled"
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_the_latency_test_measures_the_connection_and_the_device_and_the_server_is_told():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url, width=1000, height=760, init="window.__fastLatency = true")
        acts = hub.test_actions
        await page.click("[data-testid=menu-button]")
        await page.click("[data-testid=tile-latency]")
        await page.click("[data-testid=start-test]")
        await page.wait_for_selector("[data-testid=net-result]", timeout=8000)
        assert "tu conexión" in (await page.locator("[data-testid=net-result]").inner_text()).lower()
        await page.click("[data-testid=start-tap]")
        await page.wait_for_selector(".tap-target")
        # tap along with each flash, like a person with a quick, accurate hand
        deadline = asyncio.get_running_loop().time() + 8
        seen = None
        while asyncio.get_running_loop().time() < deadline and await page.locator("[data-testid=result-step]").count() == 0:
            flash = await page.evaluate("document.querySelector('.tap-target')?.dataset.flash ?? null")
            if flash in ("0", "1"):
                token = (flash, await page.evaluate("performance.now() | 0") // 150)
                if token != seen:
                    seen = token
                    # one call for looking and pressing: the circle vanishes by itself when the last flash is done
                    await page.evaluate("document.querySelector('.tap-target')?.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, pointerType: 'mouse'}))")
            await asyncio.sleep(0.01)
        await page.wait_for_selector("[data-testid=result-step]", timeout=4000)
        assert acts.latency is not None and acts.latency["taps"] >= 4 and 0 <= acts.latency["device"] <= 150
        assert acts.latency["median"] is not None and acts.latency["loss"] == 0
        assert "ms" in await page.locator("[data-testid=adj-net]").inner_text()
        assert await page.evaluate("window.__eventos.comp.device") == acts.latency["device"]          # the server's answer is applied
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_the_tutorial_teaches_with_a_practice_qte_that_never_reaches_the_server():
    async def scenario(hub, browser, url):
        acts = hub.test_actions
        acts.tutorial_done = False
        page = await open_page(browser, url, width=1100, height=760)
        await page.wait_for_selector("[data-testid=tutorial]", timeout=6000)                # it starts by itself the first time
        assert "bienvenido" in (await page.locator("[data-testid=tutorial]").inner_text()).lower()
        await page.click("[data-testid=tutorial-next]")                                      # el canal
        await page.click("[data-testid=tutorial-next]")                                      # escribir
        await page.click("[data-testid=tutorial-next]")                                      # práctica: esquivar
        await page.wait_for_selector('[data-testid=qte-widget][data-kind=evade]', timeout=3000)
        await asyncio.sleep(0.2)
        await tap(page.locator("[data-testid=qte-widget] .qw-btn"))
        await page.wait_for_selector('[data-testid=tutorial-verdict].ok', timeout=3000)
        assert "esquivar vale" in (await page.locator("[data-testid=tutorial-verdict]").inner_text()).lower()
        await page.click("[data-testid=tutorial-next]")                                      # práctica: parry
        await page.wait_for_selector('[data-testid=tutorial-verdict].bad', timeout=9000)    # let it run out: it says so, nobody is hurt
        assert "se acabó" in (await page.locator("[data-testid=qte-widget] .qw-result").inner_text()).lower()
        await page.locator("[data-testid=tutorial-verdict] button").click()                  # otra vez
        await page.wait_for_selector('[data-testid=qte-widget][data-kind=parry]', timeout=4000)
        await asyncio.sleep(0.2)
        await tap(page.locator("[data-testid=qte-widget] .qw-btn"))
        await page.wait_for_selector('[data-testid=tutorial-verdict].ok', timeout=3000)
        assert acts.pressed == []                                                            # nothing was sent: it is practice
        for _ in range(3):
            await page.click("[data-testid=tutorial-next]")
        await page.click("[data-testid=tutorial-finish]")
        await page.wait_for_selector("[data-testid=tutorial]", state="detached")
        for _ in range(40):
            if acts.prefs:
                break
            await asyncio.sleep(0.1)
        assert acts.prefs and acts.prefs["tutorialDone"] is True
        # and it can be opened again from the menu
        await page.click("[data-testid=menu-button]")
        await page.click("[data-testid=tile-tutorial]")
        await page.wait_for_selector("[data-testid=tutorial]")
        await page.click("[data-testid=tutorial-close]")
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))


def test_keyboard_shortcuts_do_not_fire_while_typing_and_the_menu_pages_open_and_close():
    async def scenario(hub, browser, url):
        page = await open_page(browser, url)
        acts = hub.test_actions
        await hub.qte_start(qte(hub, 1, page.me, timeout=3.0))
        await page.wait_for_selector("[data-testid=qte-widget]")
        box = page.locator("[data-testid=composer] textarea")
        await box.click()
        await page.keyboard.type("aqe")                                                        # letters typed in the box are letters
        assert len(acts.pressed) == 0 and await box.input_value() == "aqe"
        await page.keyboard.press("Alt+e")                                                     # Alt + letter works even there
        await wait_presses(acts, 1)
        await page.keyboard.press("Escape")                                                    # leaves the box
        assert await page.evaluate("document.activeElement.tagName") == "BODY"
        await hub.qte_end("1")

        await page.click("[data-testid=menu-button]")
        assert "prueba de latencia" in (await page.locator("[data-testid=page]").inner_text()).lower()
        assert await page.locator("[data-testid=tile-achievements]").count() == 1                 # and the player's own things, above them
        await page.click("[data-testid=tile-help]")
        text = await page.locator("[data-testid=page]").inner_text()
        assert "reglas de los qte" in text.lower() and "espacio" in text.lower()
        await page.keyboard.press("Escape")                                                    # help -> menu
        await page.wait_for_selector("[data-testid=tile-help]")
        await page.keyboard.press("Escape")                                                    # menu -> event
        await page.wait_for_selector("[data-testid=composer]")
        assert await page.evaluate("window.__eventos.view") == "event"
        assert page.errors == []

    asyncio.run(with_page(scenario, actions=True))
