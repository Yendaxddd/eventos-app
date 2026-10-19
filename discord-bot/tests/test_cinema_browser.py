"""Cinematics in a real (headless) Chromium: a game master writes one in the panel, plays it, and every player's screen shows it with its
sound at the right moments; the channel message is written; a player can skip it or switch cinematics off."""
import asyncio
import io
import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import PIXEL, WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity import media  # noqa: E402
from test_activity_gm_browser import gm_page, run, until  # noqa: E402
from test_audio_browser import LISTEN, heard, wait_heard  # noqa: E402


def wav(seconds=0.3, rate=8000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return out.getvalue()


def test_a_game_master_writes_a_cinematic_and_every_screen_plays_it_with_its_sound_and_its_message(tmp_path):
    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
        rig.bridge.cinema.book.path = tmp_path / "cinematics.json"
        rig.server.files = store
        sound = rig.bridge.audio.library.add("rugido.wav", wav(), "sfx")
        posted = []

        async def send(content=None, **kwargs):
            posted.append(content)
        rig.channel.send = send

        player = await open_page(browser, url, name="Luis", init=LISTEN)
        await player.mouse.click(5, 5)
        page = await gm_page(browser, url, tab="cinema")

        # write it
        await page.click("[data-testid=cine-new]")
        await page.wait_for_selector("[data-testid=cine-editor]")
        await page.fill("[data-testid=cine-name]", "Llegada del Rey")
        await page.click("[data-testid=cine-trigger-boss_defeated]")
        await page.fill("[data-testid=cine-text-1]", "Así que habéis venido a morir.")
        await page.fill("[data-testid=cine-speaker-1]", "Rey de las Maldiciones")
        await page.fill("[data-testid=cine-at-1]", "0.3")
        await page.fill("[data-testid=cine-at-0]", "0")
        await page.click("[data-testid=cine-add-audio]")
        await page.select_option("[data-testid=cine-sound-2]", sound["id"])
        await page.fill("[data-testid=cine-at-2]", "0.1")
        await page.click("[data-testid=cine-add-effect]")
        await page.fill("[data-testid=cine-at-3]", "0.5")
        await page.click("[data-testid=cine-add-post]")
        await page.fill("[data-testid=cine-post-4]", "⚔️ El rey desenvaina su espada.")
        await page.fill("[data-testid=cine-at-4]", "0.6")
        assert await page.locator("[data-testid=cine-timeline] .cine-mark").count() == 5

        # a bad script is refused with the step named
        await page.fill("[data-testid=cine-text-1]", "")
        await page.click("[data-testid=cine-save]")
        await page.locator(".toast", has_text="texto está vacío").first.wait_for(timeout=4000)
        await page.fill("[data-testid=cine-text-1]", "Así que habéis venido a morir.")

        # preview on the editor's own screen
        await page.click("[data-testid=cine-preview]")
        await page.wait_for_selector("[data-testid=cine]")
        assert "Vista previa" in await page.locator(".cine-controls").inner_text()
        await page.click("[data-testid=cine-skip]")
        await page.wait_for_selector("[data-testid=cine]", state="detached")
        assert (await heard(player))["sources"] == 0 and posted == []                       # a preview is private: nobody else hears or reads it

        await page.click("[data-testid=cine-save]")
        await page.wait_for_selector("[data-testid=cine-list]")
        saved = rig.bridge.cinema.book.listing()
        assert len(saved) == 1 and saved[0]["triggers"] == ["boss_defeated"] and [s["type"] for s in saved[0]["steps"]] == ["scene", "audio", "text", "effect", "post"]
        cid = saved[0]["id"]

        # everybody plays it
        await page.click(f"[data-testid=cine-play-{cid}]")
        await player.wait_for_selector("[data-testid=cine]")
        await player.wait_for_selector("[data-testid=cine-caption]", timeout=3000)
        await wait_heard(player, sources=1)
        await until(lambda: posted == ["⚔️ El rey desenvaina su espada."], "the channel message")
        assert "rey de las maldiciones" in (await player.locator("[data-testid=cine-caption]").inner_text()).lower()
        await player.wait_for_function("document.querySelector('[data-testid=cine-caption] p').textContent.includes('morir')", timeout=3000)       # it types itself out
        assert await player.locator(".cine-bar").count() == 2
        await page.click(f"[data-testid=cine-stop-{cid}]")
        await player.wait_for_selector("[data-testid=cine]", state="detached", timeout=3000)

        # a player may skip it for themselves, and may switch cinematics off
        await page.click(f"[data-testid=cine-play-{cid}]")
        await player.wait_for_selector("[data-testid=cine-skip]")
        await player.click("[data-testid=cine-skip]")
        await player.wait_for_selector("[data-testid=cine]", state="detached")
        await page.click(f"[data-testid=cine-stop-{cid}]")
        await player.evaluate("window.__eventos.setPrefs({ cinema: false })")
        await page.click(f"[data-testid=cine-play-{cid}]")
        await asyncio.sleep(0.6)
        assert await player.locator("[data-testid=cine]").count() == 0
        await page.click(f"[data-testid=cine-stop-{cid}]")

        # the game says the boss fell: the cinematic bound to it starts by itself
        await player.evaluate("window.__eventos.setPrefs({ cinema: true })")
        rig.bridge.on_event("boss_defeated", {"name": "Rey"})
        await player.wait_for_selector("[data-testid=cine]", timeout=3000)
        assert page.errors == [] and player.errors == []

    run(scenario)
