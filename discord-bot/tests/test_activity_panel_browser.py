"""«Mi panel» in a real (headless) Chromium, against the real bridge and a made-up bot: the profile, achievements, characters and
powers, skill tree, inventory, counter pictures and the leaderboard, on a computer and on a phone.

Skipped when the client has not been built (`npm run build` in activity_client/) or Playwright's Chromium is missing."""
import asyncio
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_activity_browser import PIXEL, WEB, _chromium, open_page, playwright_api  # noqa: E402  (skips this module when Playwright is missing)

pytestmark = pytest.mark.skipif(not (WEB / "app.js").exists(), reason="activity client not built (npm run build)")

from eventos_app.activity.server import dev_identity  # noqa: E402
from test_activity_panel import PNG, PanelRig  # noqa: E402


async def with_panel(scenario):
    me = dev_identity("Ana")[0]
    rig = PanelRig(me=me)
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
                return await scenario(rig, browser, f"http://127.0.0.1:{rig.port}", me)
            finally:
                await browser.close()


def run(scenario):
    return asyncio.run(with_panel(scenario))


async def panel_at(page, tab):
    """Through the menu, like a player: ☰ → the tile of that tab."""
    await page.click("[data-testid=menu-button]")
    await page.click(f"[data-testid=tile-{tab}]")
    await page.wait_for_selector(f"[data-testid=dash-tab-{tab}][aria-selected=true]")


async def wait_toast(page, contains):
    """The text of the toast that says `contains` (older toasts may still be on screen)."""
    toast = page.locator(".toast", has_text=re.compile(re.escape(contains), re.I)).first
    await toast.wait_for(timeout=4000)
    return (await toast.inner_text()).lower()


def test_the_menu_opens_each_part_of_the_panel_and_back_returns_to_the_menu():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await page.click("[data-testid=menu-button]")
        for tab in ("summary", "achievements", "characters", "skills", "inventory", "images", "ranking"):
            assert await page.locator(f"[data-testid=tile-{tab}]").count() == 1, tab
        await page.click("[data-testid=tile-achievements]")
        await page.wait_for_selector("[data-testid=achievements]")
        assert await page.evaluate("window.__eventos.view") == "panel"
        await page.click("[data-testid=dash-tab-ranking]")                       # switching tab keeps the same «back»
        await page.wait_for_selector("[data-testid=ranking]")
        await page.click("[data-testid=back-button]")
        await page.wait_for_selector("[data-testid=tile-skills]")
        assert await page.evaluate("window.__eventos.view") == "menu"
        await page.keyboard.press("Escape")
        await page.wait_for_selector("[data-testid=composer]")
        assert page.errors == []
    run(scenario)


def test_the_summary_shows_the_players_numbers_and_the_participation_switch_reaches_the_bot():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await panel_at(page, "summary")
        await page.wait_for_selector("[data-testid=summary]")
        assert "Ana" in await page.locator("[data-testid=hero-name]").inner_text()
        assert "75 %" in await page.locator("[data-testid=stat-rate]").inner_text()
        assert "15 de 20" in await page.locator("[data-testid=stat-rate]").inner_text()
        assert (await page.locator("[data-testid=stat-bf] b").inner_text()) == "2"
        assert "0,8" in await page.locator("[data-testid=stat-time]").inner_text()
        assert await page.locator("[data-testid=charge-1]").get_attribute("data-ready") == "1" and "LISTA" in await page.locator("[data-testid=charge-1]").inner_text()
        assert await page.locator("[data-testid=charge-2]").get_attribute("data-ready") == "0"
        assert "Nimble" in await page.locator(".hero").inner_text() and "3 puntos" in await page.locator(".hero").inner_text()
        assert await page.locator("[data-testid=times-chart] svg").count() == 1
        await page.click(".hero-active .switch")                                  # stay out of the QTEs
        await page.wait_for_function("document.querySelector('.hero-active span').textContent.includes('Fuera')")
        assert me in rig.panel_app.afk_users
        await page.click(".hero-active .switch")
        await page.wait_for_function("document.querySelector('.hero-active span').textContent.includes('Participas')")
        assert me not in rig.panel_app.afk_users
        await page.click("[data-testid=go-skills]")                               # the shortcuts open the other tabs
        await page.wait_for_selector("[data-testid=skills]")
        assert page.errors == []
    run(scenario)


