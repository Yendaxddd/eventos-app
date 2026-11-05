"""The desktop window, really built (CustomTkinter): its pages, what they show for a first run and for an event going on, and the buttons that
open the GM panel and make copies of the data. Skipped where there is no Tk or no display (they run on a virtual display with xvfb-run, and
on the Windows build)."""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

tk = pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")
pytest.importorskip("PIL")

pytestmark = pytest.mark.skipif(os.environ.get("EVENTOS_NO_UI_TESTS") == "1", reason="UI tests switched off")

from eventos_app import backups, browser, paths, updates  # noqa: E402


def _display_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


if not _display_available():
    pytest.skip("no display for Tk (run with xvfb-run)", allow_module_level=True)

from desktop_fakes import connect  # noqa: E402
from eventos_app.console_bridge import Segment  # noqa: E402


def open_window(tmp_path, monkeypatch, *, settings_json: str | None = None, ask_for_updates: bool = False):
    """The real window over an empty app folder (no token: a first run). The check for new versions is off unless a test asks for it."""
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    if ask_for_updates:
        monkeypatch.delenv("EVENTOS_NO_UPDATE_CHECK", raising=False)
    else:
        monkeypatch.setenv("EVENTOS_NO_UPDATE_CHECK", "1")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "player_stats.json").write_text('{"1": {"successful": 3}}', encoding="utf-8")
    if settings_json is not None:
        (tmp_path / "settings.json").write_text(settings_json, encoding="utf-8")
    from eventos_app.ui import App

    app = App()
    app.update()
    return app


@pytest.fixture()
def window(tmp_path, monkeypatch):
    app = open_window(tmp_path, monkeypatch)
    yield app
    app.destroy()


def settle(app, seconds: float = 0.5) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def wait_for(window, condition, seconds: float = 10.0) -> None:
    end = time.time() + seconds
    while time.time() < end:
        window._drain_background()
        window.update()
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for the window")


def labels(widget) -> list[str]:
    """Every text a widget shows, from itself and the ones inside it."""
    found = []
    for child in [widget, *widget.winfo_children()]:
        try:
            text = child.cget("text")
        except Exception:  # noqa: BLE001 - not every widget has text
            text = ""
        if isinstance(text, str) and text:
            found.append(text)
        if child is not widget:
            found.extend(labels(child))
    return found


def test_every_page_is_there_and_the_sidebar_shows_only_the_chosen_one(window):
    assert list(window.pages) == ["home", "activity", "data", "log", "config", "help"]
    for name in window.pages:
        window.show_page(name)
        settle(window, 0.05)
        assert window.current == name
        assert [n for n, page in window.pages.items() if page.winfo_ismapped()] == [name]
    assert window.nav_buttons["help"].cget("text_color") != window.nav_buttons["home"].cget("text_color")     # the chosen one is highlighted


def test_a_first_run_shows_the_checklist_with_the_token_first_and_the_quick_actions_asleep(window):
    window.show_page("home")
    wait_for(window, lambda: "Token del bot" in " ".join(labels(window.home.check_card)))
    assert window.home.check_card.winfo_ismapped() and not window.home.ready_strip.winfo_ismapped() and not window.home.event_card.winfo_ismapped()
    text = " ".join(labels(window.home.check_card))
    assert "Token del bot" in text and "Ir a Configuración" in text and "Servidor y canal del evento" in text
    assert all(str(button.cget("state")) == "disabled" for button in window.home.action_buttons.values())
    assert window.home.status_pill.cget("text") == "Detenido" and "Iniciar bot" in window.home.toggle_btn.cget("text")
    assert window.side_pill.cget("text") == "Detenido"
    window.toggle_bot()                                                                 # starting without a token takes you to the place that asks for it
    settle(window, 0.1)
    assert window.current == "config" and not window.runner.is_active()


