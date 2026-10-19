"""Each player's settings and latency adjustment, and what the server tells a client when it comes in."""
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import LatencyBook, PrefsStore  # noqa: E402
from eventos_app.activity.latency import CAP_MS, compensation, sanitize as sanitize_latency  # noqa: E402
from eventos_app.activity.prefs import DEFAULTS, sanitize  # noqa: E402
from eventos_app.activity.qte import describe  # noqa: E402
from test_activity_play import Rig, frame, run  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "activity_client" / "test" / "prefs-cases.json"


# ---- settings -----------------------------------------------------------------------------------------------------------
def test_settings_are_cleaned_field_by_field():
    assert sanitize(None) == DEFAULTS and sanitize("x") == DEFAULTS and sanitize([]) == DEFAULTS
    out = sanitize({"theme": "oled", "textScale": 500, "buttonScale": "90", "volume": -5, "buttonPlacement": "up", "sound": 0,
                    "nonsense": 1, "density": "spacious", "messageLimit": 75.6, "keepEvade": "yes"})
    assert out["theme"] == "oled" and out["density"] == "spacious"
    assert out["textScale"] == 140 and out["volume"] == 0                  # out of range: pulled into it
    assert out["buttonScale"] == 100                                       # text is not a number: the default (this is the server's rule; the client sends numbers)
    assert out["buttonPlacement"] == "random"                              # not one of the choices: the default
    assert out["sound"] is False and out["keepEvade"] is True              # truthy / falsy
    assert out["messageLimit"] == 76 and "nonsense" not in out
    assert sanitize({"textScale": True})["textScale"] == 100               # a boolean is not a number
    assert sanitize({"textScale": float("nan")})["textScale"] == 100


def test_the_server_and_the_client_clean_settings_the_same_way():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert len(cases) >= 8
    for case in cases:
        assert sanitize(case["raw"]) == case["expected"], case["raw"]


def test_each_player_keeps_their_own_settings_and_testers_are_not_written_to_disk(tmp_path):
    path = tmp_path / "prefs.json"
    store = PrefsStore(path)
    assert store.get(5) == DEFAULTS and not store.has(5)
    saved = store.set(5, {"theme": "contrast", "textScale": 120})
    assert saved["theme"] == "contrast" and store.has(5) and store.get(6) == DEFAULTS
    store.set(-1234, {"theme": "oled"})                                      # somebody testing from this PC
    again = PrefsStore(path)
    assert again.get(5)["textScale"] == 120 and not again.has(-1234)
    assert json.loads(path.read_text(encoding="utf-8")).keys() == {"5"}
    path.write_text("{ not json", encoding="utf-8")
    assert PrefsStore(path).get(5) == DEFAULTS                                 # a damaged file does not stop the app


# ---- latency ----------------------------------------------------------------------------------------------------------------
def test_a_latency_test_result_is_forced_into_believable_numbers():
    clean = sanitize_latency({"median": 80, "min": 40, "p90": 120, "jitter": 9, "loss": 0.1, "device": 400, "spread": 20, "taps": 8, "x": 1})
    assert clean["device"] == 150 and clean["median"] == 80 and clean["loss"] == 0.1 and clean["taps"] == 8 and "x" not in clean
    assert sanitize_latency({"median": -5, "loss": 7, "device": None})["loss"] == 1.0
    assert sanitize_latency({"median": "fast", "device": "slow"}) is None and sanitize_latency("x") is None and sanitize_latency({}) is None
    assert sanitize_latency({"median": 50, "device": None})["device"] is None


def test_the_adjustment_is_network_added_and_device_taken_off_with_limits(tmp_path):
    assert compensation(40, 60) == {"net": 40.0, "device": 60.0, "cap": CAP_MS}
    assert compensation(9000, 9000)["net"] == 400.0 and compensation(9000, 9000)["device"] == 150.0
    assert compensation(-5, -5) == {"net": 0.0, "device": 0.0, "cap": CAP_MS}
    book = LatencyBook(tmp_path / "latency.json")
    assert book.device_ms(7) == 0.0 and book.get(7) is None
    book.set(7, {"median": 60, "device": 45})
    book.set(-9, {"median": 60, "device": 99})
    assert LatencyBook(tmp_path / "latency.json").device_ms(7) == 45.0 and LatencyBook(tmp_path / "latency.json").get(-9) is None
    assert book.set(7, {"median": "?"}) is None and book.device_ms(7) == 45.0         # a bad result keeps the old one
    book.clear(7)
    assert book.device_ms(7) == 0.0


