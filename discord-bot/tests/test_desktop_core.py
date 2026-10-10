"""Tests for the GUI-independent parts of the desktop app (no display needed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eventos_app import paths, settings  # noqa: E402
from eventos_app.console_bridge import ConsoleProxy, to_segments  # noqa: E402


# ---- console bridge --------------------------------------------------------
def test_markup_becomes_coloured_segments():
    segs = to_segments(("[green]ok[/green] plain",))
    assert segs[0].text == "ok" and segs[0].color == "#008000"
    assert "".join(s.text for s in segs) == "ok plain"
    assert segs[-1].color is None


def test_unknown_colour_and_unbalanced_markup_never_raise():
    assert "".join(s.text for s in to_segments(("[nosuchcolour]hi[/nosuchcolour]",))) == "hi"
    assert "".join(s.text for s in to_segments(("oops [/red] closing",))) == "oops [/red] closing"


def test_renderables_are_flattened_to_text():
    from rich.panel import Panel

    text = "".join(s.text for s in to_segments((Panel.fit("[bold]hola[/bold]"),)))
    assert "hola" in text and "[bold]" not in text


def test_proxy_sends_to_sink_and_survives_a_broken_sink():
    got = []
    proxy = ConsoleProxy()
    proxy.set_sink(got.append)
    proxy.print("[red]x[/red]", "y")
    assert "".join(s.text for s in got[0]) == "x y"

    def boom(_):
        raise RuntimeError("sink died")

    proxy.set_sink(boom)
    proxy.print("still fine")  # must not raise


def test_proxy_without_stdout_is_silent(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    ConsoleProxy().print("windowed build, no console")


# ---- settings --------------------------------------------------------------
def test_settings_roundtrip_and_env(tmp_path):
    f = tmp_path / "settings.json"
    s = settings.Settings(discord_token=" tok ", admin_role_id="123", reset_on_start=True, hotkeys_enabled=False)
    settings.save(s, f)
    loaded = settings.load(f)
    assert loaded == s
    env = loaded.to_env()
    assert env["DISCORD_TOKEN"] == "tok" and env["ADMIN_ROLE_ID"] == "123"
    assert env["EVENTOS_RESET_ON_START"] == "1" and env["EVENTOS_HOTKEYS"] == "0"
    assert "GM_ROLE_ID" not in env  # empty ids are not exported (the bot does int(env) on them)


def test_settings_validation_rejects_non_numeric_ids():
    problems = settings.Settings(gm_role_id="not a number").validate()
    assert len(problems) == 1 and "GM" in problems[0]
    assert settings.Settings(gm_role_id="123").validate() == []


def test_corrupt_settings_are_backed_up_not_fatal(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text("{ this is not json", encoding="utf-8")
    assert settings.load(f).discord_token == ""
    assert (tmp_path / "settings.json.bad").exists()


def test_unknown_keys_in_settings_file_are_ignored(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"discord_token": "t", "from_a_future_version": 1}), encoding="utf-8")
    assert settings.load(f).discord_token == "t"


# ---- paths -----------------------------------------------------------------
def test_eventos_home_override(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path / "h"))
    monkeypatch.setattr(paths, "_home_cache", None)
    assert paths.app_home() == (tmp_path / "h").resolve()
    assert paths.data_dir() == paths.app_home() / "data"
    assert paths.logs_dir().is_dir()
    monkeypatch.setattr(paths, "_home_cache", None)


def test_seed_defaults_copies_missing_files_only(tmp_path, monkeypatch):
    install = tmp_path / "install"
    (install / "data").mkdir(parents=True)
    (install / "data" / "a.json").write_text("shipped", encoding="utf-8")
    (install / "data" / "b.json").write_text("shipped", encoding="utf-8")
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "data" / "a.json").write_text("edited by user", encoding="utf-8")

    monkeypatch.setattr(paths, "install_dir", lambda: install)
    monkeypatch.setattr(paths, "_home_cache", home)
    paths.seed_defaults()
    assert (home / "data" / "a.json").read_text(encoding="utf-8") == "edited by user"
    assert (home / "data" / "b.json").read_text(encoding="utf-8") == "shipped"
    monkeypatch.setattr(paths, "_home_cache", None)


# ---- the bot module keeps working headless ----------------------------------
def test_bot_prompt_uses_env_preset_instead_of_stdin(monkeypatch, tmp_path):
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as bot

    fake = type("Fake", (), {})()
    monkeypatch.setenv("EVENTOS_RESET_ON_START", "1")
    assert bot.AdvancedQTEBot.prompt_reset_hp_and_charges(fake) == "reset"
    monkeypatch.setenv("EVENTOS_RESET_ON_START", "0")
    assert bot.AdvancedQTEBot.prompt_reset_hp_and_charges(fake) == "keep"
    monkeypatch.setattr(paths, "_home_cache", None)