def test_achievements_keep_secrets_and_let_the_player_choose_title_and_domain():
    async def scenario(rig, browser, url, me):
        rig.panel_app.player_achievements[str(me)]["domains"].append("malevolent_shrine")
        page = await open_page(browser, url)
        await panel_at(page, "achievements")
        await page.wait_for_selector("[data-testid=achievements]")
        assert (await page.locator("[data-testid=ach-count]").inner_text()).replace("\n", "") == "2 / 16"
        secret = page.locator("[data-testid=ach-shrine]")
        assert await secret.get_attribute("data-state") == "secret"
        text = (await secret.inner_text()).lower()
        assert "???" in text and "shrine" not in text and "untouched" not in text and "daño" not in text
        assert "shrine" not in (await page.locator("[data-testid=ach-cat-domain]").inner_text()).lower().replace("malevolent shrine", "")
        assert await page.locator("[data-testid=ach-first_evade]").get_attribute("data-state") == "done"
        assert "12 / 100" in await page.locator("[data-testid=ach-progress-evade_master]").inner_text()
        assert "esquiva 100 qte" in (await page.locator("[data-testid=ach-evade_master]").inner_text()).lower()

        await page.get_by_test_id("title-∞ Infinity").click()
        await page.wait_for_function("document.querySelector('[data-testid=\"title-∞ Infinity\"]').getAttribute('aria-pressed') === 'true'")
        assert rig.panel_app.player_achievements[str(me)]["active_title"] == "∞ Infinity"
        await page.click("[data-testid=title-none]")
        await page.wait_for_function("document.querySelector('[data-testid=title-none]').getAttribute('aria-pressed') === 'true'")
        assert "active_title" not in rig.panel_app.player_achievements[str(me)]

        assert await page.locator("[data-testid=domain-use-infinite_void]").is_disabled()
        await page.click("[data-testid=domain-use-malevolent_shrine]")
        await page.wait_for_function("document.querySelector('[data-testid=domain-malevolent_shrine]').dataset.active === '1'")
        assert rig.panel_app.player_achievements[str(me)]["active_domain"] == "malevolent_shrine"
        assert await page.locator("[data-testid=domain-infinite_void]").get_attribute("data-active") == "0"

        await page.click("[data-testid=cat-combat]")                              # filter by category
        assert await page.locator("[data-testid=ach-cat-combat]").count() == 1 and await page.locator("[data-testid=ach-cat-domain]").count() == 0
        assert page.errors == []
    run(scenario)


