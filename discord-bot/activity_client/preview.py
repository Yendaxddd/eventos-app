"""Development tool: runs the Activity against made-up game data and takes screenshots of it, so the interface can be
looked at without Discord.   python activity_client/preview.py <folder> [scenario ...]

Not shipped with the app."""
import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright  # noqa: E402

from eventos_app.activity import ActivityServer, DiscordAuth, Hub  # noqa: E402

WEB = ROOT / "eventos_app" / "activity" / "web"
RULES = {"times": {
    "easy": {"evade": 6.0, "parry": [4.0, 7.0], "perfect": 5.5, "timeout": 6.75},
    "medium": {"evade": 4.5, "parry": [3.0, 5.0], "perfect": 4.0, "timeout": 5.0},
    "hard": {"evade": 4.0, "parry": [2.5, 4.5], "perfect": 3.5, "timeout": 5.75},
    "impossible": {"evade": 1.5, "parry": [0.8, 1.7], "perfect": 1.25, "timeout": 3.5}},
    "bfWindow": 0.2, "chainWindow": 0.15, "counterWindow": 5.0, "saveLimit": 2, "saveWindow": 60, "ultimateCost": 100}
WIN = {"evade": [0.0, 4.5], "parry": [3.0, 5.0], "bf": [3.8, 4.2]}


