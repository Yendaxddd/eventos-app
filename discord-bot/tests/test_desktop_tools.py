"""The desktop app's pure parts (no display needed): opening the Activity in a window of its own, and the copies of the event's data."""
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from desktop_fakes import fake_bot  # noqa: E402
from eventos_app import backups, browser  # noqa: E402


# ---- the host's own window ---------------------------------------------------------------------------------------------------
def test_edge_is_preferred_then_chrome_and_other_systems_use_what_is_installed():
    env = {"ProgramFiles(x86)": r"C:\Program Files (x86)", "ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\Ana\AppData\Local"}
    edge86 = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    nothing = lambda name: None  # noqa: E731
    assert browser.find_app_browser("win32", env, nothing, lambda p: p in (edge86, chrome)) == edge86
    assert browser.find_app_browser("win32", env, nothing, lambda p: p == chrome) == chrome
    assert browser.find_app_browser("win32", env, nothing, lambda p: False) is None
    assert browser.find_app_browser("win32", {}, nothing, lambda p: True) is None                       # no Program Files at all
    assert browser.find_app_browser("linux", env, {"chromium": "/usr/bin/chromium"}.get, lambda p: False) == "/usr/bin/chromium"
    assert browser.find_app_browser("linux", env, {"google-chrome": "/opt/gc", "chromium": "/usr/bin/chromium"}.get, lambda p: False) == "/opt/gc"
    assert browser.find_app_browser("linux", env, nothing, lambda p: False) is None


def test_the_host_address_is_a_test_window_with_the_gm_panel_that_the_player_list_hides():
    assert browser.host_url(8765) == "http://127.0.0.1:8765/?dev=Anfitri%C3%B3n&gm=1&host=1"
    assert browser.host_url(9000, gm=False, name="Ana López") == "http://127.0.0.1:9000/?dev=Ana%20L%C3%B3pez"
    command = browser.app_window_command("http://127.0.0.1:8765/?dev=A", "msedge.exe", (1000, 700))
    assert command[0] == "msedge.exe" and "--app=http://127.0.0.1:8765/?dev=A" in command and "--window-size=1000,700" in command


def test_the_window_opens_as_an_app_window_and_falls_back_to_the_normal_browser():
    started, opened = [], []

    def spawn(command, **kwargs):
        started.append((command, kwargs))

    assert browser.open_app_window("http://x/", find=lambda: "edge", spawn=spawn, fallback=opened.append) == "window"
    assert started[0][0][:2] == ["edge", "--app=http://x/"] and opened == []
    assert browser.open_app_window("http://x/", find=lambda: None, spawn=spawn, fallback=opened.append) == "browser" and opened == ["http://x/"]

    def broken(command, **kwargs):
        raise OSError("blocked by a policy")

    assert browser.open_app_window("http://y/", find=lambda: "edge", spawn=broken, fallback=opened.append) == "browser" and opened[-1] == "http://y/"


# ---- copies of the data ------------------------------------------------------------------------------------------------------
@pytest.fixture()
def home(tmp_path):
    data = tmp_path / "data"
    (data / "special_objects" / "approved").mkdir(parents=True)
    (data / "player_stats.json").write_text('{"111": {"successful": 3}}', encoding="utf-8")
    (data / "special_objects" / "approved" / "core.json").write_text('{"id": "core"}', encoding="utf-8")
    (data / "half_written.json.tmp").write_text("{", encoding="utf-8")
    (tmp_path / "settings.json").write_text('{"discord_token": "SECRET-TOKEN"}', encoding="utf-8")        # never part of a copy
    return tmp_path


