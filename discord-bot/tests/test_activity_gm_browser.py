"""The game-master panel in a real (headless) Chromium, against the real bridge and a made-up bot: who sees it, and what each part does
to the bot, on a computer and on a phone.

Skipped when the client has not been built (`npm run build` in activity_client/) or Playwright's Chromium is missing."""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import PIXEL, WEB, _chromium, open_page, playwright_api  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402


async def with_gm(scenario):
    rig = GmRig(me=ME)
    rig.web_dir = WEB
    async with rig:
        async def media(url):                       # Discord's CDN, replaced by one real 1x1 picture
            return "image/png", PIXEL
        rig.server._media_fetch = media
        async with playwright_api.async_playwright() as p:
            try:
                browser = await p.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
            except Exception as exc:  # noqa: BLE001 - no browser here (e.g. CI): nothing to test
                pytest.skip(f"no Chromium available: {str(exc).splitlines()[0]}")
            try:
                return await scenario(rig, browser, f"http://127.0.0.1:{rig.port}")
            finally:
                await browser.close()


def run(scenario):
    return asyncio.run(with_gm(scenario))


async def gm_page(browser, url, tab="event", **kwargs):
    """A game master's window (a test window on this PC asking for the panel), opened through the menu like a person would."""
    page = await open_page(browser, url, name="Gus", extra="&gm=1", **kwargs)
    await page.click("[data-testid=menu-button]")
    await page.click("[data-testid=tile-gm]")
    await page.wait_for_selector("[data-testid=gm]")
    if tab != "event":
        await page.click(f"[data-testid=gm-tab-{tab}]")
    await page.wait_for_selector(f"[data-testid=gm-tab-{tab}][aria-selected=true]")
    return page