def test_characters_can_be_registered_given_powers_edited_and_dropped_and_every_screen_hears_about_it():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        phone = await open_page(browser, url, width=420, height=800, mobile=True)         # the same player on a second screen
        await panel_at(page, "characters")
        await page.wait_for_selector("[data-testid=characters]")
        assert await page.locator("[data-testid=char-Kuro]").count() == 1 and "Corte" in await page.locator("[data-testid=char-Kuro]").inner_text()

        await page.fill("[data-testid=register-name]", "  Zed ")
        await page.click("[data-testid=register-submit]")
        await page.wait_for_selector("[data-testid=char-Zed]")
        assert rig.panel_app.character_registry["Zed"] == me
        await page.wait_for_function("window.__eventos.characters.includes('Zed')")       # the «write as» list follows
        await phone.wait_for_function("window.__eventos.characters.includes('Zed')")      # and so does the other screen
        await page.fill("[data-testid=register-name]", "Mina")                             # somebody else's
        await page.click("[data-testid=register-submit]")
        await wait_toast(page, "ya está registrado")
        assert "Mina" not in rig.panel_app.user_characters[me]

        # a new power
        await page.click("[data-testid=power-add-Shiro-1]")
        await page.wait_for_selector("[data-testid=power-editor]")
        await page.fill("[data-testid=power-name]", "Escudo lunar")
        await page.fill("[data-testid=power-description]", "Una barrera de luz")
        await page.select_option("[data-testid=power-type]", "defend")
        await page.fill("[data-testid=power-effect-amount]", "80")
        await page.fill("[data-testid=power-cooldown]", "90")
        await page.fill("[data-testid=power-trigger]", " Luz De Luna ")
        await page.click("[data-testid=power-save]")
        await page.wait_for_selector("[data-testid=power-editor]", state="detached")
        saved = rig.panel_app.character_powers["Shiro"]["power1"]
        assert saved == {"name": "Escudo lunar", "description": "Una barrera de luz", "type": "defend", "cooldown": 90, "effect": "damage:80",
                         "image_url": None, "trigger_phrase": "luz de luna", "show": "all"}
        card = page.locator("[data-testid=power-Shiro-1]")
        assert "Escudo lunar" in await card.inner_text() and "80 de daño al jefe" in await card.inner_text() and "«luz de luna»" in await card.inner_text()

        # edit the one Kuro already has: the form starts with what it has
        await page.click("[data-testid=power-edit-Kuro-1]")
        assert await page.input_value("[data-testid=power-name]") == "Corte" and await page.input_value("[data-testid=power-effect-amount]") == "50"
        await page.select_option("[data-testid=power-effect-kind]", "heal")
        await page.fill("[data-testid=power-effect-amount]", "20")
        await page.click("[data-testid=power-save]")
        await page.wait_for_selector("[data-testid=power-editor]", state="detached")
        assert rig.panel_app.character_powers["Kuro"]["power1"]["effect"] == "heal:20"
        assert "Te curas 20 PV" in await page.locator("[data-testid=power-Kuro-1]").inner_text()

        # several effects at once, with what they will do said before saving, and who sees the picture
        await page.click("[data-testid=power-edit-Kuro-1]")
        await page.click("[data-testid=power-add-effect]")
        await page.select_option("[data-testid=power-effect-kind-1]", "shield_team")
        await page.fill("[data-testid=power-effect-1-amount]", "35")
        assert "35 % menos de daño" in await page.locator("[data-testid=power-preview]").inner_text()
        await page.click("[data-testid=power-show-self]")
        await page.click("[data-testid=power-save]")
        await page.wait_for_selector("[data-testid=power-editor]", state="detached")
        assert rig.panel_app.character_powers["Kuro"]["power1"]["effect"] == "heal:20;shield_team:35:12"
        assert rig.panel_app.character_powers["Kuro"]["power1"]["show"] == "self"

        # an invalid one is explained, not lost
        await page.click("[data-testid=power-edit-Kuro-1]")
        await page.select_option("[data-testid=power-effect-kind]", "custom")
        await page.fill("[data-testid=power-effect-text]", "borrar todo")
        await page.click("[data-testid=power-save]")
        await wait_toast(page, "efecto")
        await page.wait_for_selector("[data-testid=power-editor]")                         # still open, so nothing typed is lost
        await page.keyboard.press("Escape")

        # a picture for the power, from the device
        await page.click("[data-testid=power-add-Shiro-2]")
        await page.set_input_files("[data-testid=power-file]", {"name": "mi poder.png", "mimeType": "image/png", "buffer": PNG})
        await page.wait_for_function("document.querySelector('[data-testid=power-image]').value.startsWith('https://cdn.discordapp.com/attachments/')")
        assert rig.stored and rig.stored[-1][1] == "mi_poder.png"
        await page.keyboard.press("Escape")

        # remove a power and a character, both asking first
        await page.click("[data-testid=power-Shiro-1] .confirm-pair, [data-testid=power-Shiro-1] button:has-text('Quitar')")
        await page.click("[data-testid=power-Shiro-1] .btn-danger")
        await page.wait_for_selector("[data-testid=power-add-Shiro-1]")
        assert "power1" not in rig.panel_app.character_powers.get("Shiro", {})
        await page.click("[data-testid=char-drop-Zed]")
        assert "Zed" in rig.panel_app.character_registry                                   # one tap is not enough
        await page.click("[data-testid=char-drop-Zed-yes]")
        await page.wait_for_selector("[data-testid=char-Zed]", state="detached")
        assert "Zed" not in rig.panel_app.character_registry
        await phone.wait_for_function("!window.__eventos.characters.includes('Zed')")
        assert page.errors == [] and phone.errors == []
    run(scenario)