def names(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as zf:
        return set(zf.namelist())


def test_a_copy_holds_the_data_and_a_manifest_but_never_the_settings_or_half_written_files(home):
    path = backups.make_backup(home, now=1_800_000_000)
    assert path.parent == home / "backups" and path.name.startswith("EventosApp-datos-") and path.suffix == ".zip"
    assert names(path) == {"data/player_stats.json", "data/special_objects/approved/core.json", "manifest.json"}
    assert "SECRET-TOKEN" not in b"".join(zipfile.ZipFile(path).read(n) for n in names(path)).decode("utf-8", "ignore")
    manifest = json.loads(zipfile.ZipFile(path).read("manifest.json"))
    assert manifest["files"] == 2 and manifest["app"] == "Eventos App" and manifest["version"]
    assert not list((home / "backups").glob("*.part"))


def test_two_copies_in_the_same_second_do_not_overwrite_each_other_and_a_label_shows_in_the_list(home):
    first = backups.make_backup(home, now=1_800_000_000)
    second = backups.make_backup(home, now=1_800_000_000)
    third = backups.make_backup(home, label="Antes de la Final!", now=1_800_000_000)
    assert len({first, second, third}) == 3 and second.name.endswith("_2.zip") and third.name.endswith("-antes-de-la-final.zip")
    listed = backups.list_backups(home)
    assert {b.path for b in listed} == {first, second, third} and {b.label for b in listed} == {"", "antes-de-la-final"}
    assert all(b.size > 0 for b in listed)


def test_the_list_is_newest_first_and_ignores_what_is_not_a_copy(home):
    old = backups.make_backup(home, now=1_700_000_000)
    new = backups.make_backup(home, label=backups.AUTOMATIC, now=1_800_000_000)
    (home / "backups" / "notes.txt").write_text("x", encoding="utf-8")
    (home / "backups" / "EventosApp-datos-garbage.zip").write_bytes(b"")
    listed = backups.list_backups(home)
    assert [b.path for b in listed] == [new, old]
    assert "Automática" in listed[0].title and "Manual" in listed[1].title
    assert backups.list_backups(home / "nowhere") == []


def test_only_the_automatic_copies_are_dropped_when_there_are_too_many(home):
    manual = backups.make_backup(home, now=1_700_000_000)
    safety = backups.make_backup(home, label=backups.SAFETY, now=1_700_000_100)
    automatic = [backups.make_backup(home, label=backups.AUTOMATIC, keep=3, now=1_800_000_000 + i * 60) for i in range(6)]
    left = {b.path for b in backups.list_backups(home)}
    assert manual in left and safety in left                                            # copies made on purpose stay until the person deletes them
    assert {p for p in automatic} & left == set(automatic[-3:])                         # the three newest automatic ones


def test_nothing_to_copy_is_said_in_plain_words(tmp_path):
    with pytest.raises(backups.BackupError, match="no hay datos"):
        backups.make_backup(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.json.tmp").write_text("{", encoding="utf-8")
    with pytest.raises(backups.BackupError):
        backups.make_backup(tmp_path)


def test_restoring_puts_the_data_back_exactly_and_keeps_a_copy_of_what_was_there(home):
    original = backups.make_backup(home, now=1_800_000_000)
    (home / "data" / "player_stats.json").write_text('{"111": {"successful": 99}}', encoding="utf-8")
    (home / "data" / "new_file.json").write_text("{}", encoding="utf-8")
    (home / "data" / "special_objects" / "approved" / "core.json").unlink()
    safety = backups.restore_backup(home, original)
    assert json.loads((home / "data" / "player_stats.json").read_text(encoding="utf-8")) == {"111": {"successful": 3}}
    assert (home / "data" / "special_objects" / "approved" / "core.json").read_text(encoding="utf-8") == '{"id": "core"}'
    assert not (home / "data" / "new_file.json").exists()                                # what the copy did not have is gone: the state is the copy's
    assert safety is not None and "new_file.json" in "".join(names(safety)) and backups.SAFETY in safety.name   # nothing was lost
    assert not [p for p in home.iterdir() if p.name.startswith((".restore-", ".data-replaced-"))]
    assert (home / "settings.json").exists()


def test_restoring_into_a_fresh_install_needs_no_safety_copy(home, tmp_path_factory):
    original = backups.make_backup(home, now=1_800_000_000)
    fresh = tmp_path_factory.mktemp("fresh")
    assert backups.restore_backup(fresh, original) is None
    assert (fresh / "data" / "player_stats.json").exists()


@pytest.mark.parametrize("evil", ["data/../../evil.txt", "../evil.txt", "/etc/evil.txt", "C:/evil.txt", "data\\..\\evil.txt", "other/evil.txt", "evil.txt", "data/./../x"])
def test_a_copy_with_names_that_lead_out_of_the_data_folder_restores_nothing(home, tmp_path, evil):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("data/fine.json", "{}")
        zf.writestr(evil, "owned")
    before = {p.relative_to(home): p.read_bytes() for p in (home / "data").rglob("*") if p.is_file()}
    with pytest.raises(backups.BackupError):
        backups.restore_backup(home, bad)
    after = {p.relative_to(home): p.read_bytes() for p in (home / "data").rglob("*") if p.is_file()}
    assert before == after                                                              # the data is as it was
    assert not (home.parent / "evil.txt").exists() and not (home / "evil.txt").exists()
    assert not list(home.glob(".restore-*")) and not list(home.glob(".data-replaced-*"))


def test_something_that_is_not_a_copy_is_refused_politely(home, tmp_path):
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"this is not a zip")
    with pytest.raises(backups.BackupError, match="no es una copia válida"):
        backups.restore_backup(home, junk)
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr(backups.MANIFEST, "{}")
    with pytest.raises(backups.BackupError, match="vacía"):
        backups.restore_backup(home, empty)
    with pytest.raises(backups.BackupError):
        backups.restore_backup(home, tmp_path / "missing.zip")
    assert (home / "data" / "player_stats.json").exists()


def test_a_failure_while_swapping_leaves_the_old_data_in_place(home, monkeypatch):
    original = backups.make_backup(home, now=1_800_000_000)
    (home / "data" / "player_stats.json").write_text('{"changed": true}', encoding="utf-8")
    real_rename = Path.rename

    def flaky(self, target):
        if self.name == "data" and self.parent.name.startswith(".restore-"):               # moving the restored data into place fails
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(backups.BackupError):
        backups.restore_backup(home, original)
    assert json.loads((home / "data" / "player_stats.json").read_text(encoding="utf-8")) == {"changed": True}      # the old data came back


def test_only_copies_in_the_copies_folder_can_be_deleted(home, tmp_path):
    made = backups.make_backup(home, now=1_800_000_000)
    outside = tmp_path / "EventosApp-datos-20261019-083000.zip"
    outside.write_bytes(b"x")
    with pytest.raises(backups.BackupError):
        backups.delete_backup(home, outside)
    with pytest.raises(backups.BackupError):
        backups.delete_backup(home, home / "data" / "player_stats.json")
    backups.delete_backup(home, made)
    assert not made.exists() and outside.exists()


def test_the_summary_counts_what_the_data_folder_holds(home):
    summary = backups.data_summary(home)
    assert summary["files"] == 2 and summary["bytes"] > 10 and summary["newest"] <= time.time() + 5
    assert backups.data_summary(home / "nowhere") == {"files": 0, "bytes": 0, "newest": None}


# ---- what the window shows about the event ----------------------------------------------------------------------------------------------------
def test_the_event_snapshot_lists_the_fight_the_boss_and_the_most_hurt_players_first():
    from eventos_app.snapshot import event_snapshot

    snap = event_snapshot(fake_bot(), online={1})
    assert snap["fight"] is True and snap["boss"]["name"] == "Rey de las Maldiciones" and snap["boss"]["hp"] == 640 and snap["boss"]["max"] == 1000
    assert [q["id"] for q in snap["qtes"]] == ["7"] and snap["session"] == {"qtes": 14, "blackFlashes": 3}
    assert [p["name"] for p in snap["players"]] == ["Jugador …3", "Mina", "Luis", "Ana"]                # 0, 10, 55 and 80 HP: the ones in trouble first
    mina, luis, ana = snap["players"][1:]
    assert mina["revenge"] is True and mina["online"] is False and luis["afk"] is True and ana["online"] is True and snap["players"][0]["alive"] is False
    assert ana["charges"] == [100.0, 40.0] and snap["playerCount"] == 4
    assert json.loads(json.dumps(snap, allow_nan=False)) == snap                                       # plain data


def test_the_snapshot_never_breaks_the_window_whatever_the_bot_is_doing():
    from types import SimpleNamespace as NS

    from eventos_app.snapshot import event_snapshot

    assert event_snapshot(None) == {}
    assert event_snapshot(NS())["players"] == [] and event_snapshot(NS())["boss"] is None                  # a bot that has done nothing yet
    broken = fake_bot(resolve_event_guild=lambda: (_ for _ in ()).throw(RuntimeError("not ready")))
    assert event_snapshot(broken)["players"][0]["name"].startswith("Jugador")                              # no server yet: ids instead of names


# ---- «Antes de empezar» --------------------------------------------------------------------------------------------------------------------------------
def steps(**kwargs):
    from eventos_app import readiness

    base = dict(token_set=True, connected=True, starting=False, event_ready=True, activity_enabled=True, secret_set=True, tunnel="up", activity_running=True)
    base.update(kwargs)
    return {s.key: s for s in readiness.checklist(**base)}


def test_the_checklist_says_what_is_missing_in_order_and_where_to_fix_it():
    from eventos_app import readiness

    everything = readiness.checklist(token_set=True, connected=True, starting=False, event_ready=True, activity_enabled=True, secret_set=True, tunnel="up")
    assert readiness.all_done(everything) and [s.key for s in everything] == ["token", "start", "event", "activity"]
    fresh = steps(token_set=False, connected=False, event_ready=False, secret_set=False)
    assert fresh["token"].state == "todo" and fresh["token"].action == "config" and fresh["start"].state == "wait" and fresh["event"].state == "wait"
    ready_to_go = steps(connected=False, event_ready=False)
    assert ready_to_go["token"].state == "done" and ready_to_go["start"].state == "todo" and ready_to_go["start"].action == "start"
    assert steps(connected=False, starting=True)["start"].state == "wait" and steps(connected=False, starting=True)["start"].action == ""
    assert steps(event_ready=False)["event"].state == "todo" and steps(event_ready=False)["event"].action == "event"


def test_the_activity_step_follows_its_switch_its_secret_and_its_tunnel():
    assert steps(activity_enabled=False)["activity"].state == "off" and steps(activity_enabled=False)["activity"].action == "activity"
    assert steps(secret_set=False)["activity"].state == "todo" and "Client Secret" in steps(secret_set=False)["activity"].detail
    assert steps(connected=False)["activity"].state == "wait"
    assert steps(tunnel="error", tunnel_detail="Tailscale no está instalado")["activity"].detail == "Tailscale no está instalado"
    assert steps(tunnel="error")["activity"].state == "todo" and steps(tunnel="opening")["activity"].state == "wait"
    from eventos_app import readiness

    assert readiness.all_done(list(steps(activity_enabled=False).values())) is True                    # an optional part that is switched off is not a pending step


# ---- the report a person pastes when asking for help ---------------------------------------------------------------------------------------------------------
def test_the_support_report_never_contains_a_secret_even_inside_the_log_lines():
    from eventos_app import support
    from eventos_app.settings import Settings

    token = "MTA0MDAwMDAwMDAwMDAwMDAw.GabcDE.abcdefghijklmnopqrstuvwxyz123456"
    helper = "NzAwMDAwMDAwMDAwMDAwMDAw.GfghIJ.abcdefghijklmnopqrstuvwxyz654321"
    settings = Settings(discord_token=token, activity_client_secret="a-client-secret-value", helper_bots=[{"token": helper, "name": "Ayudante"}], activity_enabled=True)
    report = support.support_report(settings, state="Conectado", connection="EventBot#1234 · 1 servidor", event="Evento: Mi servidor › #qte",
                                    activity={"running": True, "port": 8765, "tunnel": "up", "detail": "", "users": [{"name": "Ana", "hidden": False}, {"name": "Anfitrión", "hidden": True}]},
                                    log_lines=[f"línea {i}" for i in range(60)] + [f"login con {token}", "cliente a-client-secret-value ok", f"ayudante {helper}"])
    for secret in (token, helper, "a-client-secret-value", "GabcDE", "GfghIJ"):
        assert secret not in report
    assert "«oculto»" in report and "Eventos App" in report and "Conectado · EventBot#1234" in report
    assert "Conectados: 1" in report                                                          # the host's own window is not a person
    assert "línea 59" in report and "línea 10" not in report and "login con «oculto»" in report       # only the last lines, with the secrets blanked
    assert "Token del bot: puesto" in report and "Bots auxiliares: 1" in report


def test_redact_hides_every_given_secret_and_ignores_short_or_empty_ones():
    from eventos_app import support

    assert support.redact("hola abc12345 y abc12345", ["abc12345", "", "  ", "x"]) == "hola «oculto» y «oculto»"
    assert support.redact("x is not secret", ["x"]) == "x is not secret"                      # too short to be a secret: it would hide ordinary letters


def test_a_copy_on_stop_is_made_only_when_something_changed_since_the_last_one(home, monkeypatch):
    from eventos_app import paths
    from eventos_app.runner import BotRunner

    monkeypatch.setattr(paths, "app_home", lambda: home)
    runner = BotRunner()
    assert backups.changed_since_last(home) is True                                      # data and no copy yet
    runner._backup_on_stop()
    assert len(backups.list_backups(home)) == 1 and backups.list_backups(home)[0].label == backups.AUTOMATIC
    assert backups.changed_since_last(home) is False
    runner._backup_on_stop()                                                             # stopping again with nothing new: no duplicate
    assert len(backups.list_backups(home)) == 1
    later = time.time() + 120
    os.utime(home / "data" / "player_stats.json", (later, later))                        # the bot saved something after the copy
    assert backups.changed_since_last(home) is True
    assert backups.changed_since_last(home / "nowhere") is False                         # nothing to copy at all
    runner._backup_on_stop()
    assert len(backups.list_backups(home)) == 2


def test_a_failing_copy_on_stop_never_gets_in_the_way_of_stopping(home, monkeypatch):
    from eventos_app import paths
    from eventos_app.runner import BotRunner

    monkeypatch.setattr(paths, "app_home", lambda: home)
    monkeypatch.setattr(backups, "make_backup", lambda *a, **k: (_ for _ in ()).throw(backups.BackupError("sin espacio")))
    BotRunner()._backup_on_stop()                                                        # no exception


# ---- «¿hay una versión nueva?» ------------------------------------------------------------------------------------------------------------------------------------
def test_versions_are_compared_by_number_not_by_text():
    from eventos_app import updates

    assert updates.parse_version("v1.0.0") == (1, 0, 0) and updates.parse_version("0.11.2-beta") == (0, 11, 2) and updates.parse_version("1.2") == (1, 2, 0)
    assert updates.parse_version("latest") is None and updates.parse_version("") is None and updates.parse_version(None) is None
    assert updates.is_newer("v0.12.0", "0.11.0") and updates.is_newer("1.0.0", "0.99.9") and updates.is_newer("0.10.0", "0.9.9")     # 10 is more than 9
    assert not updates.is_newer("0.11.0", "0.11.0") and not updates.is_newer("0.9.0", "0.10.0") and not updates.is_newer("rubbish", "0.1.0")


def release(tag="v1.0.1", **extra):
    base = {"tag_name": tag, "html_url": f"https://github.com/x/y/releases/tag/{tag}", "body": "## Novedades en 1.0.1 — Algo\n\nMás cosas.",
            "assets": [{"name": "EventosApp-windows.zip", "browser_download_url": "https://x/zip"},
                       {"name": "EventosApp-Setup-1.0.1.exe", "browser_download_url": "https://x/setup.exe"}]}
    base.update(extra)
    return base


def test_a_newer_release_is_reported_with_its_page_its_first_line_and_the_installer():
    from eventos_app import updates

    found = updates.check("1.0.0", fetch=lambda url: release())
    assert found.version == "1.0.1" and found.url.endswith("/v1.0.1") and found.notes == "Novedades en 1.0.1 — Algo" and found.installer == "https://x/setup.exe"
    assert updates.check("1.0.1", fetch=lambda url: release()) is None                        # up to date
    assert updates.check("1.0.0", fetch=lambda url: release(prerelease=True)) is None          # not a release to bother anyone with
    assert updates.check("1.0.0", fetch=lambda url: release(draft=True)) is None
    assert updates.check("1.0.0", fetch=lambda url: release(assets=[], body="")).installer == ""


def test_everything_that_can_go_wrong_while_checking_is_silent():
    from eventos_app import updates

    def offline(url):
        raise OSError("sin internet")

    assert updates.check("1.0.0", fetch=offline) is None
    assert updates.check("1.0.0", fetch=lambda url: ["not", "a", "dict"]) is None
    assert updates.check("1.0.0", fetch=lambda url: {}) is None
    assert updates.check("1.0.0", fetch=lambda url: {"tag_name": "nightly"}) is None
    found = updates.check("1.0.0", fetch=lambda url: release(assets=None, body=None))
    assert found.installer == "" and found.notes == ""                                         # a release without assets or notes still counts
