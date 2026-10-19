"""The game masters' quick controls beside the chat, in a real (headless) Chromium: only for the role, and every button does what the panel's does."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import WEB, open_page  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity import media  # noqa: E402
from test_activity_gm_browser import run, until, wait_toast  # noqa: E402
from test_audio import OGG  # noqa: E402


async def gm_event_page(browser, url, **kwargs):
    page = await open_page(browser, url, name="Gus", extra="&gm=1", **kwargs)
    if await page.locator("[data-testid=side-tab-gm]").count():                              # a game master's side panel has two tabs
        await page.click("[data-testid=side-tab-gm]")
    return page


def test_the_deck_is_there_for_game_masters_only_and_runs_the_boss_and_the_fight(tmp_path):
    async def scenario(rig, browser, url):
        rig.app.tupperbox_boss_config["character_name"] = "Lyra"
        rig.app.tupperbox_boss_config["boss_hp"] = 1000
        rig.app.tupperbox_boss_config["abilities"] = {"Corte": {"damage": 45}}
        player = await open_page(browser, url, name="Luis", width=1100, height=800)
        assert await player.locator("[data-testid=gm-deck]").count() == 0 and await player.locator("[data-testid=gm-deck-button]").count() == 0
        assert await player.locator("[data-testid=side-tab-gm]").count() == 0
        page = await gm_event_page(browser, url, width=1100, height=1200)
        await page.wait_for_selector("[data-testid=gm-deck]")
        assert "Sin combate" in await page.locator("[data-testid=deck-fight-state]").inner_text()

        # the boss of Tupperbox appears with one click, and is hurt and healed in percentages
        await page.click("[data-testid=deck-spawn]")
        await page.wait_for_selector("[data-testid=deck-boss]")
        assert rig.app.active_boss["name"] == "Lyra" and rig.app.fight_active
        await page.click("[data-testid=deck-ability-Corte]")                                    # the boss's own attacks are one click away too
        await until(lambda: any(c[0] == "boss_use_ability" for c in rig.bot.calls), "the boss ability")
        await page.click("[data-testid=deck-dmg-10]")
        await until(lambda: rig.app.active_boss["hp_current"] == 900, "10 % of the boss's life")
        await page.click("[data-testid=deck-heal]")
        await until(lambda: rig.app.active_boss["hp_current"] == 1000, "the heal")
        await page.fill("[data-testid=deck-dmg-exact] >> xpath=../input", "250")
        await page.click("[data-testid=deck-dmg-exact]")
        await until(lambda: rig.app.active_boss["hp_current"] == 750, "an exact blow")
        await page.click("[data-testid=deck-defeat]")                                          # it asks first
        assert rig.app.active_boss is not None
        await page.click("[data-testid=deck-defeat-yes]")
        await until(lambda: rig.app.active_boss is None, "the boss to fall")
        await page.wait_for_selector("[data-testid=deck-spawn]")

        # the fight, a checkpoint and a QTE
        await page.wait_for_selector("[data-testid=deck-fight-start]")                      # the boss falling ended the fight
        await page.click("[data-testid=deck-fight-start]")
        await until(lambda: rig.app.fight_active is True, "the fight to start")
        await page.click("[data-testid=deck-checkpoint]")
        await until(lambda: rig.app.regen_checkpoints == ["Checkpoint 1"], "the checkpoint")
        await page.click("text=Combo >> visible=true")
        await page.click("[data-testid=deck-launch]")
        await until(lambda: any(c[0] == "trigger_combo_qte" for c in rig.bot.calls), "the combo QTE")
        await page.click("[data-testid=deck-fight-end]")                                       # ending a fight asks first
        assert rig.app.fight_active is True
        await page.click("[data-testid=deck-fight-end-yes]")
        await until(lambda: rig.app.fight_active is False, "the fight to end")
        assert page.errors == [] and player.errors == []

    run(scenario)


def test_the_deck_plays_a_cinematic_and_music_and_shows_what_is_linked_to_each_moment_of_the_fight(tmp_path):
    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
        rig.server.files = store
        track = rig.bridge.audio.library.add("batalla.ogg", OGG + b"x" * 40, "music")
        rig.bridge.cinema.book.path = tmp_path / "cine.json"
        cinema = rig.bridge.cinema.book.put({"name": "Llegada", "steps": [{"type": "text", "at": 0, "text": "Hola", "duration": 5}], "triggers": ["boss_spawn"], "boss": "Lyra"})
        rig.bridge.audio.library.set_phase("fight_start", "music", track["id"], 80)
        rig.bridge.fx.book.set_event("boss_defeated", {"preset": "explosion"})
        page = await gm_event_page(browser, url, width=1100, height=1500)
        await page.wait_for_selector("[data-testid=deck-links]")
        spawn_link = await page.locator("[data-testid=deck-link-boss_spawn]").inner_text()
        assert "Llegada" in spawn_link and "solo Lyra" in spawn_link
        assert "batalla" in await page.locator("[data-testid=deck-link-fight_start]").inner_text()
        assert "Explosión" in await page.locator("[data-testid=deck-link-boss_defeated]").inner_text()

        await page.click("[data-testid=deck-cinema-play]")
        await until(lambda: rig.bridge.cinema.current() is not None, "the cinematic to start")
        await page.wait_for_selector("[data-testid=deck-cinema-stop]")
        await page.click("[data-testid=deck-cinema-stop]")
        await until(lambda: rig.bridge.cinema.current() is None, "the cinematic to stop")
        await page.click("[data-testid=deck-music-play]")
        await until(lambda: rig.bridge.audio.music is not None and rig.bridge.audio.music["sound"]["name"] == "batalla", "the music")
        await page.wait_for_selector("[data-testid=deck-music-stop]")
        await page.click("[data-testid=deck-music-stop]")
        await until(lambda: rig.bridge.audio.music is None, "the music to stop")
        assert page.errors == []

    run(scenario)


def test_on_a_phone_the_deck_opens_from_the_top_bar():
    async def scenario(rig, browser, url):
        page = await gm_event_page(browser, url, width=390, height=800, mobile=True)
        await page.click("[data-testid=gm-deck-button]")
        await page.wait_for_selector(".sheet [data-testid=gm-deck]")
        await page.wait_for_selector(".sheet [data-testid=deck-fight-state]")
        overflow = await page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert overflow is False
        assert page.errors == []

    run(scenario)


def test_each_moment_of_the_fight_gets_its_cinematic_music_effect_and_sound_from_one_card_in_the_boss_tab(tmp_path):
    from test_activity_gm_browser import gm_page

    async def scenario(rig, browser, url):
        store = media.MediaStore(tmp_path / "media")
        library = rig.bridge.audio.library
        library.store, library.path = store, tmp_path / "audio.json"
        rig.server.files = store
        track = library.add("batalla.ogg", OGG + b"x" * 40, "music")
        hit = library.add("golpe.ogg", OGG + b"y" * 40, "sfx")
        rig.bridge.cinema.book.path = tmp_path / "cine.json"
        cinema = rig.bridge.cinema.book.put({"name": "Caída del Rey", "steps": [{"type": "text", "at": 0, "text": "Adiós", "duration": 3}], "triggers": []})
        page = await gm_page(browser, url, tab="boss")
        await page.wait_for_selector("[data-testid=link-boss_defeated]")
        await page.select_option("[data-testid=link-cinema-boss_defeated]", cinema["id"])
        await until(lambda: rig.bridge.cinema.book.items[cinema["id"]]["triggers"] == ["boss_defeated"], "the cinematic to be linked")
        await page.select_option("[data-testid=link-music-boss_defeated]", "__stop")
        await until(lambda: library.phases.get("boss_defeated", {}).get("mode") == "stop", "the music change")
        await page.select_option("[data-testid=link-music-fight_start]", track["id"])
        await until(lambda: library.phases.get("fight_start", {}).get("sound") == track["id"], "the fight music")
        await page.select_option("[data-testid=link-effect-boss_defeated]", "dominio")
        await until(lambda: rig.bridge.fx.book.events.get("boss_defeated", {}).get("preset") == "dominio", "the effect")
        await page.select_option("[data-testid=link-sound-boss_defeated]", hit["id"])
        await until(lambda: library.cues.get("boss_defeated", {}).get("sound") == hit["id"], "the sound")
        # choosing «none» undoes each one
        await page.select_option("[data-testid=link-effect-boss_defeated]", "")
        await until(lambda: "boss_defeated" not in rig.bridge.fx.book.events, "the effect to go")
        await page.select_option("[data-testid=link-cinema-boss_defeated]", "")
        await until(lambda: rig.bridge.cinema.book.items[cinema["id"]]["triggers"] == [], "the cinematic to be unlinked")
        # the game says the boss fell: what is left plays (the music stops, the sound is heard)
        rig.bridge.audio.music = {"sound": track, "startedAt": 0, "volume": 50, "loop": True}
        rig.bridge.on_event("boss_defeated", {"name": "Rey"})
        await until(lambda: rig.bridge.audio.music is None, "the music to stop by itself")
        assert page.errors == []

    run(scenario)