def test_a_test_that_skipped_the_tap_step_keeps_the_earlier_device_measurement(tmp_path):
    book = LatencyBook(tmp_path / "latency.json")
    book.set(7, {"median": 60, "device": 45, "spread": 12, "taps": 8})
    kept = book.set(7, {"median": 80, "min": 40, "device": None, "spread": None, "taps": 0})
    assert kept["median"] == 80 and kept["device"] == 45 and kept["taps"] == 8                 # the network part is new, the device part stays
    assert LatencyBook(tmp_path / "latency.json").device_ms(7) == 45.0
    book.clear(8)
    assert book.set(8, {"median": 80, "device": None})["device"] is None                       # nothing to keep for somebody new
    assert book.device_ms(8) == 0.0


# ---- what the server says when somebody comes in -----------------------------------------------------------------------
def test_a_new_player_is_welcomed_with_rules_adjustment_and_no_settings_and_a_game_master_is_told_so():
    async def scenario():
        async with Rig() as rig:
            rig.app.qte_timeout_durations = {"easy": 6.75}
            rig.app.bf_timing_window = 0.2
            rig.app.is_admin = lambda member: member.id == 111
            members = {111: NS(id=111, display_name="Ana", display_avatar=NS(url="https://cdn/ana.png")),
                       222: NS(id=222, display_name="Luis", display_avatar=NS(url="https://cdn/luis.png"))}
            rig.app.resolve_event_guild = lambda: NS(get_member=lambda uid: members.get(uid))
            ws, welcome = await rig.login()
            gm_welcome = welcome
            ws2, other = await rig.login(222)
            await ws.close()
            await ws2.close()
            return gm_welcome, other

    gm, other = run(scenario())
    assert gm["perms"] == {"gm": True} and other["perms"] == {"gm": False}
    assert gm["prefs"] is None                                                      # the server knows nothing about them yet: the client sends its own
    assert gm["comp"] == {"net": 0.0, "device": 0.0, "cap": CAP_MS} and gm["calib"] is None
    assert gm["rules"]["times"]["easy"] == {"evade": 6.0, "parry": [4.0, 7.0], "perfect": None, "timeout": 6.75}
    assert gm["rules"]["bfWindow"] == 0.2 and gm["rules"]["counterWindow"] == 5.0 and gm["charAvatars"] == {}
    assert gm["version"] and gm["serverTime"] > 0


def test_settings_sent_by_a_client_are_cleaned_kept_and_given_back_on_the_next_visit(tmp_path):
    async def scenario():
        async with Rig() as rig:
            rig.bridge.prefs = PrefsStore(tmp_path / "prefs.json")
            ws, _ = await rig.login()
            await ws.send_json({"t": "prefs", "prefs": {"theme": "oled", "textScale": 9999, "buttonPlacement": "bottom", "evil": "<script>"}})
            await asyncio.sleep(0.2)
            await ws.close()
            ws2, welcome = await rig.login()
            await ws2.send_json({"t": "prefs", "prefs": "garbage"})
            await asyncio.sleep(0.1)
            await ws2.close()
            return welcome, rig.bridge.prefs.get(111)

    welcome, after_garbage = run(scenario())
    assert welcome["prefs"]["theme"] == "oled" and welcome["prefs"]["textScale"] == 140 and welcome["prefs"]["buttonPlacement"] == "bottom"
    assert "evil" not in welcome["prefs"]
    assert after_garbage == DEFAULTS                                                 # garbage resets to the defaults, it never breaks anything


def test_the_latency_test_is_saved_answered_with_the_new_adjustment_and_used_on_the_next_press(tmp_path):
    async def scenario():
        async with Rig() as rig:
            rig.bridge.latency = LatencyBook(tmp_path / "latency.json")
            ws, _ = await rig.login()
            await ws.send_json({"t": "sync", "rtt": 80.0, "offset": 0.0})                 # the client's own figure: 80 ms round trip
            await asyncio.sleep(0.1)
            await ws.send_json({"t": "latency", "result": {"median": 80, "min": 70, "p90": 95, "jitter": 6, "loss": 0, "device": 60, "taps": 6, "spread": 14}})
            calib, comp = await frame(ws, "calib"), await frame(ws, "comp")
            rig.start_qte(7)
            await frame(ws, "qte")
            rig.hub.qtes["7"]["tGo"] -= 5000                                               # it has been running for 5 s
            await ws.send_json({"t": "press", "id": "7", "command": "evade", "dt": 1000})
            await frame(ws, "qte_result")
            return calib, comp, rig.calls

    calib, comp, calls = run(scenario())
    assert calib["calib"]["device"] == 60 and calib["calib"]["median"] == 80
    assert comp["comp"] == {"net": 40.0, "device": 60.0, "cap": CAP_MS}                    # half the round trip added, the device lag taken off
    assert abs(calls[-1][1] - 0.98) < 1e-9                                                  # 1000 ms + 40 - 60