async def until(condition, what="the bot to change", timeout=3.0):
    """The panel answers when the bot has changed, but a toast saying «guardado» may be a leftover of the step before: wait for the state itself."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return
        await asyncio.sleep(0.03)
    raise AssertionError(f"timed out waiting for {what}")


async def wait_toast(page, contains):
    toast = page.locator(".toast", has_text=re.compile(re.escape(contains), re.I)).first
    await toast.wait_for(timeout=4000)
    return (await toast.inner_text()).lower()


def test_only_game_masters_see_the_panel_in_the_menu_and_nobody_else_can_open_it():
    async def scenario(rig, browser, url):
        plain = await open_page(browser, url, name="Luis")
        await plain.click("[data-testid=menu-button]")
        await plain.wait_for_selector("[data-testid=tile-summary]")
        assert await plain.locator("[data-testid=tile-gm]").count() == 0
        await plain.evaluate("window.__eventos.go('gm')")                  # forcing the page open does not give the panel to anyone
        await plain.wait_for_selector("[data-testid=gm-denied]")
        assert "solo para el equipo de GM" in await plain.locator("[data-testid=gm-denied]").inner_text()
        assert await plain.locator("[data-testid=gm-tab-event]").count() == 0
        assert plain.errors == []

        page = await open_page(browser, url, name="Gus", extra="&gm=1")
        await page.click("[data-testid=menu-button]")
        assert "game master" in (await page.locator(".card-2").first.inner_text()).lower()
        await page.click("[data-testid=tile-gm]")
        for tab in ("event", "boss", "players", "values", "data", "history"):
            assert await page.locator(f"[data-testid=gm-tab-{tab}]").count() == 1, tab
        assert await page.evaluate("window.__eventos.view") == "gm"
        await page.click("[data-testid=back-button]")                       # back goes to the menu, as everywhere
        await page.wait_for_selector("[data-testid=tile-gm]")
        assert page.errors == []
    run(scenario)


def test_a_qte_is_launched_from_the_panel_with_the_chosen_kind_difficulty_and_person():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url)
        await page.wait_for_selector("[data-testid=gm-launch]")
        assert "alguien al azar" in await page.locator("[data-testid=gm-launch-summary]").inner_text()
        await page.click("[data-testid=gm-mode-combo]")
        await page.click("[data-testid=gm-difficulty-hard]")
        await page.select_option("[data-testid=gm-target]", str(OTHER))
        summary = await page.locator("[data-testid=gm-launch-summary]").inner_text()
        assert "de combo" in summary and "difícil" in summary and "a Mina" in summary
        await page.click("[data-testid=gm-launch-go]")
        await wait_toast(page, "QTE lanzado")
        await until(lambda: any(c[0] == "trigger_combo_qte" for c in rig.bot.calls), "the combo QTE to reach the bot")
        call = next(c for c in rig.bot.calls if c[0] == "trigger_combo_qte")
        assert call[1][0] == "hard" and call[1][1].id == OTHER and call[1][2] is True
        await page.click("[data-testid=gm-mode-group]")                      # a group QTE has no single target
        assert await page.locator("[data-testid=gm-target]").is_disabled()
        assert "a todo el grupo" in await page.locator("[data-testid=gm-launch-summary]").inner_text()
        assert page.errors == []
    run(scenario)


def test_a_stunned_boss_blocks_new_qtes_and_the_panel_says_why():
    async def scenario(rig, browser, url):
        rig.app.enemy_stunned, rig.app.stun_end_time = True, time.time() + 60
        page = await gm_page(browser, url)
        await page.wait_for_selector("[data-testid=gm-stunned]")
        assert await page.locator("[data-testid=gm-launch-go]").is_disabled()
        assert "aturdido" in (await page.locator("[data-testid=gm-stunned]").inner_text()).lower()
        assert page.errors == []
    run(scenario)


def test_a_batch_is_built_and_sent_and_the_fight_and_checkpoints_are_controlled():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url)
        await page.click("[data-testid=gm-batch-start]")
        await page.click("[data-testid=gm-batch-add-easy]")
        await page.click("[data-testid=gm-batch-add-impossible]")
        await page.wait_for_function("document.querySelector('[data-testid=gm-batch-queue]').textContent.includes('Imposible')")
        assert "1. Fácil" in await page.locator("[data-testid=gm-batch-queue]").inner_text()
        await page.click("[data-testid=gm-batch-undo]")
        await page.wait_for_function("!document.querySelector('[data-testid=gm-batch-queue]').textContent.includes('Imposible')")
        await page.click("[data-testid=gm-batch-send]")
        await wait_toast(page, "tanda enviada")
        assert any(c[0] == "process_batch_qtes" for c in rig.bot.calls)
        await page.click("[data-testid=gm-fight-start]")                       # the fight begins
        await wait_toast(page, "combate empezado")
        assert rig.app.fight_active is True
        await page.click("[data-testid=gm-fight-end]")                         # ...and asks before it ends
        await page.click("[data-testid=gm-fight-end-yes]")
        await wait_toast(page, "combate terminado")
        assert rig.app.fight_active is False
        await page.click("[data-testid=gm-checkpoint]")
        await wait_toast(page, "checkpoint lanzado")
        assert rig.app.regen_checkpoints == ["Checkpoint 1"]
        assert page.errors == []
    run(scenario)


def test_the_mode_of_the_automatic_qtes_and_its_odds_are_saved():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url)
        await page.click("[data-testid=gm-qtemode-random]")
        await page.fill("[data-testid=gm-weight-combo]", "40")
        await page.click("[data-testid=gm-qtemode-save]")
        await wait_toast(page, "modo de qte guardado")
        await until(lambda: rig.app.current_qte_mode == "random")
        assert rig.app.qte_variations["combo"]["weight"] == 40
        for key in ("standard", "combo", "direction", "fake"):                 # all at zero is refused before it is sent
            await page.fill(f"[data-testid=gm-weight-{key}]", "0")
        assert await page.locator("[data-testid=gm-qtemode-save]").is_disabled()
        assert page.errors == []
    run(scenario)


def test_a_value_changes_in_the_bot_and_a_refused_one_is_explained_and_changes_nothing():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url, tab="values")
        await page.wait_for_selector("[data-testid=gm-value-input-max_hp]")
        assert await page.locator("[data-testid=gm-value-save-max_hp]").is_disabled()          # nothing typed yet: nothing to save
        await page.fill("[data-testid=gm-value-input-max_hp]", "150")
        await page.click("[data-testid=gm-value-save-max_hp]")
        await until(lambda: rig.app.max_hp == 150)
        assert rig.app.player_hp[ME]["max"] == 150
        await page.fill("[data-testid=gm-value-input-max_hp]", "99999")
        await page.click("[data-testid=gm-value-save-max_hp]")
        assert "va de 1 a 9999" in await wait_toast(page, "va de 1 a 9999")
        assert rig.app.max_hp == 150
        await page.click("[data-testid=gm-value-input-ultimate_self_recharge]")                # a yes/no value saves when it is flipped
        await page.wait_for_function("document.querySelector('[data-testid=gm-value-input-ultimate_self_recharge]').getAttribute('aria-checked') === 'true'")
        assert rig.app.ultimate_self_recharge is True
        await page.fill("[data-testid=gm-qte-easy-timeout]", "1")                              # shorter than the end of the parry: refused
        await page.click("[data-testid=gm-qte-save-easy]")
        await wait_toast(page, "tiempo límite")
        assert rig.app.qte_timeout_durations["easy"] == 6.75
        await page.fill("[data-testid=gm-qte-easy-timeout]", "9")
        await page.click("[data-testid=gm-qte-save-easy]")
        await until(lambda: rig.app.qte_timeout_durations["easy"] == 9.0)
        assert page.errors == []
    run(scenario)


def test_the_boss_is_registered_hurt_and_defeated_from_the_panel():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url, tab="boss")
        await page.wait_for_selector("[data-testid=gm-boss-register]")
        assert await page.locator("[data-testid=gm-register-go]").is_disabled()               # a boss needs a name
        await page.fill("[data-testid=gm-register-name]", "Rey")
        await page.fill("[data-testid=gm-register-hp]", "300")
        await page.click("[data-testid=gm-register-go]")
        await wait_toast(page, "jefe registrado")
        await page.wait_for_selector("[data-testid=gm-boss-name]")
        assert rig.app.active_boss["hp_max"] == 300 and rig.app.fight_active
        assert "300 / 300" in await page.locator("[data-testid=gm-boss-active]").inner_text()
        await page.fill("[data-testid=gm-boss-amount]", "100")
        await page.click("[data-testid=gm-boss-damage]")
        await page.wait_for_function("document.querySelector('[data-testid=gm-boss-active]').textContent.includes('200 / 300')")
        await page.click("[data-testid=gm-boss-defeat]")                                      # it asks first
        assert rig.app.active_boss is not None
        await page.click("[data-testid=gm-boss-defeat-yes]")
        await page.wait_for_function("document.querySelector('[data-testid=gm-boss-active]').textContent.includes('No hay un jefe')")
        assert rig.app.active_boss is None
        assert page.errors == []
    run(scenario)


def test_boss_abilities_gifs_and_domain_are_kept_and_a_bad_form_is_explained():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url, tab="boss")
        await page.click("[data-testid=gm-ability-new]")
        await page.fill("[data-testid=gm-ability-name]", "Corte")
        await page.fill("[data-testid=gm-ability-damage]", "45")
        await page.select_option("[data-testid=gm-ability-status]", "burn")
        await page.fill("[data-testid=gm-ability-chance]", "150")                              # more than 100 %: refused
        await page.click("[data-testid=gm-ability-save]")
        await wait_toast(page, "va de 0 a 100")
        assert "Corte" not in rig.app.tupperbox_boss_config["abilities"]
        await page.fill("[data-testid=gm-ability-chance]", "60")
        await page.click("[data-testid=gm-ability-save]")
        await wait_toast(page, "habilidad guardada")
        assert rig.app.tupperbox_boss_config["abilities"]["Corte"]["damage"] == 45
        assert rig.app.tupperbox_boss_config["status_inflict"]["Corte"] == {"status": "burn", "chance": 60, "duration": 60}
        await page.wait_for_selector("[data-testid=gm-ability-Corte]")
        await page.fill("[data-testid=gm-gif-evade]", "https://cdn.discordapp.com/e.png")
        await page.click("[data-testid=gm-gif-add-evade]")
        await wait_toast(page, "imagen añadida")
        assert rig.app.tupperbox_boss_config["evade_gifs"] == ["https://cdn.discordapp.com/e.png"]
        await page.fill("[data-testid=gm-gif-evade]", "http://not-secure.example/e.png")
        await page.click("[data-testid=gm-gif-add-evade]")
        await wait_toast(page, "https")
        await page.fill("[data-testid=gm-domain-name]", "Santuario")
        await page.select_option("[data-testid=gm-domain-type]", "stun")
        await page.click("[data-testid=gm-domain-save]")
        await wait_toast(page, "dominio guardado")
        assert rig.app.tupperbox_boss_config["domain"]["type"] == "stun" and rig.app.tupperbox_boss_config["domain"]["name"] == "Santuario"
        await page.click("[data-testid=gm-ability-remove-Corte]")
        await page.click("[data-testid=gm-ability-remove-Corte-yes]")
        await wait_toast(page, "habilidad quitada")
        assert "Corte" not in rig.app.tupperbox_boss_config["abilities"]
        assert page.errors == []
    run(scenario)


def test_a_person_is_found_and_edited_from_the_players_list():
    async def scenario(rig, browser, url):
        manager = rig.app.special_objects_manager                                              # the sample objects are unique and already owned: bring a plain one
        charm = json.loads((manager.templates_path / "template_passive.json").read_text(encoding="utf-8"))
        charm.update({"id": "plain_charm", "name": "Amuleto sencillo", "unique": False})
        (manager.approved_path / "plain_charm.json").write_text(json.dumps(charm), encoding="utf-8")
        manager.load_all()
        page = await gm_page(browser, url, tab="players")
        await page.wait_for_selector(f"[data-testid=gm-player-{OTHER}]")
        assert await page.locator(f"[data-testid=gm-player-{ME}]").count() == 1
        await page.fill("[data-testid=gm-player-search]", "mi")                               # finds Mina, hides Ana
        await page.wait_for_function(f"!document.querySelector('[data-testid=gm-player-{ME}]')")
        await page.click(f"[data-testid=gm-player-{OTHER}]")
        await page.wait_for_selector("[data-testid=gm-person-name]")
        assert (await page.locator("[data-testid=gm-person-name]").inner_text()) == "Mina"
        await page.fill("[data-testid=gm-hp-current]", "40")
        await page.click("[data-testid=gm-hp-apply]")
        await wait_toast(page, "vida cambiada")
        assert rig.app.player_hp[OTHER]["current"] == 40
        await page.fill("[data-testid=gm-hp-current]", "5000")                                # above the maximum: refused
        await page.click("[data-testid=gm-hp-apply]")
        await wait_toast(page, "va de 1 a 100")
        assert rig.app.player_hp[OTHER]["current"] == 40
        await page.click("[data-testid=gm-afk]")
        await page.wait_for_function(f"document.querySelector('[data-testid=gm-afk]').getAttribute('aria-checked') === 'false'")
        assert OTHER in rig.app.afk_users
        await page.fill("[data-testid=gm-points-amount]", "3")
        await page.click("[data-testid=gm-points-give]")
        await wait_toast(page, "puntos dados")
        await until(lambda: rig.app.player_skills.get(str(OTHER), {}).get("skill_points") == 3)
        assert (await page.locator("[data-testid=gm-points-now]").inner_text()) == "3"
        await page.select_option("[data-testid=gm-ach-pick]", "first_evade")
        await page.click("[data-testid=gm-ach-give]")
        await page.wait_for_selector("[data-testid=gm-ach-first_evade]")
        assert "first_evade" in rig.app.player_achievements[str(OTHER)]
        await page.click("[data-testid=gm-ach-remove-first_evade]")
        await page.click("[data-testid=gm-ach-remove-first_evade-yes]")
        await wait_toast(page, "logro quitado")
        assert "first_evade" not in rig.app.player_achievements[str(OTHER)]
        await page.select_option("[data-testid=gm-obj-pick]", "plain_charm")
        await page.click("[data-testid=gm-obj-give]")
        await page.wait_for_selector("[data-testid=gm-obj-plain_charm]")
        assert "plain_charm" in manager.player_inventory[OTHER]
        await page.fill("[data-testid=gm-spins-plain_charm-hard]", "9")
        await page.click("[data-testid=gm-spins-save-plain_charm]")
        await wait_toast(page, "vueltas cambiadas")
        assert manager.get_tracking(OTHER, "plain_charm", "hard") == 9
        await page.click("[data-testid=gm-obj-take-plain_charm]")
        await page.click("[data-testid=gm-obj-take-plain_charm-yes]")
        await wait_toast(page, "objeto quitado")
        assert "plain_charm" not in manager.player_inventory[OTHER]
        await page.click("[data-testid=gm-person-back]")
        await page.wait_for_selector("[data-testid=gm-players]")
        assert page.errors == []
    run(scenario)


def test_content_files_are_edited_with_the_json_checked_live_and_a_copy_kept():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url, tab="data")
        await page.click("[data-testid=gm-section-files]")
        await page.select_option("[data-testid=gm-file-select]", "achievements")
        await page.wait_for_selector("[data-testid=gm-editor-text]")
        assert "Sin cambios" in await page.locator("[data-testid=gm-editor-status]").inner_text()
        assert await page.locator("[data-testid=gm-editor-save]").is_disabled()
        await page.fill("[data-testid=gm-editor-text]", "{ esto no es json")
        assert "no es válido" in await page.locator("[data-testid=gm-editor-status]").inner_text()
        assert await page.locator("[data-testid=gm-editor-save]").is_disabled()               # a broken file can not even be sent
        path = rig.base / "data" / "achievements" / "achievements_config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["achievements"]["editado"] = {"name": "Editado", "description": "Desde el panel", "category": "combat", "icon": "🧪", "trigger": "manual", "reward": {}}
        await page.fill("[data-testid=gm-editor-text]", json.dumps(config))
        await page.click("[data-testid=gm-editor-save]")
        await wait_toast(page, "archivo guardado")
        await until(lambda: "editado" in rig.app.achievements_config["achievements"])
        await page.wait_for_selector("[data-testid=gm-backups] li")
        assert await page.locator("[data-testid=gm-backups] li").count() == 1
        config["achievements"]["editado"]["name"] = ""                                         # valid JSON but not a valid achievement: the bot refuses it
        await page.fill("[data-testid=gm-editor-text]", json.dumps(config))
        await page.click("[data-testid=gm-editor-save]")
        await wait_toast(page, "necesita un nombre")
        assert rig.app.achievements_config["achievements"]["editado"]["name"] == "Editado"
        backup = (await page.locator("[data-testid=gm-backups] li code").first.inner_text())
        await page.click(f"[data-testid='gm-restore-{backup}']")                               # recover the first version
        await page.click(f"[data-testid='gm-restore-{backup}-yes']")
        await wait_toast(page, "copia recuperada")
        await until(lambda: "editado" not in rig.app.achievements_config["achievements"])
        assert page.errors == []
    run(scenario)


def test_achievements_are_created_from_a_form_and_pending_objects_are_approved():
    async def scenario(rig, browser, url):
        manager = rig.app.special_objects_manager
        good = json.loads((manager.templates_path / "template_passive.json").read_text(encoding="utf-8"))
        good.update({"id": "cursed_ring", "name": "Anillo maldito"})
        (manager.pending_path / "cursed_ring.json").write_text(json.dumps(good), encoding="utf-8")
        (manager.pending_path / "broken.json").write_text(json.dumps({"id": "broken", "name": "Roto", "type": "banana"}), encoding="utf-8")
        page = await gm_page(browser, url, tab="data")
        await page.click("[data-testid=gm-ach-new]")
        await page.fill("[data-testid=gm-achform-id]", "desde_el_panel")
        await page.fill("[data-testid=gm-achform-name]", "Desde el panel")
        await page.fill("[data-testid=gm-achform-trigger]", "evade_count:7")
        await page.fill("[data-testid=gm-achform-points]", "2")
        await page.click("[data-testid=gm-achform-save]")
        await page.wait_for_selector("[data-testid=gm-achrow-desde_el_panel]")
        saved = rig.app.achievements_config["achievements"]["desde_el_panel"]
        assert saved["name"] == "Desde el panel" and saved["trigger"] == "evade_count:7" and saved["reward"] == {"skill_points": 2}
        await page.fill("[data-testid=gm-ach-search]", "desde el")
        assert await page.locator("[data-testid^=gm-achrow-]").count() == 1
        await page.click("[data-testid=gm-ach-new]")                                           # a bad trigger is explained, nothing is written
        await page.fill("[data-testid=gm-achform-id]", "otro")
        await page.fill("[data-testid=gm-achform-name]", "Otro")
        await page.fill("[data-testid=gm-achform-trigger]", "cuando me apetezca")
        await page.click("[data-testid=gm-achform-save]")
        await wait_toast(page, "disparador")
        assert "otro" not in rig.app.achievements_config["achievements"]
        await page.keyboard.press("Escape")
        await page.click("[data-testid=gm-ach-delete-desde_el_panel]")
        await page.click("[data-testid=gm-ach-delete-desde_el_panel-yes]")
        await wait_toast(page, "logro borrado")
        assert "desde_el_panel" not in rig.app.achievements_config["achievements"]

        await page.click("[data-testid=gm-section-objects]")
        await page.wait_for_selector("[data-testid='gm-pending-cursed_ring.json']")
        assert await page.locator("[data-testid='gm-approve-broken.json']").is_disabled()      # an object with errors can not be approved
        assert "tipo" in await page.locator("[data-testid='gm-pending-broken.json']").inner_text()
        await page.click("[data-testid='gm-approve-cursed_ring.json']")
        await wait_toast(page, "aprobado")
        assert "cursed_ring" in manager.objects
        await page.wait_for_selector("[data-testid=gm-approved-cursed_ring]")
        await page.click("[data-testid='gm-reject-broken.json']")
        await page.fill("[data-testid='gm-reject-reason-broken.json']", "No encaja")
        await page.click("[data-testid='gm-reject-confirm-broken.json']")
        await wait_toast(page, "rechazado")
        assert not (manager.pending_path / "broken.json").exists()
        assert page.errors == []
    run(scenario)


def test_the_history_lists_who_did_what_newest_first():
    async def scenario(rig, browser, url):
        page = await gm_page(browser, url)
        await page.select_option("[data-testid=gm-target]", str(OTHER))
        await page.click("[data-testid=gm-launch-go]")
        await wait_toast(page, "QTE lanzado")
        await page.click("[data-testid=gm-checkpoint]")
        await wait_toast(page, "checkpoint lanzado")
        await page.click("[data-testid=gm-tab-history]")
        await page.wait_for_selector("[data-testid=gm-log-item]")
        items = await page.locator("[data-testid=gm-log-item]").all_inner_texts()
        assert len(items) == 2 and "Checkpoint 1" in items[0] and "Lanzó un QTE individual" in items[1]
        assert all("Gus (prueba local)" in item for item in items)
        assert page.errors == []
    run(scenario)


def test_the_panel_fits_a_phone_in_every_tab_without_sideways_scrolling():
    async def scenario(rig, browser, url):
        rig.app.active_boss = {"name": "Rey", "hp_current": 70, "hp_max": 100, "gif_url": None, "participants": set()}
        page = await gm_page(browser, url, width=390, height=800, mobile=True)
        for tab, marker in (("event", "gm-launch"), ("boss", "gm-boss-active"), ("players", "gm-players"), ("values", "gm-values"), ("data", "gm-data"), ("history", "gm-history")):
            await page.click(f"[data-testid=gm-tab-{tab}]")
            await page.wait_for_selector(f"[data-testid={marker}]")
            await asyncio.sleep(0.3)
            overflow = await page.evaluate("""() => {
                const wide = [...document.querySelectorAll('.dash-body *')].filter((el) => el.getBoundingClientRect().right > innerWidth + 1 && !el.closest('.dash-nav'));
                return { page: document.documentElement.scrollWidth - innerWidth, body: document.querySelector('.dash-body').scrollWidth - document.querySelector('.dash-body').clientWidth,
                         wide: wide.slice(0, 3).map((el) => el.className || el.tagName) };
            }""")
            assert overflow["page"] <= 0 and overflow["body"] <= 1, (tab, overflow)
        await page.click("[data-testid=gm-tab-values]")
        await page.fill("[data-testid=gm-value-input-save_limit]", "4")
        await page.locator("[data-testid=gm-value-save-save_limit]").scroll_into_view_if_needed()
        await page.click("[data-testid=gm-value-save-save_limit]")
        await wait_toast(page, "guardado")
        assert rig.app.save_limit == 4
        assert page.errors == []
    run(scenario)