def test_an_event_going_on_shows_the_fight_the_boss_the_players_and_wakes_the_quick_actions(window):
    connect(window)
    home = window.home
    wait_for(window, lambda: home.tiles["fight"]._value.cget("text") == "En curso" and len([b for b in home._players if b.winfo_ismapped()]) == 4)
    assert home.ready_strip.winfo_ismapped() and not home.check_card.winfo_ismapped() and home.event_card.winfo_ismapped()
    assert home.status_pill.cget("text") == "Conectado" and "Detener bot" in home.toggle_btn.cget("text")
    assert home.tiles["fight"]._value.cget("text") == "En curso" and home.tiles["qtes"]._value.cget("text") == "1"
    assert home.tiles["online"]._value.cget("text") == "3"                              # the host's own window is not a player
    assert home.tiles["session"]._value.cget("text") == "14"
    assert "Rey de las Maldiciones" in home.boss_bar.name.cget("text") and home.boss_bar.value.cget("text") == "640 / 1000"
    shown = [bar.name.cget("text") for bar in home._players if bar.winfo_ismapped()]
    assert shown == ["Jugador …3", "Mina  ·  modo venganza", "Luis  ·  fuera de los QTE", "Ana"]          # the most hurt first
    assert all(str(button.cget("state")) == "normal" for button in home.action_buttons.values())
    assert "F9" in home.action_buttons["single_easy"].cget("text")                      # the key of each button is on it
    assert "Mi servidor" in home.subtitle_label.cget("text")


def test_the_activity_page_shows_the_address_who_is_inside_and_how_good_their_connection_is(window):
    connect(window)
    window.show_page("activity")
    page = window.pages["activity"]
    wait_for(window, lambda: page.address.cget("text") == "equipo.tail1234.ts.net" and len([r for r in page._rows if r[0].winfo_ismapped()]) == 4)
    assert page.address.cget("text") == "equipo.tail1234.ts.net" and page.state_pill.cget("text") == "Lista"
    assert "solo la primera vez" in page.detail.cget("text")                            # a fixed address is pasted once
    rows = [(name.cget("text"), ping.cget("text")) for row, name, ping, since in page._rows if row.winfo_ismapped()]
    assert [r[0] for r in rows] == ["Ana", "Mina", "Luis", "Anfitrión  · esta app"]
    assert "excelente" in rows[0][1] and "buena" in rows[1][1] and "mala" in rows[2][1]
    assert page.count.cget("text") == "3 jugadores"
    window.runner._activity.tunnel.state, window.runner._activity.tunnel.detail = "error", "Tailscale no está instalado"
    wait_for(window, lambda: page.state_pill.cget("text") == "Error")
    assert "Tailscale no está instalado" in page.detail.cget("text")
    assert str(page.copy_btn.cget("state")) == "disabled"                               # there is no address to copy while the tunnel is down
    window.runner._activity = None
    wait_for(window, lambda: page.address.cget("text") == "Todavía no hay dirección")
    assert str(page.copy_btn.cget("state")) == "disabled"


def test_the_gm_panel_opens_in_a_window_of_its_own_at_the_hosts_address_and_says_why_it_cannot(window, monkeypatch):
    opened = []
    monkeypatch.setattr(browser, "open_app_window", lambda url, **kw: opened.append(url) or "window")
    window.open_gm_panel()                                                             # the Activity is not running
    assert opened == [] and window.current == "activity" and "no está en marcha" in window.toast_bar.cget("text")
    connect(window)
    window.show_page("home")
    window.open_gm_panel()
    assert opened == ["http://127.0.0.1:8765/?dev=Anfitri%C3%B3n&gm=1&host=1"]
    monkeypatch.setattr(browser, "open_app_window", lambda url, **kw: "browser")
    window.open_gm_panel()
    assert "navegador" in window.toast_bar.cget("text")


