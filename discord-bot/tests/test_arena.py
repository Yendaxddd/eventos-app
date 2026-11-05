"""The Activity's own QTEs (swipe, drag, tap) and fake QTEs answered from the Activity: judged by the server, felt through the bot."""
import asyncio
import random
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity.arena import MASH_COUNT, TIMEOUT, judge, params_for  # noqa: E402
from test_activity_play import Rig, frame, run  # noqa: E402

ANA = NS(id=111, display_name="Ana", name="ana")


def test_each_gesture_is_judged_by_what_it_asked_for_and_by_the_clock():
    flick = params_for("flick", "hard", random.Random(1))
    assert judge("flick", flick, {"dir": flick["dir"]}, 0.5, 1.4) == (True, "")
    assert judge("flick", flick, {"dir": "nope"}, 0.5, 1.4)[0] is False
    assert judge("flick", flick, {"dir": flick["dir"]}, 2.0, 1.4) == (False, "late")
    drag = params_for("drag", "medium", random.Random(2))
    gx, gy = drag["to"]
    assert judge("drag", drag, {"x": gx + 0.05, "y": gy}, 1, 3)[0] is True
    assert judge("drag", drag, {"x": gx + 0.3, "y": gy}, 1, 3) == (False, "missed")
    assert judge("drag", drag, {"x": "inf", "y": 0}, 1, 3)[0] is False and judge("drag", drag, None, 1, 3)[0] is False
    mash = params_for("mash", "medium")
    need = MASH_COUNT["medium"]
    assert judge("mash", mash, {"count": need}, 2.0, 3.2)[0] is True
    assert judge("mash", mash, {"count": need - 1}, 2.0, 3.2) == (False, "short")
    assert judge("mash", mash, {"count": need}, 0.2, 3.2)[0] is False                         # 60 taps a second: a script, not a person
    for mode in ("flick", "drag"):
        assert TIMEOUT[mode]["easy"] > TIMEOUT[mode]["impossible"]


class Hurt:
    def __init__(self):
        self.calls, self.stats = [], []

    async def damage(self, uid, difficulty):
        self.calls.append((uid, difficulty))

    async def update(self, uid, kind, ok, seconds):
        self.stats.append((uid, kind, ok))


def rig_with_hurt(rig):
    hurt = Hurt()
    rig.app.damage_player, rig.app.update_player_stats = hurt.damage, hurt.update
    events = []
    rig.bridge.on_event = lambda event, data=None: events.append((event, (data or {}).get("user")))
    return hurt, events


def test_a_right_answer_counts_as_an_evade_a_wrong_one_hurts_and_nobody_else_may_answer():
    async def scenario():
        async with Rig() as rig:
            hurt, events = rig_with_hurt(rig)
            ws, _ = await rig.login()
            somebody_elses, = await rig.bridge.arena.launch("flick", "easy", [NS(id=333, display_name="Otro", name="otro")])
            await frame(ws, "qte")
            await ws.send_json({"t": "press", "id": somebody_elses["id"], "command": "gesture", "dt": 400, "data": {"dir": "up"}})
            refused = await frame(ws, "error")
            ok_frame, = await rig.bridge.arena.launch("flick", "easy", [ANA])
            shown = await frame(ws, "qte")
            await ws.send_json({"t": "press", "id": ok_frame["id"], "command": "gesture", "dt": 400, "data": {"dir": ok_frame["arena"]["dir"]}})
            good = await frame(ws, "qte_result")
            ended = await frame(ws, "qte_end")
            bad_frame, = await rig.bridge.arena.launch("mash", "easy", [ANA])
            await ws.send_json({"t": "press", "id": bad_frame["id"], "command": "gesture", "dt": 900, "data": {"count": 2}})
            bad = await frame(ws, "qte_result")
            again = None
            await ws.send_json({"t": "press", "id": bad_frame["id"], "command": "gesture", "dt": 950, "data": {"count": 20}})
            again = await frame(ws, "error")
            return shown, refused, good, ended, bad, again, hurt, events

    shown, refused, good, ended, bad, again, hurt, events = run(scenario())
    assert shown["q"]["mode"] == "flick" and shown["q"]["target"]["id"] == "111" and shown["q"]["commands"] == ["gesture"]
    assert "no es tuyo" in refused["reason"]
    assert good["ok"] is True and good["ms"] > 0 and ended["id"] == shown["q"]["id"]
    assert bad["ok"] is False and bad["why"] == "short" and "terminó" in again["reason"]              # one answer per QTE
    assert hurt.calls == [(111, "easy")] and (111, "evade", True) in hurt.stats and (111, "evade", False) in hurt.stats
    assert ("evade_ok", 111) in events and ("qte_fail", 111) in events


def test_no_answer_in_time_is_a_failure_and_hurts():
    async def scenario():
        async with Rig() as rig:
            hurt, _ = rig_with_hurt(rig)
            ws, _ = await rig.login()
            import eventos_app.activity.arena as arena
            old = dict(arena.TIMEOUT["drag"])
            arena.TIMEOUT["drag"]["impossible"] = 0.2
            try:
                await rig.bridge.arena.launch("drag", "impossible", [ANA], damage=7)
                result = await frame(ws, "qte_result", timeout=3)
            finally:
                arena.TIMEOUT["drag"].update(old)
            return result, hurt.calls, dict(rig.bridge.arena.live)

    result, calls, live = run(scenario())
    assert result["ok"] is False and result["why"] == "timeout" and calls == [(111, 7)] and live == {}


def test_the_panel_launches_a_gesture_qte_only_for_somebody_with_the_activity_open():
    async def scenario():
        async with Rig() as rig:
            rig.bridge.gm.stunned_left = lambda: 0.0
            rig.app.qte_players = [ANA, NS(id=333, display_name="Lejos", name="lejos")]
            ws, _ = await rig.login()
            random.seed(3)
            out = await rig.bridge.arena.gm_launch("GM", "mash", "medium")
            shown = await frame(ws, "qte")
            try:
                await rig.bridge.arena.gm_launch("GM", "mash", "medium", target_id=333)
            except Exception as exc:  # noqa: BLE001
                refused = str(exc)
            return out, shown, refused

    out, shown, refused = run(scenario())
    assert out == {"ok": True} and shown["q"]["target"]["id"] == "111" and "no tiene la Actividad abierta" in refused


def test_answering_a_fake_qte_from_the_activity_is_falling_for_it():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            rig.app.active_qtes[5] = {"difficulty": "easy", "mode": "fake", "target": ANA, "participants": {}, "responses": set(), "message": None}
            shown = await frame(ws, "qte")
            await ws.send_json({"t": "press", "id": "5", "command": "evade", "dt": 500})
            result = await frame(ws, "qte_result")
            return shown, result

    shown, result = run(scenario())
    assert shown["q"]["mode"] == "fake" and shown["q"]["target"]["id"] == "111" and shown["q"]["commands"] == ["evade", "parry"]
    assert result["ok"] is False
