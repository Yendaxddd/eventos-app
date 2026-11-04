"""Players' cinematics for their own powers: the model, the director playing them, and the request → review → approve flow."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eventos_app.activity import Hub  # noqa: E402
from eventos_app.activity.cinema import CinemaBook, CinemaDirector, clean_request, request_matches  # noqa: E402
from eventos_app.activity.cinema_requests import MAX_REQUEST_SECONDS, bind_label  # noqa: E402
from eventos_app.activity.staff import OP_PERMS  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402
from test_activity_play import frame, run  # noqa: E402
from test_audio import conn_of  # noqa: E402


def request(**bind):
    return {"name": "Kokusen", "kind": "request", "status": "approved",
            "bind": {"event": "power_used", "user": "222", "character": "Kuro", "slot": "2", "cooldown": 300, **bind},
            "steps": [{"type": "title", "at": 0, "text": "¡Kokusen!", "duration": 2}]}


def test_a_request_is_cleaned_and_matches_only_its_player_character_and_power():
    assert clean_request({"name": "x"}) == {"kind": "gm"}
    odd = clean_request({"kind": "request", "status": "hacked", "bind": {"event": "rm -rf", "slot": "9", "cooldown": "nope"}})
    assert odd["status"] == "draft" and odd["bind"]["event"] == "power_used" and odd["bind"]["slot"] == "" and odd["bind"]["cooldown"] == 300
    assert clean_request({"kind": "request", "bind": {"cooldown": 99999}})["bind"]["cooldown"] == 3600
    c = {**request(), **clean_request(request())}
    hit = {"user": 222, "character": "kuro", "slot": "2"}
    assert request_matches(c, "power_used", hit)
    assert not request_matches(c, "power_used", {**hit, "user": 111})              # somebody else's power
    assert not request_matches(c, "power_used", {**hit, "slot": "1"})              # the other power
    assert not request_matches(c, "power_used", {**hit, "character": "Mei"})       # another of their characters
    assert not request_matches(c, "black_flash", hit)
    assert not request_matches({**c, "status": "pending"}, "power_used", hit)       # not approved yet
    assert bind_label(c["bind"]) == "Cuando Kuro usa el Poder 2"
    assert bind_label({"event": "black_flash", "character": "Kuro"}) == "Cuando hago un Black Flash (como Kuro)"


def test_an_approved_request_plays_when_its_player_does_that_then_waits_its_cooldown(tmp_path):
    async def scenario():
        hub = Hub()
        book = CinemaBook(None, None)
        director = CinemaDirector(hub, book)
        conn_of(hub, 1)
        mine = book.put(request(cooldown=60))
        gm = book.put({"name": "Para todos", "triggers": ["power_used"], "steps": [{"type": "title", "at": 0, "text": "Poder", "duration": 1}]})
        out = {"mine": await director.on_event("power_used", {"user": 222, "character": "Kuro", "slot": "2"}), "first": director.run["id"]}
        await director.stop()
        out["again"] = await director.on_event("power_used", {"user": 222, "character": "Kuro", "slot": "2"})
        out["second"] = director.run["id"]                                            # the cooldown: the game masters' one plays
        return out, mine["id"], gm["id"]

    out, mine, gm = run(scenario())
    assert out == {"mine": True, "first": mine, "again": True, "second": gm}


def test_players_request_game_masters_review_and_nobody_else_sees_it_before(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            rig.bridge.cinema.book.path = tmp_path / "cinematics.json"
            rig.bridge.characters_of = lambda uid: ["Kuro"] if uid == OTHER else []
            gm, _ = await rig.login(ME)
            player, _ = await rig.login(OTHER)
            state = await rig.ask(player, "creq.state")
            raw = request(character="Kuro")
            del raw["status"]
            not_mine = await rig.ask(player, "creq.save", cinema={**raw, "bind": {**raw["bind"], "character": "Mei"}})
            sound = await rig.ask(player, "creq.save", cinema={**raw, "steps": raw["steps"] + [{"type": "audio", "at": 0, "mode": "play", "sound": "x"}]})
            too_long = await rig.ask(player, "creq.save", cinema={**raw, "steps": [{"type": "title", "at": 0, "text": "x", "duration": 30}]})
            saved = await rig.ask(player, "creq.save", cinema=raw)
            cid = saved["data"]["saved"]["id"]
            hidden = await rig.ask(gm, "gm.cinemas")                                   # not in the game masters' own list
            queue_before = await rig.ask(gm, "gm.requests")                            # drafts are the player's own business
            refused = await rig.ask(player, "gm.requests")
            sent = await rig.ask(player, "creq.send", id=cid)
            told = await frame(gm, "toast")
            queue = await rig.ask(gm, "gm.requests")
            approved = await rig.ask(gm, "gm.request_decide", id=cid, status="approved", review="¡Brutal!")
            news = await frame(player, "toast")
            fires = await rig.bridge.cinema.on_event("power_used", {"user": OTHER, "character": "Kuro", "slot": "2"})
            edited = await rig.ask(player, "creq.save", cinema={**raw, "id": cid, "name": "Kokusen 2"})
            return (state, not_mine, sound, too_long, saved, hidden, queue_before, refused, sent, told, queue, approved, news, fires, edited)

    (state, not_mine, sound, too_long, saved, hidden, queue_before, refused, sent, told, queue, approved, news, fires, edited) = run(scenario())
    assert [c["name"] for c in state["data"]["characters"]] == ["Kuro"] and state["data"]["mine"] == [] and state["data"]["maxSeconds"] == MAX_REQUEST_SECONDS
    assert not_mine["t"] == "rpc_err" and "no es tuyo" in not_mine["reason"]
    assert sound["t"] == "rpc_err" and "sonidos" in sound["reason"]
    assert too_long["t"] == "rpc_err" and "como mucho" in too_long["reason"]
    assert saved["data"]["saved"]["status"] == "draft" and all(c["kind"] == "request" and c["share"] == "private" for c in saved["data"]["mine"])
    assert [c["name"] for c in hidden["data"]["cinemas"]] == [] and queue_before["data"]["requests"] == []
    assert refused["t"] == "rpc_err"
    assert sent["data"]["mine"][-1]["status"] == "pending" and "pide una cinemática" in told["text"]
    assert [c["id"] for c in queue["data"]["requests"]] == [saved["data"]["saved"]["id"]] and queue["data"]["requests"][0]["owner"]["id"] == str(OTHER)
    assert approved["data"]["requests"][0]["status"] == "approved" and "aprobó" in news["text"] and "Brutal" in news["text"]
    assert fires is True
    assert edited["data"]["saved"]["status"] == "draft"                                # changed after approval: it needs a new look


def test_the_review_ops_need_the_requests_box():
    assert OP_PERMS["gm.requests"] == OP_PERMS["gm.request_decide"] == "requests"