def picture() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 320), "#1b1033")
    draw = ImageDraw.Draw(img)
    for i in range(0, 640, 8):
        draw.line([(i, 0), (320 + (i - 320) * 0.4, 320)], fill=(60 + i // 5, 30, 120), width=3)
    draw.ellipse([220, 60, 420, 260], outline="#c084fc", width=8)
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    return buffer.getvalue()


def message(mid, text, name="Ana", color="#ff8800", bot=False, webhook=False, ours=False, embeds=(), reactions=(), reply=None, ts=1767225600000):
    return {"id": str(mid), "ts": ts, "edited": False, "text": text, "attachments": [], "embeds": list(embeds), "stickers": [],
            "reactions": list(reactions), "reply": reply,
            "author": {"id": str(abs(hash(name)) % 10**6), "name": name, "avatar": "", "bot": bot, "webhook": webhook, "ours": ours, "color": color}}


BACKLOG = [
    message(1, "# 🔥 **COMBO QTE!** 🔥\n**MEDIUM** 🟡 | @Ana\n⚡ Complete **5 QTEs** in sequence!", name="Events and fun Bot", bot=True, color=""),
    message(2, "Ahí voy… *respira hondo* y abre los ojos. No pienso retroceder.", name="Kuro", webhook=True, color=""),
    message(3, "**¡Cuidado!** el jefe carga algo grande", name="Luis", color="#38bdf8"),
    message(4, "", name="Events and fun Bot", bot=True, color="", embeds=[{
        "title": "⚡💥 BLACK FLASH! 💥⚡", "description": "**Ana** landed a **PERFECT BLACK FLASH!**\n\n💢 **25 DAMAGE!**\n🌀 Enemy stunned for 1s!",
        "color": "#8a2be2", "url": "", "image": "https://cdn.discordapp.com/attachments/1/2/bf.png", "thumb": "", "video": "", "author": "", "footer": "Black Flash Chance: 3.0% | Response Time: 3.98s",
        "fields": []}], reactions=[{"emoji": {"name": "❗"}, "count": 1}, {"emoji": {"name": "✅"}, "count": 2}]),
    message(5, "jajaja qué buen parry", name="Beto", color="#34d399", reply={"author": "Ana", "text": "Ahí voy… respira hondo"}),
    message(6, "⚔️ <@1> **parried!** [PERFECT] (3.98s)\n```\nHP 97/100\n```", name="Events and fun Bot", bot=True, color=""),
    message(7, "💔 **Luis** took 3 damage! HP: 97/100", name="Events and fun Bot", bot=True, color=""),
]
STATE = {"boss": {"name": "𝕋𝕣𝕦𝕖 𝕡𝕠𝕥𝕖𝕟𝕥𝕚𝕒𝕝 — Anomaly SU14Y-U", "hp": 675, "max": 1000}, "fight": True,
         "players": [{"id": "USER", "name": "Ana (prueba local)", "hp": 62, "max": 100, "revenge": False},
                     {"id": "2", "name": "Luis", "hp": 97, "max": 100, "revenge": False},
                     {"id": "3", "name": "Beto", "hp": 18, "max": 100, "revenge": True}]}


class Actions:
    def __init__(self, hub):
        self.hub, self.said, self.pressed, self.prefs, self.latency = hub, [], [], None, None
        self.tutorial_done = True

    def characters_of(self, user_id):
        return ["Kuro", "Shiro"]

    def me_of(self, user_id):
        return {"charges": {"power1": 100.0, "power2": 42.0}, "cost": 100, "streak": 4,
                "saves": {"left": 2, "limit": 2, "until": None}, "parryUntil": None, "counterUntil": None,
                "powers": {"Kuro": {"power1": {"name": "Corte Abismal", "until": None, "paused": None}, "power2": {"name": "Muro", "until": None, "paused": None}}},
                "domain": True}

    async def welcome_extras(self, conn):
        return {"perms": {"gm": bool(conn.gm)}, "prefs": {"tutorialDone": self.tutorial_done}, "calib": None, "comp": {"net": 24.0, "device": 0.0, "cap": 300},
                "rules": RULES, "charAvatars": {}}

    async def save_prefs(self, conn, prefs):
        self.prefs = prefs

    async def save_latency(self, conn, result):
        self.latency = result
        return result, {"net": 21.0, "device": float((result or {}).get("device") or 0), "cap": 300}

    async def say(self, conn, frame):
        self.said.append(frame)

    async def press(self, conn, frame):
        self.pressed.append(frame)
        await self.hub.send(conn, {"t": "qte_result", "id": frame.get("id"), "ok": True, "ms": 3980, "reactions": ["✅"]})


def qte(hub, qid, target, mode="single", difficulty="medium", ago=0.0, **extra):
    commands = {"single": ["evade", "parry", "save", "adapt"], "group": ["evade"], "combo": ["evade", "parry"],
                "direction": ["up", "down", "left", "right"], "bf_chain": ["parry"]}[mode]
    frame = {"id": str(qid), "mode": mode, "difficulty": difficulty, "target": target, "participants": [], "tGo": hub.now_ms() - ago * 1000,
             "timeout": 5.0, "windows": WIN, "commands": commands}
    frame.update(extra)
    return frame


async def run(out: Path, only: list[str]):
    hub = Hub()
    hub.channel_name = "borrador-para-los-qte"
    hub.backlog.extend(BACKLOG)
    hub.state = STATE
    actions = Actions(hub)
    png = picture()

    async def media(url):
        return "image/png", png

    server = ActivityServer(hub, auth=DiscordAuth(client_id=1, client_secret="x"), authorize=None, web_dir=WEB, client_id=1, port=0,
                            actions=actions, media_fetch=media, media_dir=Path(tempfile.mkdtemp()))
    port = await server.start()
    base = f"http://127.0.0.1:{port}"
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        exe = next(iter(sorted(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome"))), None)
        browser = await p.chromium.launch(executable_path=str(exe) if exe else None, args=["--no-sandbox"])

        async def open_page(width, height, mobile=False, gm=False, name="Ana", prefs=None):
            context = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2 if mobile else 1,
                                                is_mobile=mobile, has_touch=mobile)
            page = await context.new_page()
            page.on("pageerror", lambda e: print("PAGE ERROR:", e))
            page.on("console", lambda m: print("console:", m.text) if m.type == "error" else None)
            if prefs is not None:
                await page.add_init_script("localStorage.setItem('eventos.prefs', JSON.stringify(%s))" % prefs)
            await page.goto(f"{base}/?dev={name}{'&gm=1' if gm else ''}")
            await page.wait_for_selector("[data-testid=composer]", timeout=8000)
            await page.evaluate("document.documentElement.classList.add('preview')")
            return page

        async def shot(page, name):
            await page.screenshot(path=str(out / f"{name}.png"))
            print("saved", name)

        async def tap_first(page):
            await page.locator("[data-testid=qte-widget] .qw-btn").first.dispatch_event("pointerdown", {"button": 0, "pointerType": "mouse"})

        wanted = lambda n: not only or n in only   # noqa: E731
        done = {"tutorialDone": True}
        pref_done = '{"tutorialDone": true}'

        if wanted("desktop"):
            page = await open_page(1280, 760, prefs=pref_done)
            me = await page.evaluate("window.__eventos.you.id")
            hub.state = {**STATE, "players": [{**pl, "id": me if pl["id"] == "USER" else pl["id"]} for pl in STATE["players"]]}
            await hub.broadcast({"t": "state", "s": hub.state})
            await asyncio.sleep(0.5)
            await shot(page, "01-desktop-idle")
            target = {"id": me, "name": "Ana"}
            await hub.qte_start(qte(hub, 1, target, ago=0.4))
            await asyncio.sleep(0.5)
            await shot(page, "02-desktop-evade")
            await asyncio.sleep(2.7)
            await shot(page, "03-desktop-parry")
            await hub.qte_end("1")
            await hub.qte_start(qte(hub, 2, target, ago=1.0, difficulty="hard"))
            await hub.qte_start(qte(hub, 3, target, ago=0.5, difficulty="easy", timeout=6.75, windows={"evade": [0, 6.0], "parry": [4.0, 7.0], "bf": [5.3, 5.7]}))
            await hub.qte_start(qte(hub, 4, {"id": "2", "name": "Luis"}, ago=0.2))
            await asyncio.sleep(0.6)
            await shot(page, "04-desktop-three")
            await page.context.close()

        if wanted("phone"):
            page = await open_page(390, 800, mobile=True, prefs=pref_done)
            me = await page.evaluate("window.__eventos.you.id")
            hub.state = {**STATE, "players": [{**pl, "id": me if pl["id"] == "USER" else pl["id"]} for pl in STATE["players"]]}
            await hub.broadcast({"t": "state", "s": hub.state})
            await asyncio.sleep(0.5)
            await shot(page, "10-phone-idle")
            await hub.qte_start(qte(hub, 11, {"id": me, "name": "Ana"}, ago=0.3))
            await asyncio.sleep(0.5)
            await shot(page, "11-phone-evade")
            await page.context.close()

        if wanted("pages"):
            page = await open_page(1100, 760, prefs=pref_done)
            for name, tid in (("20-menu", "menu-button"), ("21-settings", "tile-settings"), ("22-latency", "settings-button")):
                pass
            await page.click("[data-testid=menu-button]")
            await asyncio.sleep(0.4)
            await shot(page, "20-menu")
            await page.click("[data-testid=tile-settings]")
            await asyncio.sleep(0.4)
            await shot(page, "21-settings")
            await page.evaluate("document.querySelector('.page-body').scrollTop = 900")
            await asyncio.sleep(0.2)
            await shot(page, "22-settings-2")
            await page.click("[data-testid=back-button]")
            await page.click("[data-testid=tile-latency]")
            await asyncio.sleep(0.4)
            await shot(page, "23-latency")
            await page.click("[data-testid=start-test]")
            await asyncio.sleep(2.0)
            await shot(page, "24-latency-running")
            await page.context.close()

        if wanted("modes"):
            page = await open_page(1100, 780, prefs=pref_done)
            me = await page.evaluate("window.__eventos.you.id")
            hub.state = {**STATE, "players": [{**pl, "id": me if pl["id"] == "USER" else pl["id"]} for pl in STATE["players"]]}
            await hub.broadcast({"t": "state", "s": hub.state})
            target = {"id": me, "name": "Ana"}
            await hub.qte_start(qte(hub, 20, target, mode="direction", windows={"evade": [0.0, 4.0], "bf": None}, timeout=4.0, arrow="⬆️"))
            await asyncio.sleep(0.5)
            await shot(page, "40-direction")
            await hub.qte_end("20")
            await hub.qte_start(qte(hub, 21, target, mode="combo", windows=None, timeout=15.0, combo={"length": 5, "index": 1, "step": "parry", "limits": [5, 10, 15, 20, 25]}, ago=2.0))
            await asyncio.sleep(0.5)
            await shot(page, "41-combo")
            await hub.qte_end("21")
            await hub.qte_start(qte(hub, 22, target, mode="bf_chain", windows={"parry": [1.0, 3.0], "bf": [1.7, 2.0]}, timeout=3.0, chain=2))
            await asyncio.sleep(0.4)
            await shot(page, "42-chain-wait")
            await asyncio.sleep(1.3)
            await shot(page, "43-chain-live")
            await hub.qte_end("22")
            now = hub.now_ms()
            await hub.broadcast({"t": "me", "now": now, "me": {"charges": {"power1": 100.0, "power2": 42.0}, "cost": 100, "streak": 4,
                                 "saves": {"left": 1, "limit": 2, "until": None}, "parryUntil": None, "counterUntil": now + 4200, "powers": {}, "domain": True}})
            await hub.qte_start(qte(hub, 23, {"id": "2", "name": "Luis"}, ago=0.5))
            await hub.qte_start(qte(hub, 24, {"id": "3", "name": "Beto"}, ago=1.5))
            await asyncio.sleep(0.6)
            await shot(page, "44-counter-rescue")
            await page.context.close()
            page = await open_page(1100, 780, prefs=pref_done)
            me = await page.evaluate("window.__eventos.you.id")
            await hub.qte_start(qte(hub, 30, {"id": me, "name": "Ana"}, ago=0.2))
            await asyncio.sleep(0.5)
            await tap_first(page)
            await asyncio.sleep(0.4)
            await shot(page, "45-result-ok")
            await page.context.close()

        if wanted("crowd"):
            page = await open_page(390, 800, mobile=True, prefs=pref_done)
            me = await page.evaluate("window.__eventos.you.id")
            hub.state = {**STATE, "players": [{**pl, "id": me if pl["id"] == "USER" else pl["id"]} for pl in STATE["players"]]}
            await hub.broadcast({"t": "state", "s": hub.state})
            for qid in range(40, 45):
                await hub.qte_start(qte(hub, qid, {"id": me, "name": "Ana"}, timeout=4.0 + (qid - 40) * 0.3, ago=0.1))
            await asyncio.sleep(0.7)
            await shot(page, "50-phone-crowd")
            await page.click("[data-testid=players-button]")
            await asyncio.sleep(0.5)
            await shot(page, "51-phone-sheet")
            await page.context.close()

        if wanted("tutorial"):
            actions.tutorial_done = False
            page = await open_page(1100, 760)
            await asyncio.sleep(3.0)
            await shot(page, "30-tutorial-0")
            for i in range(1, 5):
                await page.click("[data-testid=tutorial-next]")
                await asyncio.sleep(1.4)
                await shot(page, f"3{i}-tutorial-{i}")
            await page.context.close()
        await browser.close()
    await server.stop()


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("preview-shots")
    asyncio.run(run(folder, sys.argv[2:]))
