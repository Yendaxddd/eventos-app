"""The cinematics for creators in a real (headless) Chromium: a dialogue between two with their portraits, screen effects (blur, a
see-through black and white over the game), weather and title cards; templates and copy/paste in the editor; the music given back after
a preview; sound still playing for a player who switched cinematics off."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity import media  # noqa: E402
from test_activity_gm_browser import gm_page, run, until  # noqa: E402
from test_audio_browser import LISTEN, wait_heard  # noqa: E402
from test_cinema_browser import wav  # noqa: E402


def test_a_dialogue_between_two_with_screen_effects_weather_and_a_title_plays_on_every_screen():
    async def scenario(rig, browser, url):
        cinema = rig.bridge.cinema.book.put({"name": "Encuentro", "bars": False, "steps": [
            {"type": "text", "at": 0, "side": "left", "speaker": "Kuro", "text": "¿Quién anda ahí?", "duration": 1.6, "effect": "fade"},
            {"type": "text", "at": 1.8, "side": "right", "speaker": "Shiro", "text": "Tu sombra.", "duration": 2.5, "effect": "fade"},
            {"type": "effect", "at": 0, "effect": "blur", "duration": 8, "intensity": 100},
            {"type": "weather", "at": 0, "weather": "snow", "intensity": 50},
            {"type": "title", "at": 4.5, "text": "Capítulo II", "subtitle": "La caída", "style": "chapter", "duration": 3}]})
        player = await open_page(browser, url, name="Luis", width=1000, height=700)
        await rig.bridge.cinema.play(cinema["id"])
        await player.wait_for_selector("[data-testid=cine-portrait-left]")
        assert "kuro" in (await player.locator("[data-testid=cine-portrait-left]").inner_text()).lower()
        # whatever is under a cinematic is not pressed by mistake: the tap lands on the cinematic
        assert await player.evaluate("!!document.elementFromPoint(innerWidth / 2, innerHeight / 2).closest('.cine')")
        await player.wait_for_selector("[data-testid=cine-portrait-right].talking", timeout=4000)
        assert "waiting" in await player.locator("[data-testid=cine-portrait-left]").get_attribute("class")
        stage_filter = await player.evaluate("document.querySelector('[data-testid=cine-stage]').style.filter")
        assert "blur" in stage_filter
        assert await player.evaluate("getComputedStyle(document.querySelector('.cine-front')).filter") in ("none", "")   # the words stay sharp
        assert await player.locator("[data-testid=cine-weather][data-weather=snow] i").count() >= 10
        await player.wait_for_selector("[data-testid=cine-title]", timeout=5000)
        title = await player.locator("[data-testid=cine-title]").inner_text()
        assert "Capítulo II" in title and "La caída" in title
        assert player.errors == []

    run(scenario)


def test_a_see_through_cinematic_tints_the_game_itself_lets_it_be_used_and_leaves_it_as_it_was():
    async def scenario(rig, browser, url):
        cinema = rig.bridge.cinema.book.put({"name": "Recuerdo", "see": True, "bars": False, "steps": [
            {"type": "effect", "at": 0, "effect": "grayscale", "duration": 2.5, "intensity": 100},
            {"type": "text", "at": 0.2, "text": "Hace muchos años…", "duration": 2}]})
        player = await open_page(browser, url, name="Luis")
        await rig.bridge.cinema.play(cinema["id"])
        await player.wait_for_selector("[data-testid=cine-caption]")
        await player.wait_for_function("document.querySelector('.app').style.filter.includes('grayscale')")
        assert not await player.evaluate("!!document.elementFromPoint(innerWidth / 2, innerHeight / 3).closest('.cine')")   # the game can still be used
        await player.wait_for_selector("[data-testid=cine]", state="detached", timeout=6000)
        assert await player.evaluate("document.querySelector('.app').style.filter") == ""
        assert player.errors == []

    run(scenario)


def test_a_player_with_cinematics_off_still_hears_their_sound(tmp_path):
    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
        rig.server.files = store
        sound = rig.bridge.audio.library.add("golpe.wav", wav(), "sfx")
        cinema = rig.bridge.cinema.book.put({"name": "Golpe", "steps": [{"type": "text", "at": 0, "text": "¡Bum!", "duration": 1.5},
                                                                          {"type": "audio", "at": 0.3, "mode": "play", "sound": sound["id"]}]})
        player = await open_page(browser, url, name="Luis", init=LISTEN)
        await player.mouse.click(5, 5)
        await player.evaluate("window.__eventos.setPrefs({ cinema: false })")
        await rig.bridge.cinema.play(cinema["id"])
        await wait_heard(player, sources=1)
        assert await player.locator("[data-testid=cine]").count() == 0          # nothing drawn
        assert player.errors == []

    run(scenario)


def test_the_editor_adds_a_template_copies_and_pastes_steps_and_saves_the_sides_of_a_dialogue():
    async def scenario(rig, browser, url):
        rig.bridge.cinema.book.path = None
        page = await gm_page(browser, url, tab="cinema", width=1300, height=1400)
        await page.click("[data-testid=cine-new]")
        await page.fill("[data-testid=cine-name]", "Conversación")
        await page.fill("[data-testid=cine-cursor]", "5")
        await page.click("[data-testid=cine-template-dialogue]")
        await until(lambda: any(sum(1 for s in c["steps"] if s.get("side") in ("left", "right")) == 3 for c in rig.bridge.cinema.book.items.values()),
                    "the dialogue template to be saved", timeout=5)
        saved = next(iter(rig.bridge.cinema.book.items.values()))
        sides = [s for s in saved["steps"] if s.get("side") in ("left", "right")]
        assert [s["side"] for s in sides] == ["left", "right", "left"] and sides[0]["at"] == 5
        # copy the selected step (the first line of the template) and paste it at second 20
        await page.click("[data-testid=cine-copy]")
        await page.fill("[data-testid=cine-cursor]", "20")
        await page.click("[data-testid=cine-paste]")
        await until(lambda: any(s["at"] == 20 and s.get("side") == "left" for s in next(iter(rig.bridge.cinema.book.items.values()))["steps"]),
                    "the pasted step", timeout=5)
        # a screen effect and a title from the buttons
        await page.click("[data-testid=cine-add-effect]")
        await page.click("[data-testid=cine-effect-chromatic]")
        await page.click("[data-testid=cine-add-title]")
        await page.fill("[data-testid=cine-title-text]", "Fin")
        await until(lambda: any(s["type"] == "title" and s["text"] == "Fin" for s in next(iter(rig.bridge.cinema.book.items.values()))["steps"])
                    and any(s["type"] == "effect" and s["effect"] == "chromatic" for s in next(iter(rig.bridge.cinema.book.items.values()))["steps"]),
                    "the effect and the title", timeout=5)
        assert page.errors == []

    run(scenario)


def test_a_preview_with_its_own_music_gives_the_event_music_back(tmp_path):
    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
        rig.server.files = store
        event = rig.bridge.audio.library.add("tema.wav", wav(2), "music")
        other = rig.bridge.audio.library.add("flashback.wav", wav(2), "music")
        page = await gm_page(browser, url, tab="cinema")
        await page.mouse.click(5, 5)
        await rig.bridge.audio.start_music(event["id"])
        await page.wait_for_function(f"window.__eventos.music && window.__eventos.music.sound.id === {event['id']!r}")
        cinema = {"name": "Prueba", "bg": "#000000", "bars": False, "skippable": True, "steps": [
            {"type": "audio", "at": 0, "mode": "music", "sound": other["id"], "volume": 100},
            {"type": "text", "at": 0, "text": "…", "duration": 1.2}], "triggers": []}
        rig.bridge.cinema.book.put(cinema)
        await page.click("[data-testid^=cine-edit-]")
        await page.click("[data-testid=cine-preview]")
        await page.wait_for_function(f"window.__eventos.music && window.__eventos.music.sound.id === {other['id']!r}")
        await page.wait_for_selector("[data-testid=cine]", state="detached", timeout=6000)
        await page.wait_for_function(f"window.__eventos.music && window.__eventos.music.sound.id === {event['id']!r}")
        assert page.errors == []

    run(scenario)
