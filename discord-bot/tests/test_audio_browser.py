"""The event's sound in a real (headless) Chromium: the game masters fill the library, play music, press sounds and bind them to what
happens; a player's page plays them with its own volume."""
import asyncio
import io
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity import media  # noqa: E402
from test_activity_gm_browser import gm_page, run, until  # noqa: E402

LISTEN = """
window.__audio = { sources: [], elements: [] };
const start = AudioBufferSourceNode.prototype.start;
AudioBufferSourceNode.prototype.start = function (...a) { window.__audio.sources.push({ seconds: this.buffer ? this.buffer.duration : null }); return start.apply(this, a); };
const play = HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play = function () { window.__audio.elements.push({ src: this.src, loop: this.loop }); return play.apply(this, arguments); };
"""


def wav(seconds=0.4, rate=8000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return out.getvalue()


async def heard(page):
    return await page.evaluate("({ sources: window.__audio.sources.length, elements: window.__audio.elements.length })")


async def wait_heard(page, sources=None, elements=None, seconds=4.0):
    for _ in range(int(seconds / 0.05)):
        got = await heard(page)
        if (sources is None or got["sources"] >= sources) and (elements is None or got["elements"] >= elements):
            return got
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected sources>={sources} elements>={elements}, got {await heard(page)}")


def test_the_game_masters_fill_the_library_and_every_player_hears_the_music_the_sounds_and_the_cues(tmp_path):
    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
        rig.server.files = store
        player = await open_page(browser, url, name="Luis", init=LISTEN)
        await player.mouse.click(5, 5)                                                          # the first touch lets the browser play
        page = await gm_page(browser, url, tab="audio")
        assert await page.locator("[data-testid=gm-audio]").count() == 1

        # two files: an effect and a track
        await page.set_input_files("[data-testid=gm-upload-file]", files=[{"name": "golpe.wav", "mimeType": "audio/wav", "buffer": wav(0.3)}])
        await page.wait_for_selector("[data-testid^=gm-sound-name-]")
        await page.select_option("[data-testid=gm-upload-kind]", "music")
        await page.set_input_files("[data-testid=gm-upload-file]", files=[{"name": "tema final.wav", "mimeType": "audio/wav", "buffer": wav(1.2)}])
        await page.wait_for_function("document.querySelectorAll('[data-testid^=gm-sound-name-]').length === 2")
        sounds = {s["name"]: s for s in rig.bridge.audio.library.public()}
        assert sounds["golpe"]["kind"] == "sfx" and sounds["tema final"]["kind"] == "music" and sounds["tema final"]["loop"] is True
        hit, theme = sounds["golpe"]["id"], sounds["tema final"]["id"]

        # a sound by hand
        await page.click(f"[data-testid=gm-pad-{hit}]")
        await wait_heard(player, sources=1)

        # a cue: the game says a Black Flash happened
        await page.select_option("[data-testid=gm-cue-sound-black_flash]", hit)
        await until(lambda: "black_flash" in rig.bridge.audio.library.cues, "the cue")
        rig.bridge.on_event("black_flash", {"user": None})
        await wait_heard(player, sources=2)

        # music for everybody, shown in the top bar, and silenced by the player
        await page.click(f"[data-testid=gm-music-play-{theme}]")
        await page.wait_for_selector("[data-testid=gm-music-now]")
        got = await wait_heard(player, elements=1)
        assert got["elements"] >= 1
        assert (await player.evaluate("window.__audio.elements.at(-1)"))["loop"] is True
        assert "tema final" in await player.locator("[data-testid=now-playing]").inner_text()
        before = await heard(player)
        await player.click("[data-testid=now-playing]")                                         # the player's own switch
        await player.evaluate("window.__eventos.go('settings')")
        rig.bridge.on_event("black_flash", {"user": None})
        await asyncio.sleep(0.5)
        assert (await heard(player))["sources"] == before["sources"]                           # silenced here, still playing for everybody else
        assert rig.bridge.audio.music is not None
        await page.click("[data-testid=gm-music-stop]")
        await until(lambda: rig.bridge.audio.music is None, "the music to stop")
        assert page.errors == [] and player.errors == []

    run(scenario)


def test_a_player_who_has_not_touched_the_page_is_asked_to_and_hears_the_sound_after_the_first_touch(tmp_path):
    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
        rig.server.files = store
        sound = rig.bridge.audio.library.add("aviso.wav", wav(0.3), "sfx")
        # a browser that refuses to make sound until the page is touched (the real situation inside Discord)
        player = await open_page(browser, url, name="Luis", init="""
            window.__audio = { sources: [], elements: [] };
            const start = AudioBufferSourceNode.prototype.start;
            AudioBufferSourceNode.prototype.start = function (...a) { window.__audio.sources.push({}); return start.apply(this, a); };
            const AC = window.AudioContext;
            window.AudioContext = class extends AC { get state() { return window.__touched ? super.state : 'suspended'; } resume() { return window.__touched ? super.resume() : Promise.resolve(); } };
            document.addEventListener('pointerdown', () => { window.__touched = true; }, true);
        """)
        await rig.bridge.audio.play(sound["id"], 100)
        await asyncio.sleep(0.4)
        assert (await heard(player))["sources"] == 0
        assert "Toca para activar" in await player.locator("[data-testid=now-playing]").inner_text()
        await player.mouse.click(5, 5)
        await wait_heard(player, sources=1)
        await until(lambda: True)
        await player.wait_for_selector("[data-testid=now-playing]", state="detached", timeout=3000)     # nothing is waiting any more
        assert player.errors == []

    run(scenario)