def test_the_log_is_the_same_stream_on_the_home_page_and_the_log_page_and_can_be_filtered(window):
    for text, color in (("✓ Todo bien", "#008000"), ("⚠ Sin webhook para Ayudante", "#ffa500"), ("QTE lanzado", None), ("✗ Falló el túnel", "#ff0000")):
        window._log_queue.append([Segment(text, color)])
    page = window.pages["log"]
    wait_for(window, lambda: "Falló el túnel" in window.home.log.box.get("1.0", "end"))
    window.show_page("log")
    settle(window, 0.2)
    everything = page.view.box.get("1.0", "end")
    assert all(word in everything for word in ("Todo bien", "Sin webhook", "QTE lanzado", "Falló el túnel"))
    assert "Sin webhook" in window.home.log.box.get("1.0", "end")                      # the Home page shows the same lines
    page.search.insert(0, "webhook")
    page._filter()
    only = page.view.box.get("1.0", "end")
    assert "Sin webhook" in only and "Todo bien" not in only and "QTE lanzado" not in only
    page.search.delete(0, "end")
    page.problems.select()
    page._filter()
    problems = page.view.box.get("1.0", "end")
    assert "Sin webhook" in problems and "Falló el túnel" in problems and "Todo bien" not in problems and "QTE lanzado" not in problems
    page.clear()
    page.problems.deselect()
    page._filter()
    assert page.view.box.get("1.0", "end").strip() == ""


def test_the_data_page_counts_the_data_makes_copies_and_restores_one_with_the_bot_stopped(window, monkeypatch):
    page = window.pages["data"]
    window.show_page("data")
    settle(window, 0.2)
    assert "1 archivos" in page.summary.cget("text") and "Todavía no hay copias" in " ".join(labels(page))
    page.create_now()
    wait_for(window, lambda: len(backups.list_backups(paths.app_home())) == 1)
    wait_for(window, lambda: any("Manual" in t for t in labels(page.list)))
    assert "Copia creada" in window.toast_bar.cget("text")
    (paths.data_dir() / "player_stats.json").write_text('{"1": {"successful": 99}}', encoding="utf-8")
    from tkinter import messagebox

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    copy = backups.list_backups(paths.app_home())[0]
    page.restore(copy)
    wait_for(window, lambda: '"successful": 3' in (paths.data_dir() / "player_stats.json").read_text(encoding="utf-8"))
    wait_for(window, lambda: len(backups.list_backups(paths.app_home())) == 2)             # the safety copy of what was there
    connect(window)                                                                      # with the bot running a restore is refused
    page.restore(copy)
    assert "Detén el bot" in window.toast_bar.cget("text")
    assert '"successful": 3' in (paths.data_dir() / "player_stats.json").read_text(encoding="utf-8")


def test_the_copy_on_stop_switch_is_remembered(window):
    page = window.pages["data"]
    window.show_page("data")
    settle(window, 0.2)
    assert window.settings.backup_on_stop is True and page.auto.get() == 1
    page.auto.deselect()
    page._auto_changed()
    assert window.settings.backup_on_stop is False
    from eventos_app import settings as settings_store

    assert settings_store.load().backup_on_stop is False and window.config_page.vars["backup_on_stop"].get() is False
    assert window.config_page.collect().backup_on_stop is False                         # saving the settings page does not undo it


def test_the_help_page_copies_the_support_report_without_any_secret(window):
    window.settings.discord_token = "MTA0MDAwMDAwMDAwMDAwMDAw.GabcDE.abcdefghijklmnopqrstuvwxyz123456"
    window.settings.activity_client_secret = "a-client-secret-value"
    window._log_queue.append([Segment("login con MTA0MDAwMDAwMDAwMDAwMDAw.GabcDE.abcdefghijklmnopqrstuvwxyz123456", None)])
    wait_for(window, lambda: any("login con" in line.plain for line in window.hub.lines))
    page = window.pages["help"]
    page.copy_report()
    copied = window.clipboard_get()
    assert "Eventos App" in copied and "Token del bot: puesto" in copied and "«oculto»" in copied
    assert "GabcDE" not in copied and "a-client-secret-value" not in copied