def test_characters_come_in_from_a_tupperbox_export_with_their_pictures_kept_on_this_pc(tmp_path):
    import json

    from aiohttp import web
    from eventos_app.activity import media

    async def scenario(rig, browser, url, me):
        async def avatar(request):
            return web.Response(body=PIXEL, content_type="image/png")                       # a real picture, so the page can draw it

        pictures = web.Application()
        pictures.router.add_get("/kuro.png", avatar)
        runner = web.AppRunner(pictures)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        origin = f"http://127.0.0.1:{runner.addresses[0][1]}"
        try:
            store = media.MediaStore(tmp_path / "media")
            rig.server.files = rig.bridge.files = store
            rig.bridge.images_file, rig.bridge.fetch_allow_private = tmp_path / "images.json", True
            page = await open_page(browser, url)
            await panel_at(page, "characters")
            await page.click("[data-testid=tupper-open]")
            export = {"tuppers": [{"name": "Zed", "avatar_url": origin + "/kuro.png"}, {"name": "Kuro", "avatar_url": None}, {"name": "Lia", "avatar_url": origin + "/kuro.png"}]}
            await page.set_input_files("[data-testid=tupper-file]", files=[{"name": "no.json", "mimeType": "application/json", "buffer": b"esto no es json"}])
            assert "no es JSON" in await page.locator("[data-testid=tupper-error]").inner_text()
            await page.set_input_files("[data-testid=tupper-file]", files=[{"name": "tuppers.json", "mimeType": "application/json", "buffer": json.dumps(export).encode()}])
            await page.wait_for_selector("[data-testid=tupper-list]")
            assert await page.locator("[data-testid=tupper-Kuro]").inner_text() != ""
            assert "ya es tuyo" in await page.locator("[data-testid=tupper-Kuro]").inner_text()      # Kuro is already registered to this player
            await page.locator("[data-testid=tupper-Lia] input").uncheck()
            await page.click("[data-testid=tupper-go]")
            await page.wait_for_selector("[data-testid=tupper-summary]")
            summary = await page.locator("[data-testid=tupper-summary]").inner_text()
            results = await page.locator("[data-testid=tupper-results]").inner_text()
            await page.click("[data-testid=tupper-close]")
            await page.wait_for_selector("[data-testid=char-Zed]")
            assert await page.locator("[data-testid=char-Lia]").count() == 0                  # not chosen: not registered
            picture = await page.locator("[data-testid=char-Zed] img").first.get_attribute("src")
            loaded = await page.evaluate("(src) => fetch(src).then((r) => [r.status, r.headers.get('content-type')])", picture)
            assert page.errors == []
            return summary, results, picture, loaded, store.usage(media.IMAGES), rig.panel_app.character_registry

        finally:
            await runner.cleanup()

    summary, results, picture, loaded, usage, registry = run(scenario)
    assert summary.startswith("2 personajes listos") and "Zed" in results and "imagen guardada" in results and "sin imagen" in results
    assert picture.startswith("/files/images/") and loaded == [200, "image/png"] and usage[0] == 1
    assert "Zed" in registry and "Lia" not in registry


def test_the_skill_tree_shows_what_can_be_learned_and_spends_the_points():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await panel_at(page, "skills")
        await page.wait_for_selector("[data-testid=skills]")
        assert (await page.locator("[data-testid=skill-points]").inner_text()) == "3"
        assert await page.locator(".skill-lines path").count() >= 4                                 # the lines between a skill and what it needs
        assert await page.locator("[data-testid=skill-combat_1]").get_attribute("data-state") == "available"
        assert await page.locator("[data-testid=skill-defense_2a]").get_attribute("data-state") == "locked"

        await page.click("[data-testid=skill-defense_2a]")                                           # locked: it says why and cannot be learned
        assert "Necesitas: Voluntad de hierro" in await page.locator("[data-testid=skill-status]").inner_text()
        assert await page.locator("[data-testid=skill-learn]").is_disabled()
        await page.keyboard.press("Escape")

        await page.click("[data-testid=skill-combat_2a]")
        assert not await page.locator("[data-testid=skill-learn]").is_disabled()
        await page.click("[data-testid=skill-learn]")
        await page.wait_for_function("document.querySelector('[data-testid=skill-points]').textContent === '1'")
        assert rig.panel_app.player_skills[str(me)]["skills"]["combat_2a"] == 1
        assert "rango 1 de 5" in await page.locator("[data-testid=skill-combat_2a]").get_attribute("aria-label")
        await wait_toast(page, "rango 1")
        assert "Mejorar" in await page.locator("[data-testid=skill-learn]").inner_text()           # the dialog stays, ready to spend more points
        await page.keyboard.press("Escape")
        await page.click("[data-testid=skill-combat_2b]")                                            # costs 2 and only 1 point is left
        assert await page.locator("[data-testid=skill-learn]").is_disabled()
        assert "te faltan 1" in await page.locator("[data-testid=skill-status]").inner_text()
        assert page.errors == []
    run(scenario)


