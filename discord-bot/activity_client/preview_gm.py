"""Development tool: the game-master panel of the Activity, driven by the real bridge over a made-up bot, with screenshots.
    python activity_client/preview_gm.py <folder> [desktop|phone]
Not shipped with the app."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from playwright.async_api import async_playwright  # noqa: E402

from eventos_app.activity.server import dev_identity  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402

WEB = ROOT / "eventos_app" / "activity" / "web"
TABS = ["event", "boss", "players", "values", "data", "history"]
PIXEL = __import__("base64").b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def seed(rig):
    app = rig.app
    app.active_boss = {"name": "Rey de las Maldiciones", "hp_current": 640, "hp_max": 1000, "gif_url": "https://cdn.discordapp.com/boss.png", "participants": set()}
    app.fight_active = True
    app.active_qtes[7] = {"mode": "single", "difficulty": "hard", "target": app.qte_players[1]}
    app.session_stats.update({"qtes_triggered": 14, "black_flashes_today": 3})
    app.afk_users.add(OTHER)
    app.player_hp[ME]["current"] = 38
    config = app.tupperbox_boss_config
    config.update({"character_name": "Sukuna", "boss_hp": 2500, "evade_chance": 0.15, "counter_chance": 0.2, "counter_damage": 20,
                   "abilities": {"Desmantelar": {"damage": 30, "gif": "https://cdn.discordapp.com/a.png"}, "Santuario": {"damage": 55, "gif": None}},
                   "status_inflict": {"Santuario": {"status": "burn", "chance": 60, "duration": 45}},
                   "evade_gifs": ["https://cdn.discordapp.com/e1.png", "https://cdn.discordapp.com/e2.png"], "counter_gifs": ["https://cdn.discordapp.com/c1.png"],
                   "domain": {"name": "Santuario Malévolo", "type": "dps", "duration": 40, "effect_value": 12, "gif": None}})
    app.boss_defeat_gifs = ["https://cdn.discordapp.com/d1.png"]
    pending = app.special_objects_manager.pending_path
    (pending / "moon_charm.json").write_text(json.dumps({"id": "moon_charm", "name": "Amuleto lunar", "type": "passive", "rarity": "rare", "description": "Brilla de noche.", "effects": []}), encoding="utf-8")
    (pending / "roto.json").write_text(json.dumps({"id": "roto", "name": "Objeto roto", "type": "arma", "rarity": "raro"}), encoding="utf-8")
    rig.bridge.gm.log.add("Ana", "Lanzó un QTE individual (difícil) a Mina")
    rig.bridge.gm.log.add("Gus", "Puso la vida de Mina en 40/120")
    rig.bridge.gm.log.add("Ana", "Registró al jefe «Rey de las Maldiciones» con 1000 HP")


async def shot(page, out, name, pause=0.6):
    await asyncio.sleep(pause)
    await page.screenshot(path=str(out / f"{name}.png"))
    print("saved", name)


async def main(out: Path, only: list[str]):
    out.mkdir(parents=True, exist_ok=True)
    me = dev_identity("Ana")[0]
    rig = GmRig(me=me)
    rig.web_dir = WEB                                    # before it starts: the static files are routed when the server starts
    async with rig:
        seed(rig)

        async def media(url):
            return "image/png", PIXEL
        rig.server._media_fetch = media
        base = f"http://127.0.0.1:{rig.port}"
        async with async_playwright() as p:
            exe = next(iter(sorted(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome"))), None)
            browser = await p.chromium.launch(executable_path=str(exe) if exe else None, args=["--no-sandbox"])
            for label, (w, h, mobile) in (("desktop", (1280, 860, False)), ("phone", (390, 800, True))):
                if only and label not in only:
                    continue
                context = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
                page = await context.new_page()
                page.on("pageerror", lambda e: print("PAGE ERROR:", e))
                page.on("console", lambda m: print("console:", m.text) if m.type == "error" else None)
                await page.add_init_script("localStorage.setItem('eventos.prefs', JSON.stringify({tutorialDone: true}))")
                await page.goto(f"{base}/?dev=Ana&gm=1")
                await page.wait_for_selector("[data-testid=composer]", timeout=8000)
                await page.click("[data-testid=menu-button]")
                await shot(page, out, f"{label}-menu", 0.4)
                await page.click("[data-testid=tile-gm]")
                for tab in TABS:
                    await page.click(f"[data-testid=gm-tab-{tab}]")
                    await shot(page, out, f"{label}-{tab}", 0.9)
                    if tab in ("boss", "values", "data"):                                   # the long pages: also lower down
                        body = page.locator(".dash-body")
                        await body.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                        await shot(page, out, f"{label}-{tab}-end", 0.4)
                        await body.evaluate("el => el.scrollTo(0, 0)")
                # a person
                await page.click("[data-testid=gm-tab-players]")
                await page.click(f"[data-testid=gm-player-{ME}]")
                await shot(page, out, f"{label}-person", 0.9)
                await page.locator(".dash-body").evaluate("el => el.scrollTo(0, el.scrollHeight)")
                await shot(page, out, f"{label}-person-end", 0.4)
                # dialogs
                await page.click("[data-testid=gm-tab-boss]")
                await page.click("[data-testid=gm-ability-new]")
                await shot(page, out, f"{label}-ability-dialog", 0.5)
                await page.keyboard.press("Escape")
                await page.click("[data-testid=gm-tab-data]")
                await page.click("[data-testid=gm-ach-new]")
                await shot(page, out, f"{label}-achievement-dialog", 0.5)
                await page.keyboard.press("Escape")
                await page.click("[data-testid=gm-section-objects]")
                await shot(page, out, f"{label}-objects", 0.8)
                await page.click("[data-testid=gm-section-files]")
                await page.select_option("[data-testid=gm-file-select]", "achievements")
                await shot(page, out, f"{label}-files", 1.0)
                await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:]))
