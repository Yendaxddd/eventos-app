"""Mini enemies: the bestiary, spawning, the players' hits, the enemies' attacks through the Activity's QTEs, and the rewards."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eventos_app.activity.mobs as mobs_mod  # noqa: E402
from eventos_app.activity.hub import RpcError  # noqa: E402
from eventos_app.activity.mobs import Bestiary, clean_template  # noqa: E402
from test_activity_play import Rig, frame, run  # noqa: E402

ANA = NS(id=111, display_name="Ana", name="ana")


def test_a_template_is_cleaned_and_the_bestiary_keeps_it(tmp_path):
    with pytest.raises(RpcError):
        clean_template({"name": "Rata", "every": 3})                       # attacks every 3 s: too often
    with pytest.raises(RpcError):
        clean_template({"name": "Rata", "image": "http://inseguro.example/a.png"})
    with pytest.raises(RpcError):
        clean_template({"name": "   "})
    t = clean_template({"name": "  Rata   gigante ", "hp": "50", "attack": "nope", "color": "red"})
    assert t["name"] == "Rata gigante" and t["hp"] == 50 and t["attack"] == "random" and t["color"] == "#fb7185" and t["damage"] is None
    path = tmp_path / "mobs.json"
    book = Bestiary(path)
    saved = book.put({"name": "Rata", "hp": 40, "damage": 6, "attack": "mash"})
    again = book.put({"id": saved["id"], "name": "Rata feroz", "hp": 60})
    assert again["id"] == saved["id"] and len(book.items) == 1
    reread = Bestiary(path)
    assert reread.items[saved["id"]]["name"] == "Rata feroz" and reread.items[saved["id"]]["hp"] == 60
    reread.delete(saved["id"])
    assert Bestiary(path).items == {}


def _app_bits(rig):
    rig.app.power_charges = {}
    rig.app.apply_damage_buff = lambda uid, dmg: dmg * 2           # a +100 % boost
    rig.app.qte_players = [ANA]
    events = []
    rig.bridge.on_event = lambda event, data=None: events.append(event)
    return events


def test_players_hit_enemies_with_their_boost_a_cooldown_and_the_last_hit_gives_charge(monkeypatch):
    async def scenario():
        async with Rig() as rig:
            events = _app_bits(rig)
            ws, welcome = await rig.login()
            t = rig.bridge.mobs.bestiary.put({"name": "Rata", "hp": 30, "every": 600, "charge": 25})
            await rig.bridge.mobs.spawn(t["id"], 2)
            listed = await frame(ws, "mobs")
            first, second = listed["list"]
            await ws.send_json({"t": "rpc", "id": 1, "op": "mob.attack", "args": {"id": first["id"]}})
            hit = await frame(ws, "rpc_ok")
            await ws.send_json({"t": "rpc", "id": 2, "op": "mob.attack", "args": {"id": first["id"]}})
            too_soon = await frame(ws, "rpc_err")
            rig.bridge.mobs.last_hit.clear()
            await ws.send_json({"t": "rpc", "id": 3, "op": "mob.attack", "args": {"id": first["id"]}})
            got = {}
            while len(got) < 2:                                                   # the notice may come before the answer
                f = await frame(ws)
                if f["t"] in ("rpc_ok", "notice"):
                    got[f["t"]] = f
            finishing, notice = got["rpc_ok"], got["notice"]
            await rig.bridge.mobs.set_hp(second["id"], "kill")
            return welcome, listed, hit, too_soon, finishing, notice, rig.app.power_charges, events, dict(rig.bridge.mobs.live)

    welcome, listed, hit, too_soon, finishing, notice, charges, events, live = run(scenario())
    assert welcome["mobs"] == {"paused": False, "list": []}
    assert [m["name"] for m in listed["list"]] == ["Rata 1", "Rata 2"] and listed["list"][0]["hp"] == 30
    assert hit["data"]["dealt"] == 20 and hit["data"]["hp"] == 10 and not hit["data"]["down"]
    assert "Espera" in too_soon["reason"]
    assert finishing["data"]["dealt"] == 10 and finishing["data"]["down"] is True       # only what was left
    assert notice["kind"] == "mob_down" and notice["data"]["charge"] == 25
    assert charges[111] == {"power1": 25, "power2": 25}
    assert events.count("mob_down") == 2 and events[-1] == "mobs_cleared" and "mob_spawn" in events and live == {}


def test_an_enemy_attacks_somebody_in_the_activity_and_a_good_answer_hits_it_back(monkeypatch):
    monkeypatch.setattr(mobs_mod, "TICK", 0.05)

    async def scenario():
        async with Rig() as rig:
            events = _app_bits(rig)
            hurt = []

            async def damage(uid, amount):
                hurt.append((uid, amount))

            async def update(*a):
                pass

            rig.app.damage_player, rig.app.update_player_stats = damage, update
            ws, _ = await rig.login()
            t = rig.bridge.mobs.bestiary.put({"name": "Lobo", "hp": 100, "every": 4, "attack": "flick", "damage": 9, "difficulty": "easy"})
            mob, = await rig.bridge.mobs.spawn(t["id"])
            mob["next"] = 0                                                    # attack now
            shown = await frame(ws, "qte", timeout=3)
            await ws.send_json({"t": "press", "id": shown["q"]["id"], "command": "gesture", "dt": 400, "data": {"dir": shown["q"]["arena"]["dir"]}})
            await frame(ws, "qte_result")
            hit = await frame(ws, "mob_hit")
            second = rig.bridge.mobs.live[mob["id"]]
            second["next"] = 0
            shown2 = await frame(ws, "qte", timeout=3)
            await ws.send_json({"t": "press", "id": shown2["q"]["id"], "command": "gesture", "dt": 400, "data": {"dir": "nope"}})
            await frame(ws, "qte_result")
            await asyncio.sleep(0.1)
            return shown, hit, hurt, second["hp"], events

    shown, hit, hurt, hp, events = run(scenario())
    assert shown["q"]["mode"] == "flick" and shown["q"]["target"]["id"] == "111"
    assert hit["amount"] == 30 and hp == 70                     # the counter (15) with the boost (x2)
    assert hurt == [(111, 9)] and "mob_attack" in events


def test_paused_enemies_do_not_attack_and_the_limits_hold(monkeypatch):
    monkeypatch.setattr(mobs_mod, "TICK", 0.05)

    async def scenario():
        async with Rig() as rig:
            _app_bits(rig)
            ws, _ = await rig.login()
            t = rig.bridge.mobs.bestiary.put({"name": "Rata", "hp": 10, "every": 4})
            await rig.bridge.mobs.set_paused(True)
            made = await rig.bridge.mobs.spawn(t["id"], 6)
            for m in made:
                m["next"] = 0
            await asyncio.sleep(0.3)
            quiet = dict(rig.bridge.arena.live)
            await rig.bridge.mobs.spawn(t["id"], 6)
            try:
                await rig.bridge.mobs.spawn(t["id"], 1)
            except RpcError as exc:
                full = str(exc)
            await rig.bridge.mobs.remove("all")
            return quiet, full, dict(rig.bridge.mobs.live)

    quiet, full, live = run(scenario())
    assert quiet == {} and "hasta 12" in full and live == {}


def test_only_game_masters_manage_enemies():
    async def scenario():
        async with Rig() as rig:
            rig.app.is_admin = lambda m: False
            ws, _ = await rig.login()
            await ws.send_json({"t": "rpc", "id": 1, "op": "gm.mob_save", "args": {"mob": {"name": "Rata"}}})
            return await frame(ws, "rpc_err"), rig.bridge.mobs.bestiary.items

    refused, items = run(scenario())
    assert items == {} and refused["reason"]
