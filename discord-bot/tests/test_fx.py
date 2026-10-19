"""Effects for powers and events: the bindings and their rules, what plays for a power, and the Effects tab of the game-master panel."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import Hub, media  # noqa: E402
from eventos_app.activity.audio import EVENTS, AudioDirector, AudioLibrary  # noqa: E402
from eventos_app.activity.fx import BINDABLE, DEFAULT_BINDING, FxBook, FxDirector, is_empty, power_key, sanitize  # noqa: E402
from eventos_app.activity.hub import RpcError  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_play import frame, run  # noqa: E402
from test_audio import MP3, ask_seeing, conn_of  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "activity_client" / "test" / "fx-cases.json"


def test_a_binding_keeps_what_fits_and_agrees_with_the_client():
    assert sanitize(None) == DEFAULT_BINDING and sanitize("x") == DEFAULT_BINDING
    for case in json.loads(CASES.read_text(encoding="utf-8")):
        assert sanitize(case["raw"]) == case["expected"], case["raw"]
    assert is_empty(sanitize({"preset": "ninguno"})) and not is_empty(sanitize({"preset": "ninguno", "name": True}))


def test_the_book_is_kept_between_runs_and_a_damaged_file_never_breaks_it(tmp_path):
    path = tmp_path / "fx.json"
    book = FxBook(path)
    book.set_event("boss_defeated", {"preset": "explosion", "banner": "¡Cayó!"})
    book.set_power("Kuro", 1, {"preset": "slash", "color": "#ff0000"})
    book.set_defaults(False)
    again = FxBook(path)
    assert again.events["boss_defeated"]["banner"] == "¡Cayó!" and again.powers[power_key("Kuro", 1)]["color"] == "#ff0000" and again.defaults is False
    path.write_text('{"events": {"nope": {}, "heal": 5}, "powers": {"x": {}, "A|2": {"preset": "pulso"}}}', encoding="utf-8")
    odd = FxBook(path)
    assert list(odd.events) == ["heal"] and odd.events["heal"] == DEFAULT_BINDING and list(odd.powers) == ["A|2"]       # unknown things are dropped
    path.write_text("{not json", encoding="utf-8")
    assert FxBook(path).events == {}


def test_changes_are_checked_and_say_what_is_wrong(tmp_path):
    book = FxBook(tmp_path / "fx.json")
    for call, message in ((lambda: book.set_event("qte_start", {"preset": "slash"}), "no existe"), (lambda: book.set_event("heal", {"preset": "ninguno"}), "no hace nada"),
                          (lambda: book.set_power("", 1, {"preset": "slash"}), "no existe"), (lambda: book.set_power("Kuro", 3, {"preset": "slash"}), "no existe"),
                          (lambda: book.set_event("heal", {"preset": "slash", "sound": "ab"}, sounds=lambda i: None), "biblioteca")):
        try:
            call()
        except RpcError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(message)
    assert "qte_start" not in BINDABLE and "boss_defeated" in BINDABLE


def test_a_power_uses_its_own_effect_then_its_slots_then_any_power_then_a_look_by_its_type(tmp_path):
    book = FxBook(tmp_path / "fx.json")
    data = {"character": "Kuro", "slot": 1, "name": "Corte vacío", "type": "destructive"}
    assert book.binding_for("power_used", data)["preset"] == "explosion" and book.binding_for("power_used", data)["name"] is True      # nothing chosen: by type
    assert book.binding_for("power_used", {**data, "type": "unheard"})["preset"] == "impacto"
    book.set_defaults(False)
    assert book.binding_for("power_used", data) is None
    book.set_event("power_used", {"preset": "pulso"})
    assert book.binding_for("power_used", data)["preset"] == "pulso"
    book.set_event("power_1", {"preset": "rayo"})
    assert book.binding_for("power_used", data)["preset"] == "rayo" and book.binding_for("power_used", {**data, "slot": 2})["preset"] == "pulso"
    book.set_power("Kuro", 1, {"preset": "slash"})
    assert book.binding_for("power_used", data)["preset"] == "slash" and book.binding_for("power_used", {**data, "character": "Otro"})["preset"] == "rayo"
    assert book.binding_for("heal", {}) is None


def test_an_effect_reaches_every_screen_or_only_the_target_and_its_sound_follows(tmp_path):
    async def scenario():
        hub = Hub()
        library = AudioLibrary(media.MediaStore(tmp_path / "media"), tmp_path / "audio.json")
        audio = AudioDirector(hub, library)
        book = FxBook(tmp_path / "fx.json")
        director = FxDirector(hub, book, audio)
        (_, ana), (_, mina) = conn_of(hub, 1), conn_of(hub, 2)
        boom = library.add("boom.mp3", MP3)
        book.set_event("player_hit", {"preset": "impacto", "scope": "target", "sound": boom["id"], "delay": 100}, library.get)
        book.set_event("boss_defeated", {"preset": "dominio", "banner": "Fin"})
        out = [await director.dispatch("heal", {"user": 1}), await director.dispatch("player_hit", {"user": 2}), await director.dispatch("boss_defeated", {"name": "Rey"})]
        await asyncio.sleep(0.3)
        return out, ana.frames, mina.frames

    out, ana, mina = run(scenario())
    assert out == [False, True, True]
    assert [f["t"] for f in ana] == ["fx"] and ana[0]["fx"]["banner"] == "Fin" and ana[0]["ctx"]["name"] == "Rey"
    assert [f["t"] for f in mina] == ["fx", "fx", "audio"] and mina[0]["fx"]["scope"] == "target" and mina[2]["op"] == "play"      # the sound came after its delay


def test_the_effects_tab_works_for_game_masters_only_and_every_change_is_signed(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            rig.bridge.fx.book = FxBook(tmp_path / "fx.json")
            rig.app.character_powers = {"Kuro": {"power1": {"name": "Corte vacío", "type": "destructive", "effect": "damage:50"}, "power2": {"name": "Calma", "type": "support"}}}
            gm, _ = await rig.login(ME)
            player, _ = await rig.login(OTHER)
            state = await rig.ask(gm, "gm.fx")
            await player.send_json({"t": "rpc", "id": "p1", "op": "gm.fx", "args": {}})
            refused = None
            while refused is None:
                got = await asyncio.wait_for(player.receive_json(), 3)
                if got.get("id") == "p1":
                    refused = got
            saved = await rig.ask(gm, "gm.fx_set", **{"for": "power", "character": "Kuro", "slot": 1, "binding": {"preset": "slash", "banner": "¡Tajo!"}})
            event = await rig.ask(gm, "gm.fx_set", **{"for": "event", "event": "boss_defeated", "binding": {"preset": "explosion"}})
            nothing = await rig.ask(gm, "gm.fx_set", **{"for": "event", "event": "heal", "binding": {"preset": "ninguno"}})
            _, around = await ask_seeing(rig, gm, "gm.fx_preview", binding={"preset": "rayo"}, name="Prueba")
            seen = next(f for f in around if f["t"] == "fx")
            quiet = rig.bridge.fx.book.defaults
            off = await rig.ask(gm, "gm.fx_defaults", on=False)
            cleared = await rig.ask(gm, "gm.fx_clear", **{"for": "power", "character": "Kuro", "slot": 1})
            return state, refused, saved, event, nothing, seen, quiet, off, cleared, rig.bridge.gm.log.recent()

    state, refused, saved, event, nothing, seen, quiet, off, cleared, history = run(scenario())
    data = state["data"]
    assert [p["name"] for p in data["powers"]] == ["Corte vacío", "Calma"] and data["defaults"] is True and "ninguno" in data["presets"]
    assert {e["id"] for e in data["events"]} == set(BINDABLE) and all(e["id"] in EVENTS for e in data["events"])
    assert refused["t"] == "rpc_err" and "equipo de GM" in refused["reason"]
    assert saved["data"]["powers"][0]["binding"]["banner"] == "¡Tajo!" and event["data"]["events"][[e["id"] for e in event["data"]["events"]].index("boss_defeated")]["binding"]["preset"] == "explosion"
    assert nothing["t"] == "rpc_err" and "no hace nada" in nothing["reason"]
    assert seen["fx"]["preset"] == "rayo" and seen["ctx"]["name"] == "Prueba" and quiet is True
    assert off["data"]["defaults"] is False and cleared["data"]["powers"][0]["binding"] is None
    assert any("Puso un efecto" in e["action"] for e in history) and any("Quitó el efecto" in e["action"] for e in history)
