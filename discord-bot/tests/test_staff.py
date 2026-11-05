"""The game-master team: boxes per person and per role, presets, hosts, and cinematics that stay a surprise for the rest of the team."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity.staff import ALL_BUT_STAFF, OP_PERMS, PERM_IDS, PRESETS, StaffBook  # noqa: E402
from test_activity_gm_socket import GmRig, handlers  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402

SECRET = {"name": "La traición", "steps": [{"type": "text", "at": 0, "text": "El traidor era Kuro desde el principio", "duration": 3}]}


def run(coro):
    return asyncio.run(coro)


def test_every_panel_request_needs_a_known_box():
    boxes = set(PERM_IDS)
    assert set(OP_PERMS.values()) <= boxes
    shown = set(handlers())
    unmapped = sorted(op for op in shown if op not in OP_PERMS and op not in ("gm.state", "gm.quick", "gm.cinemas", "gm.cinema_link"))
    assert unmapped == [], unmapped


def test_resolving_boxes_person_beats_roles_and_admin_role_has_a_default(tmp_path):
    book = StaffBook(tmp_path / "staff.json")
    assert book.resolve(5, [], True, False) == (list(ALL_BUT_STAFF), False)
    assert book.resolve(5, [], False, False) == ([], False)
    assert book.resolve(5, [], False, True) == (list(PERM_IDS), True)
    book.set_entry("role", 77, "Narradores", PRESETS["narrator"][2])
    assert set(book.resolve(6, [77], False, False)[0]) == set(PRESETS["narrator"][2])
    book.set_entry("person", 5, "Ana", ["history"])
    assert book.resolve(5, [77], True, False) == (["history"], False)          # an entry of their own limits even an admin
    book.set_entry("host", 9, "Leo", [])
    again = StaffBook(tmp_path / "staff.json")                                 # kept on disk
    assert again.resolve(9, [], False, False)[1] is True and again.resolve(5, [], True, False)[0] == ["history"]


def test_a_box_decides_each_request_and_the_team_hears_changes_at_once():
    async def scenario():
        async with GmRig() as rig:
            ws, welcome = await rig.login(ME)                            # Ana: admin role, so every box but «staff»
            no_staff = await rig.ask(ws, "gm.staff")
            rig.bridge.staff.set_entry("host", ME, "Ana", [])
            ok_staff = await rig.ask(ws, "gm.staff")
            rig.admins.add(OTHER)
            give = await rig.ask(ws, "gm.staff_set", kind="person", id=str(OTHER), name="Mina", perms=list(PRESETS["narrator"][2]))
            ws2, mina = await rig.login(OTHER)
            launch = await rig.ask(ws2, "gm.launch", mode="group", difficulty="easy")
            cinemas = await rig.ask(ws2, "gm.cinemas")
            self_raise = await rig.ask(ws2, "gm.staff_set", kind="person", id=str(OTHER), name="Mina", perms=["event"])
            return welcome, no_staff, ok_staff, give, mina, launch, cinemas, self_raise

    welcome, no_staff, ok_staff, give, mina, launch, cinemas, self_raise = run(scenario())
    assert welcome["perms"]["gm"] is True and "staff" not in welcome["perms"]["can"] and welcome["perms"]["host"] is False
    assert no_staff["t"] == "rpc_err" and "Equipo de GM" in no_staff["reason"]
    assert ok_staff["t"] == "rpc_ok" and any(p["id"] == "narrator" for p in ok_staff["data"]["presets"])
    assert give["t"] == "rpc_ok" and give["data"]["people"][0]["preset"] == "narrator"
    assert set(mina["perms"]["can"]) == set(PRESETS["narrator"][2])
    assert launch["t"] == "rpc_err" and "Evento y QTE" in launch["reason"]
    assert cinemas["t"] == "rpc_ok"
    assert self_raise["t"] == "rpc_err"


def test_a_cinematic_is_sealed_for_the_rest_of_the_team_until_its_author_shares_it():
    async def scenario():
        async with GmRig() as rig:
            rig.admins.add(OTHER)
            ws_mina, _ = await rig.login(OTHER)
            saved = await rig.ask(ws_mina, "gm.cinema_save", cinema=SECRET)
            cid = saved["data"]["saved"]["id"]
            ws_ana, _ = await rig.login(ME)
            seen = await rig.ask(ws_ana, "gm.cinemas")
            quick = await rig.ask(ws_ana, "gm.quick")
            history = await rig.ask(ws_ana, "gm.history")
            overwrite = await rig.ask(ws_ana, "gm.cinema_save", cinema={**SECRET, "id": cid, "name": "mío"})
            copy = await rig.ask(ws_ana, "gm.cinema_duplicate", id=cid)
            delete = await rig.ask(ws_ana, "gm.cinema_delete", id=cid)
            play = await rig.ask(ws_ana, "gm.cinema_play", id=cid)
            await rig.ask(ws_ana, "gm.cinema_stop")
            shared = await rig.ask(ws_mina, "gm.cinema_save", cinema={**saved["data"]["saved"], "share": "team", "hint": "Final cap. 2"})
            seen_after = await rig.ask(ws_ana, "gm.cinemas")
            return cid, seen, quick, history, overwrite, copy, delete, play, shared, seen_after

    cid, seen, quick, history, overwrite, copy, delete, play, shared, seen_after = run(scenario())
    card = next(c for c in seen["data"]["cinemas"] if c["id"] == cid)
    dump = json.dumps([seen["data"], quick["data"], history["data"]], ensure_ascii=False)
    assert card["sealed"] is True and card["steps"] == [] and card["owner"]["name"] == "Mina"
    assert "traición" not in dump and "Kuro" not in dump                 # neither the words nor the name reach another GM
    assert overwrite["t"] == "rpc_err" and copy["t"] == "rpc_err" and delete["t"] == "rpc_err"
    assert play["t"] == "rpc_ok"                                          # still playable by whoever runs the show
    assert shared["t"] == "rpc_ok"
    opened = next(c for c in seen_after["data"]["cinemas"] if c["id"] == cid)
    assert not opened.get("sealed") and opened["steps"][0]["text"].startswith("El traidor")
