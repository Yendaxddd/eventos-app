"""The real client in a real (headless) Chromium: sign-in, mirrored messages, escaping, clock sync, phone layout.

Skipped when the client has not been built (`npm run build` in activity_client/) or Playwright's Chromium is missing.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

WEB = Path(__file__).resolve().parents[1] / "eventos_app" / "activity" / "web"
playwright_api = pytest.importorskip("playwright.async_api")
pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity import ActivityServer, DiscordAuth, Hub  # noqa: E402

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


async def with_page(scenario):
    hub = Hub()
    hub.channel_name = "qte-evento"
    server = ActivityServer(hub, auth=DiscordAuth(client_id=1, client_secret="x"), authorize=None, web_dir=WEB,
                            client_id=1, port=0)
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