def test_the_inventory_shows_objects_with_their_adaptation_progress():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await panel_at(page, "inventory")
        await page.wait_for_selector("[data-testid=inventory]")
        assert (await page.locator("[data-testid=slots]").inner_text()).replace("\n", "") == "1 / 5"
        core = page.locator("[data-testid=obj-reactive_core]")
        assert "Núcleo reactivo" in await core.inner_text() and "Legendario" in await core.inner_text() and "Único" in await core.inner_text()
        assert await core.get_attribute("data-rarity") == "legendary"
        assert "5 / 10" in await page.locator("[data-testid=track-easy]").inner_text()
        await page.locator("[data-testid=track-easy] summary").click()
        assert "Reduces el daño un 10 %" in await page.locator("[data-testid=track-easy]").inner_text()
        shard = page.locator("[data-testid=obj-mirror_shard]")
        assert "7 / 20" in await shard.inner_text()
        assert page.errors == []
    run(scenario)


def test_counter_pictures_can_be_added_by_link_or_from_the_device_and_removed():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await panel_at(page, "images")
        await page.wait_for_selector("[data-testid=images]")
        assert await page.locator(".shot").count() == 1

        await page.fill("[data-testid=image-url]", "http://insecure.example/x.png")
        await page.click("[data-testid=image-add]")
        await wait_toast(page, "https")
        await page.fill("[data-testid=image-url]", "https://cdn.discordapp.com/attachments/1/2/new.png")
        await page.click("[data-testid=image-add]")
        await page.wait_for_function("document.querySelectorAll('.shot').length === 2")
        assert rig.panel_app.user_counter_gifs[me][-1].endswith("new.png")

        await page.set_input_files("[data-testid=image-file]", {"name": "contra.png", "mimeType": "image/png", "buffer": PNG})
        await page.wait_for_function("document.querySelectorAll('.shot').length === 3")
        assert rig.stored[-1][1] == "contra.png" and rig.panel_app.user_counter_gifs[me][-1].startswith("https://cdn.discordapp.com/attachments/10/")
        await page.set_input_files("[data-testid=image-file]", {"name": "malo.png", "mimeType": "image/png", "buffer": b"<svg onload=alert(1)>"})
        await wait_toast(page, "png, jpg, gif o webp")
        assert len(rig.panel_app.user_counter_gifs[me]) == 3

        await page.click("[data-testid=image-remove-0]")
        await page.wait_for_function("document.querySelectorAll('.shot').length === 2")
        await page.click("[data-testid=images-clear]")
        await page.click("[data-testid=images-clear-yes]")
        await page.wait_for_selector(".empty")
        assert me not in rig.panel_app.user_counter_gifs
        assert page.errors == []
    run(scenario)


def test_the_leaderboard_has_a_podium_when_three_people_play_and_marks_the_player():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await panel_at(page, "ranking")
        await page.wait_for_selector("[data-testid=ranking]")
        await page.wait_for_selector("[data-testid=board]")
        assert await page.locator("[data-testid=podium]").count() == 0                            # only two people: a list, not a podium
        rows = await page.locator("[data-testid=board] li").all_inner_texts()
        assert len(rows) == 2 and "(tú)" in rows[1] and "75 %" in rows[1] and "Mina" in rows[0] and "90 %" in rows[0]

        rig.panel_app.player_stats[444] = {"total_attempts": 5, "successful": 5, "black_flashes": 9, "saves": 1}
        rig.bridge._names[444] = (10**12, "Beto", None)
        await page.click("[data-testid=board-tab-black_flashes]")
        await page.wait_for_selector("[data-testid=podium]")
        assert "Beto" in await page.locator("[data-testid=podium-1]").inner_text() and "9" in await page.locator("[data-testid=podium-1]").inner_text()
        assert "(tú)" in await page.locator("[data-testid=podium-3]").inner_text()
        await page.click("[data-testid=board-tab-best_time]")
        await page.wait_for_function("document.querySelector('[data-testid=ranking]').textContent.includes('0,8 s')")
        assert page.errors == []
    run(scenario)


