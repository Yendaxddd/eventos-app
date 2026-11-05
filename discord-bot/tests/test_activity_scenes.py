"""Scenes: which QTEs come up on their own in each kind of moment (a boss fight, a chase...), switched live by the game masters."""
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from eventos_app.activity.hub import RpcError  # noqa: E402
from eventos_app.activity.qte import describe  # noqa: E402
from eventos_app.activity.scenes import PRESETS, SceneBook, clean_scene, fallback_kind, parry_on, pick_kind, public  # noqa: E402
from eventos_app.activity.staff import OP_PERMS  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402
from test_activity_play import frame, run  # noqa: E402


def test_a_scene_is_cleaned_and_the_presets_make_sense():
    s = clean_scene({"name": "  Persecución  ", "color": "bad", "weights": {"evade": 300, "flick": "40", "nope": 9}, "counter": 0})
    assert s["name"] == "Persecución" and s["color"] == "#a78bfa" and s["weights"]["evade"] == 100 and s["weights"]["flick"] == 40
    assert "nope" not in s["weights"] and s["counter"] is False
    with pytest.raises(RpcError, match="al menos"):
        clean_scene({"name": "Nada", "weights": {}})
    with pytest.raises(RpcError, match="nombre"):
        clean_scene({"name": " ", "weights": {"evade": 1}})
    scenes = {p["id"]: clean_scene(p) for p in PRESETS}
    assert parry_on(scenes["boss"]) and scenes["boss"]["counter"]
    assert not parry_on(scenes["escape"]) and not scenes["escape"]["counter"]                 # a chase: no parry, no counter
    assert not parry_on(scenes["dodge"]) and fallback_kind(scenes["dodge"]) == "direction"
    assert fallback_kind(clean_scene({"name": "x", "weights": {"evade": 10, "mash": 10}})) == "evade"
    rng = random.Random(3)
    assert {pick_kind(scenes["escape"], rng) for _ in range(200)} == {"evade", "direction", "flick", "mash"}
    assert public(scenes["escape"]) == {"id": "escape", "name": "Huida", "color": "#22c55e", "note": scenes["escape"]["note"], "parry": False, "counter": False}


def test_the_book_keeps_scenes_and_the_active_one(tmp_path):
    book = SceneBook(tmp_path / "s.json")
    assert {s["id"] for s in book.state()["scenes"]} == {"boss", "combat", "escape", "dodge"} and book.current() is None
    mine = book.put({"name": "Sigilo", "weights": {"fake": 50, "evade": 50}, "counter": False})
    book.use(mine["id"])
    again = SceneBook(tmp_path / "s.json")
    assert again.current()["name"] == "Sigilo"
    again.delete(mine["id"])
    assert again.current() is None
    with pytest.raises(RpcError):
        again.use("ghost")
    (tmp_path / "s.json").write_text("{ broken", encoding="utf-8")
    assert len(SceneBook(tmp_path / "s.json").items) == 4                                      # a broken file: the presets


def test_a_qte_without_parry_shows_only_evade_and_no_black_flash():
    times = {"medium": {"evade_window": 4.5, "parry_window": (3.0, 5.0), "perfect_parry": 4.0}}
    target = NS(id=1, name="ana", display_name="Ana")
    normal = describe(1, {"mode": "single", "difficulty": "medium", "target": target}, times, 0, bf_window=0.2)
    chase = describe(2, {"mode": "single", "difficulty": "medium", "target": target, "no_parry": True}, times, 0, bf_window=0.2)
    assert "parry" in normal["commands"] and normal["windows"]["bf"]
    assert chase["commands"] == ["evade", "save", "adapt"] and chase["windows"] == {"evade": [0.0, 4.5], "bf": None}


def test_game_masters_switch_scenes_and_everybody_hears_it(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            rig.bridge.scenes = SceneBook(tmp_path / "scenes.json")
            rig.bridge.apply_scene()
            gm, _ = await rig.login(ME)
            player, welcome = await rig.login(OTHER)
            refused = await rig.ask(player, "gm.scene_use", id="escape")
            used = await rig.ask(gm, "gm.scene_use", id="escape")
            heard = await frame(player, "scene")
            in_bot = rig.app.qte_scene
            saved = await rig.ask(gm, "gm.scene_save", scene={**in_bot, "name": "Huida larga"})
            heard_again = await frame(player, "scene")
            none = await rig.ask(gm, "gm.scene_use", id="")
            late, welcome_after = await rig.login(OTHER)
            return welcome, refused, used, heard, in_bot, saved, heard_again, none, rig.app.qte_scene, rig.bridge.gm.log.recent()

    welcome, refused, used, heard, in_bot, saved, heard_again, none, after, history = run(scenario())
    assert welcome["scene"] is None and refused["t"] == "rpc_err"
    assert used["data"]["active"] == "escape" and heard["scene"]["name"] == "Huida" and heard["scene"]["parry"] is False
    assert in_bot["weights"]["flick"] == 25
    assert heard_again["scene"]["name"] == "Huida larga"                                      # editing the active one is heard too
    assert none["data"]["active"] == "" and after is None
    assert any("Escena: Huida" in e["action"] for e in history)


def test_a_gesture_from_a_scene_goes_to_the_activity_only_for_who_is_in_it(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            player, _ = await rig.login(OTHER)
            inside = await rig.bridge.launch_gesture("flick", "medium", NS(id=OTHER, display_name="Mina", name="mina"))
            got = await frame(player, "qte")
            outside = await rig.bridge.launch_gesture("flick", "medium", NS(id=999, display_name="Otro", name="otro"))
            wrong = await rig.bridge.launch_gesture("standard", "medium", NS(id=OTHER, display_name="Mina", name="mina"))
            return inside, got, outside, wrong

    inside, got, outside, wrong = run(scenario())
    assert inside is True and got["q"]["mode"] == "flick" and outside is False and wrong is False


def test_the_bot_draws_from_the_scene_and_honours_parry_and_counter(tmp_path, monkeypatch):
    from eventos_app import paths
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module
    bot = object.__new__(module.AdvancedQTEBot)
    bot.qte_scene = None
    assert bot.scene_parry_ok() and bot.scene_counter_ok()
    bot.qte_scene = clean_scene(PRESETS[2])                                                   # Huida
    assert not bot.scene_parry_ok() and not bot.scene_counter_ok()
    random.seed(1)
    assert {bot.pick_scene_kind(bot.qte_scene) for _ in range(200)} == {"evade", "direction", "flick", "mash"}
    assert bot.scene_fallback_kind(bot.qte_scene) == "direction"
    src = Path(module.__file__).read_text(encoding="utf-8")
    assert "if qte_data.get('no_parry'):" in src and src.count("self.scene_counter_ok() and (") == 2


def test_scene_ops_need_the_event_box():
    for op in ("gm.scenes", "gm.scene_save", "gm.scene_delete", "gm.scene_use", "gm.scene_presets"):
        assert OP_PERMS[op] == "event"