def test_the_settings_page_has_its_tabs_and_the_activity_settings_live_on_the_activity_page(window):
    page = window.config_page
    window.show_page("config", tab="send")
    settle(window, 0.2)
    assert "Bots auxiliares" in " ".join(labels(page.scroll)) and page.tabs.get() == "Envío"
    window.show_page("config", tab="start")
    settle(window, 0.2)
    assert page.tabs.get() == "Inicio e IA" and "IA (Ollama" in " ".join(labels(page.scroll))
    assert not any("Actividad de Discord (beta)" in text for text in labels(page.scroll))
    assert "Client Secret" in " ".join(labels(window.pages["activity"]))
    window.pages["activity"].app.config_page.vars["activity_client_secret"].set("abc")
    assert window.config_page.collect().activity_client_secret == "abc"


def test_a_newer_version_is_announced_in_the_sidebar_and_its_buttons_open_the_installer_and_the_news(window, monkeypatch):
    import webbrowser

    release = {"tag_name": "v9.9.9", "html_url": "https://github.com/Yendaxddd/eventos-app/releases/tag/v9.9.9", "body": "## Panel del GM en su ventana\n\n- más cosas",
               "assets": [{"name": "EventosApp-Setup-9.9.9.exe", "browser_download_url": "https://example.test/EventosApp-Setup-9.9.9.exe"}]}
    answers = [release]

    def fetch(url, timeout=6.0):
        if isinstance(answers[0], BaseException):
            raise answers[0]
        return answers[0]

    monkeypatch.setattr(updates, "fetch_json", fetch)
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)
    assert not window.update_card.winfo_ismapped()
    window.check_for_updates()
    wait_for(window, lambda: window.update_card.winfo_ismapped())
    assert "9.9.9" in window.update_title.cget("text") and window.update_notes.cget("text") == "Panel del GM en su ventana"
    window.update_download.invoke()
    window.update_news.invoke()
    assert opened == ["https://example.test/EventosApp-Setup-9.9.9.exe", release["html_url"]]
    answers[0] = {**release, "tag_name": "v0.0.1"}                                       # asked by hand, being up to date is said out loud
    window.check_for_updates(manual=True)
    wait_for(window, lambda: not window.update_card.winfo_ismapped())
    assert "al día" in window.toast_bar.cget("text")
    answers[0] = OSError("sin red")
    window.toast_bar.hide()
    window.check_for_updates()                                                           # on its own, not being able to find out is silent...
    settle(window, 0.3)
    assert not window.toast_bar.winfo_ismapped() and not window.update_card.winfo_ismapped()
    window.check_for_updates(manual=True)                                                # ...asked by hand, it says why
    wait_for(window, lambda: "conexión" in window.toast_bar.cget("text"))


def test_the_window_looks_for_a_new_version_once_after_opening_unless_it_is_switched_off(tmp_path, monkeypatch):
    from eventos_app import ui

    calls = []
    monkeypatch.setattr(ui, "UPDATE_CHECK_DELAY_MS", 50)
    monkeypatch.setattr(updates, "fetch_json", lambda url, timeout=6.0: calls.append(url) or {"tag_name": "v0.0.1"})
    app = open_window(tmp_path / "default", monkeypatch, ask_for_updates=True)
    try:
        wait_for(app, lambda: len(calls) == 1)
        settle(app, 0.3)
        assert len(calls) == 1 and not app.update_card.winfo_ismapped()                  # up to date: nothing is shown
    finally:
        app.destroy()
    calls.clear()
    app = open_window(tmp_path / "off", monkeypatch, ask_for_updates=True, settings_json='{"check_updates": false}')
    try:
        settle(app, 0.5)
        assert calls == [] and app.config_page.vars["check_updates"].get() is False
    finally:
        app.destroy()