def test_every_tab_fits_a_phone_without_sideways_scrolling():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url, width=360, height=740, mobile=True)
        await page.click("[data-testid=menu-button]")
        await page.click("[data-testid=tile-summary]")
        for tab in ("summary", "achievements", "characters", "skills", "inventory", "images", "ranking"):
            await page.click(f"[data-testid=dash-tab-{tab}]")
            await page.wait_for_selector(f"[data-testid={tab}]")
            await asyncio.sleep(0.25)
            overflow = await page.evaluate("""() => ({
                page: document.documentElement.scrollWidth - window.innerWidth,
                body: (document.querySelector('.dash-body') || {}).scrollWidth - (document.querySelector('.dash-body') || {}).clientWidth,
                tab: (() => { const r = document.querySelector('.dash-tab[aria-selected=true]').getBoundingClientRect(); return [r.left, r.right, window.innerWidth]; })() })""")
            assert overflow["page"] <= 1 and overflow["body"] <= 1, (tab, overflow)
            assert overflow["tab"][0] >= -2 and overflow["tab"][1] <= overflow["tab"][2] + 2, (tab, overflow)       # the chosen tab is in view
        assert page.errors == []
    run(scenario)


def test_every_theme_accent_and_corner_style_really_changes_how_the_page_looks():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        css = "(n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim()"
        seen = {}
        for theme in ("dark", "oled", "contrast", "midnight", "ember", "forest", "rose", "sepia"):
            await page.evaluate("(t) => window.__eventos.setPrefs({ theme: t })", theme)
            await page.wait_for_function("(t) => document.documentElement.dataset.theme === t", arg=theme)
            seen[theme] = await page.evaluate(css, "--surface")
        assert len(set(seen.values())) == len(seen), seen                                  # no two themes look the same
        await page.evaluate("window.__eventos.setPrefs({ accent: 'amber', corners: 'sharp', bg: 'grid' })")
        await page.wait_for_function("document.documentElement.dataset.accent === 'amber'")
        assert await page.evaluate(css, "--primary") == "#f59e0b"
        assert await page.evaluate(css, "--r-md") == "5px"
        assert await page.evaluate("getComputedStyle(document.body, '::before').position") == "fixed"
        assert page.errors == []
    run(scenario)


def test_a_player_gives_what_happens_to_them_a_look_of_their_own_and_sees_it_when_it_happens():
    async def scenario(rig, browser, url, me):
        page = await open_page(browser, url)
        await panel_at(page, "effects")
        await page.wait_for_selector("[data-testid=my-fx]")
        assert await page.locator("[data-testid=fx-sound-mine-parry_ok]").count() == 0                 # the library is the game masters'
        await page.click("[data-testid=fx-edit-mine-parry_ok]")
        await page.click("[data-testid=fx-preset-mine-parry_ok-slash]")
        await page.fill("[data-testid=fx-banner-mine-parry_ok]", "¡Mi tajo!")
        await page.wait_for_function("document.querySelector('[data-testid=fx-sum-mine-parry_ok]').innerText.includes('Corte')", timeout=5000)
        await asyncio.sleep(0.9)                                                                      # it saves by itself
        saved = rig.bridge.fx.book.people.get(str(me), {}).get("parry_ok")
        assert saved and saved["preset"] == "slash" and saved["banner"] == "¡Mi tajo!" and saved["scope"] == "target"
        await rig.bridge.fx.dispatch("parry_ok", {"user": me})
        await page.wait_for_selector(".vfx-banner", timeout=4000)
        assert "mi tajo" in (await page.locator(".vfx-banner").first.inner_text()).lower()
        assert page.errors == []

    run(scenario)