def test_the_server_measures_round_trips_itself_and_tells_the_player_when_their_adjustment_moves(monkeypatch):
    import eventos_app.activity.hub as hub_module
    monkeypatch.setattr(hub_module, "PING_EVERY", 0.05)

    async def scenario():
        async with Rig() as rig:
            ws, welcome = await rig.login()
            comp, answered = None, 0

            async def play():
                nonlocal comp, answered
                while comp is None:
                    got = await ws.receive_json()
                    if got["t"] == "sp":
                        await asyncio.sleep(0.04)                                           # a 40 ms round trip, give or take
                        await ws.send_json({"t": "sq", "n": got["n"]})
                        answered += 1
                    elif got["t"] == "comp":
                        comp = got

            await asyncio.wait_for(play(), 5)
            conn = next(iter(rig.hub.conns.values()))
            stats = rig.hub.stats()[0]
            seen = {"rtts": len(conn.rtts), "net_ms": conn.net_ms}          # read now: the answers still on their way keep moving the live numbers
            await ws.close()
            return comp, seen, stats

    comp, seen, stats = run(scenario())
    assert seen["rtts"] >= 3 and 30 <= seen["net_ms"] * 2 <= 120
    assert comp["comp"]["net"] >= 3 and stats["net_ms"] == round(seen["net_ms"], 1)
    assert stats["jitter_ms"] is not None


def test_requests_for_data_get_an_answer_or_a_reason():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            answers = []
            for call in ({"id": "a", "op": "ping", "args": {}}, {"id": "b", "op": "nothing", "args": {}}, {"id": "c", "op": "../ping", "args": {}},
                         {"id": "d", "op": "ping; import os", "args": {}}, {"id": "e", "op": "ping", "args": "x"}, {"id": "f", "op": "", "args": {}},
                         {"id": "g", "op": "welcome_extras", "args": {}}):
                await ws.send_json({"t": "rpc", **call})
                answers.append(await frame(ws))
            await ws.close()
            return answers

    answers = run(scenario())
    assert answers[0]["t"] == "rpc_ok" and answers[0]["data"]["pong"] is True and answers[0]["id"] == "a"
    for bad in answers[1:]:
        assert bad["t"] == "rpc_err" and bad["reason"], bad                       # an unknown name, a path, code, a bad argument: all refused


def test_a_qte_frame_says_what_time_it_is_for_the_server_so_a_late_client_can_catch_up():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            rig.start_qte(3)
            got = await frame(ws, "qte")
            await ws.close()
            return got

    got = run(scenario())
    assert abs(got["now"] - time.time() * 1000) < 2000 and got["q"]["tGo"] <= got["now"]


def test_group_and_direction_qtes_are_described_with_the_windows_the_bot_judges():
    times = {"medium": {"evade_window": 4.5, "parry_window": (3.0, 5.0), "perfect_parry": 4.0}}
    target = NS(id=5, display_name="Ana", name="ana")
    group = describe(1, {"difficulty": "medium", "mode": "group", "participants": {5: {}, 6: {}}}, times, 0.0, bf_window=0.2)
    assert group["commands"] == ["evade"] and group["windows"] == {"evade": [0.0, 4.5], "bf": None}      # the bot refuses a parry in a group QTE
    assert group["participants"] == ["5", "6"] and group["target"] is None
    fast = {"impossible": {"evade_window": 1.5, "parry_window": (0.8, 1.7)}}
    arrows = describe(2, {"difficulty": "impossible", "mode": "direction", "target": target, "shown_arrow": "⬅️"}, fast, 0.0)
    assert arrows["windows"]["evade"] == [0.0, 2.5] and arrows["timeout"] == 4.0                          # "too slow" after the evade window + 1 s, gives up at 4 s
    combo = describe(3, {"difficulty": "medium", "mode": "combo", "target": target, "combo_sequence": ["evade"] * 5, "combo_index": 2, "combo_length": 5}, times, 0.0)
    assert combo["combo"]["limits"] == [5.0, 10.0, 15.0, 20.0, 25.0] and combo["combo"]["index"] == 2
    fake = describe(4, {"difficulty": "medium", "mode": "fake", "target": target}, times, 0.0)
    assert fake["target"] is None and fake["commands"] == [] and fake["timeout"] == 3.0
