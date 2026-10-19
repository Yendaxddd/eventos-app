"""Development tool: the player's dashboards of the Activity, driven by the real bridge over made-up game data, with screenshots.
    python activity_client/preview_panel.py <folder> [desktop|phone|...]
Not shipped with the app."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from playwright.async_api import async_playwright  # noqa: E402

from eventos_app.activity.server import dev_identity  # noqa: E402
from test_activity_panel import PanelRig  # noqa: E402

WEB = ROOT / "eventos_app" / "activity" / "web"
TABS = ["summary", "achievements", "characters", "skills", "inventory", "images", "ranking"]


async def main(out: Path, only: list[str]):
    out.mkdir(parents=True, exist_ok=True)
    me = dev_identity("Ana")[0]
    rig = PanelRig(me=me)
    rig.web_dir = WEB                                    # before it starts: the static files are routed when the server starts
    async with rig:
        rig.app.user_counter_gifs[me] = ["https://cdn.discordapp.com/a.png", "https://cdn.discordapp.com/b.png"]
        png = __import__("base64").b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

        async def media(url):
            return "image/png", png
        rig.server._media_fetch = media
        base = f"http://127.0.0.1:{rig.port}"
        async with async_playwright() as p:
            exe = next(iter(sorted(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome"))), None)
            browser = await p.chromium.launch(executable_path=str(exe) if exe else None, args=["--no-sandbox"])
            for label, (w, h, mobile) in (("desktop", (1280, 800, False)), ("phone", (390, 800, True))):
                if only and label not in only:
                    continue
                context = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
                page = await context.new_page()
                page.on("pageerror", lambda e: print("PAGE ERROR:", e))
                page.on("console", lambda m: print("console:", m.text) if m.type == "error" else None)
                await page.add_init_script("localStorage.setItem('eventos.prefs', JSON.stringify({tutorialDone: true}))")
                await page.goto(f"{base}/?dev=Ana")
                await page.wait_for_selector("[data-testid=composer]", timeout=8000)
                await page.click("[data-testid=menu-button]")
                await asyncio.sleep(0.4)
                await page.screenshot(path=str(out / f"{label}-menu.png"))
                await page.click("[data-testid=tile-summary]")
                for tab in TABS:
                    await page.click(f"[data-testid=dash-tab-{tab}]")
                    await asyncio.sleep(0.7)
                    await page.screenshot(path=str(out / f"{label}-{tab}.png"))
                    print("saved", label, tab)
                # dialogs
                await page.click("[data-testid=dash-tab-characters]")
                await page.click("[data-testid=power-edit-Kuro-1]")
                await asyncio.sleep(0.5)
                await page.screenshot(path=str(out / f"{label}-power-editor.png"))
                await page.keyboard.press("Escape")
                await page.click("[data-testid=dash-tab-skills]")
                await page.click("[data-testid=skill-combat_2a]")
                await asyncio.sleep(0.5)
                await page.screenshot(path=str(out / f"{label}-skill-dialog.png"))
                await page.keyboard.press("Escape")
                await page.click("[data-testid=dash-tab-ranking]")
                rig.app.player_stats[444] = {"total_attempts": 5, "successful": 5, "black_flashes": 9, "saves": 1}
                rig.bridge._names[444] = (10**12, "Beto", None)
                await page.click("[data-testid=board-tab-black_flashes]")
                await asyncio.sleep(0.6)
                await page.screenshot(path=str(out / f"{label}-podium.png"))
                await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:]))
