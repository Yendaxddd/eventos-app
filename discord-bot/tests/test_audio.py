"""The event's sound: the library the game masters fill, the cues bound to what happens, the music everybody hears together, and the
requests of the panel's Audio tab (only for who has the GM role)."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import Hub, media  # noqa: E402
from eventos_app.activity.audio import EVENTS, AudioDirector, AudioLibrary  # noqa: E402
from eventos_app.activity.hub import Conn, RpcError  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402
from test_activity_play import frame, run  # noqa: E402

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64
WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 32


class Sink:
    """A socket that keeps what it is sent."""

    def __init__(self):
        self.frames = []

    async def send_json(self, frame):
        self.frames.append(frame)

    async def close(self, **kwargs):
        pass


def conn_of(hub, user_id):
    sink = Sink()
    conn = Conn(hub.new_id(), user_id, f"u{user_id}", "", sink)
    hub.conns[conn.id] = conn
    return conn, sink


async def ask_seeing(rig, ws, op, **args):
    """The answer to a request and every frame that came in before it (`ask` throws those away)."""
    rig.calls_made = getattr(rig, "calls_made", 0) + 1
    call = f"a{rig.calls_made}"
    await ws.send_json({"t": "rpc", "id": call, "op": op, "args": args})
    seen = []
    while True:
        got = await asyncio.wait_for(ws.receive_json(), 3)
        if got.get("id") == call and got["t"] in ("rpc_ok", "rpc_err"):
            return got, seen
        seen.append(got)


def library(tmp_path):
    return AudioLibrary(media.MediaStore(tmp_path / "media"), tmp_path / "audio.json")


# ---- the library -----------------------------------------------------------------------------------------------------
def test_sounds_are_added_renamed_kept_between_runs_and_deleted_with_their_cues(tmp_path):
    lib = library(tmp_path)
    boom = lib.add("explosión grande.mp3", MP3, "sfx")
    theme = lib.add("tema del jefe.ogg", OGG, "music")
    assert boom["name"] == "explosión grande" and boom["file"].startswith("files/audio/") and theme["loop"] is True and boom["loop"] is False
    assert lib.add("otra.ogg", OGG + b"1", "nonsense")["kind"] == "sfx"                     # an unknown kind: guessed from the size
    for bad in (b"", b"<html>", media.sniff_image and b"\x89PNG\r\n\x1a\n" + b"\x00" * 20):
        with pytest.raises(RpcError):
            lib.add("x.mp3", bad)
    lib.set_cue("black_flash", boom["id"], 80, "all")
    lib.set_cue("boss_defeated", theme["id"], 100, "target")
    changed = lib.update(boom["id"], {"name": "  Boom\n  grande ", "volume": 250, "loop": 1, "kind": "voice"})
    assert changed["name"] == "Boom grande" and changed["volume"] == 100 and changed["loop"] is True and changed["kind"] == "voice"
    for bad in ({"name": "   "}, {"kind": "nope"}):
        with pytest.raises(RpcError):
            lib.update(boom["id"], bad)
    again = library(tmp_path)                                                               # a new run reads the file
    assert [s["name"] for s in again.public()] == ["Boom grande", "tema del jefe", "otra"] and set(again.cues) == {"black_flash", "boss_defeated"}
    removed = again.delete(boom["id"])
    assert "black_flash" not in again.cues and "boss_defeated" in again.cues and removed["name"] == "Boom grande"
    assert not again.store.exists(media.AUDIO, removed["file"].rsplit("/", 1)[1])            # nobody else uses that file: it goes too
    with pytest.raises(RpcError):
        again.delete(boom["id"])


def test_a_file_two_sounds_share_stays_until_the_last_of_them_goes(tmp_path):
    lib = library(tmp_path)
    one, two = lib.add("a.mp3", MP3, "sfx"), lib.add("b.mp3", MP3, "sfx")
    assert one["file"] == two["file"] and one["id"] != two["id"]
    lib.delete(one["id"])
    assert lib.store.exists(media.AUDIO, two["file"].rsplit("/", 1)[1])
    lib.delete(two["id"])
    assert not lib.store.exists(media.AUDIO, two["file"].rsplit("/", 1)[1])


def test_a_damaged_or_tampered_library_file_never_breaks_the_app(tmp_path):
    path = tmp_path / "audio.json"
    path.write_text("{ not json", encoding="utf-8")
    assert library(tmp_path).public() == []
    path.write_text(json.dumps({"sounds": [{"id": "zz", "file": "files/audio/x.mp3"}, {"id": "abcdef01", "file": "../../etc/passwd"}, "junk",
                                           {"id": "abcdef02", "name": "ok", "file": "files/audio/" + "a" * 24 + ".mp3", "volume": "loud", "kind": "weird"}],
                                "cues": {"nope": {"sound": "abcdef02"}, "black_flash": {"sound": "missing"}, "boss_spawn": {"sound": "abcdef02", "scope": "x", "volume": 999}}}),
                    encoding="utf-8")
    lib = library(tmp_path)
    assert [s["id"] for s in lib.public()] == ["abcdef02"] and lib.public()[0]["volume"] == 100 and lib.public()[0]["kind"] == "sfx"
    assert list(lib.cues) == ["boss_spawn"] and lib.cues["boss_spawn"]["scope"] == "all" and lib.cues["boss_spawn"]["volume"] == 100
    with pytest.raises(RpcError):
        lib.set_cue("nope", "abcdef02")
    with pytest.raises(RpcError):
        lib.set_cue("black_flash", "missing")
    assert set(EVENTS) >= {"black_flash", "boss_defeated", "domain", "qte_start", "player_down"}


def test_a_qte_uses_the_cue_of_its_mode_then_its_difficulty_then_the_general_one(tmp_path):
    lib = library(tmp_path)
    a, b, c = (lib.add(f"{n}.mp3", MP3 + bytes([i]), "sfx")["id"] for i, n in enumerate("abc"))
    assert lib.cue_for("qte", {"mode": "group", "difficulty": "hard"}) is None
    lib.set_cue("qte_start", a)
    assert lib.cue_for("qte", {"mode": "single", "difficulty": "easy"})[1]["sound"] == a
    lib.set_cue("qte_hard", b)
    assert lib.cue_for("qte", {"mode": "single", "difficulty": "hard"})[1]["sound"] == b
    lib.set_cue("qte_group", c)
    assert lib.cue_for("qte", {"mode": "group", "difficulty": "hard"})[1]["sound"] == c           # the mode beats the difficulty
    lib.set_cue("qte_group", c, enabled=False)
    assert lib.cue_for("qte", {"mode": "group", "difficulty": "hard"})[1]["sound"] == b           # a switched-off cue is skipped
    assert lib.cue_for("black_flash", {}) is None


def test_the_combat_slots_exist_and_a_power_uses_its_slots_cue_before_the_general_one(tmp_path):
    for event in ("evade_ok", "parry_ok", "counter", "rescue_ok", "qte_fail", "combo_step", "player_hit", "low_hp", "heal", "boss_hit", "power_used", "power_1", "power_2"):
        assert event in EVENTS, event
    lib = library(tmp_path)
    any_power, first = (lib.add(f"{n}.mp3", MP3 + bytes([i]), "sfx")["id"] for i, n in enumerate(("cualquiera", "uno")))
    assert lib.cue_for("power_used", {"slot": 1}) is None
    lib.set_cue("power_used", any_power)
    assert lib.cue_for("power_used", {"slot": 2})[1]["sound"] == any_power
    lib.set_cue("power_1", first)
    assert lib.cue_for("power_used", {"slot": 1})[1]["sound"] == first                          # the slot's own sound wins
    assert lib.cue_for("power_used", {"slot": 2})[1]["sound"] == any_power
    assert EVENTS["parry_ok"][1] == "target" and EVENTS["boss_hit"][1] == "all"                # who hears it


def test_the_music_follows_the_fight_by_itself_and_what_is_bound_to_a_deleted_track_goes_with_it(tmp_path):
    async def scenario():
        hub = Hub()
        lib = library(tmp_path)
        director = AudioDirector(hub, lib)
        calm, battle = (lib.add(f"{n}.ogg", OGG + bytes([i]), "music")["id"] for i, n in enumerate(("calma", "batalla")))
        for call, message in ((lambda: lib.set_phase("qte_start", "stop"), "no puede"), (lambda: lib.set_phase("fight_start", "music", "zz"), "pista"), (lambda: lib.set_phase("fight_start", "loud"), "no existe")):
            try:
                call()
            except RpcError as exc:
                assert message in str(exc)
            else:
                raise AssertionError(message)
        lib.set_phase("fight_start", "music", battle, 80)
        lib.set_phase("fight_end", "music", calm, 50)
        lib.set_phase("boss_defeated", "stop")
        seen = []
        await director.dispatch("fight_start", {})
        seen.append(director.music["sound"]["name"])
        await director.dispatch("boss_defeated", {"name": "Rey"})
        seen.append(director.music)
        await director.dispatch("fight_end", {})
        seen.append((director.music["sound"]["name"], director.music["volume"]))
        reloaded = AudioLibrary(lib.store, lib.path)
        lib.delete(battle)
        return seen, dict(reloaded.phases), dict(lib.phases)

    seen, reloaded, after = run(scenario())
    assert seen == ["batalla", None, ("calma", 50)]
    assert set(reloaded) == {"fight_start", "fight_end", "boss_defeated"} and reloaded["boss_defeated"]["mode"] == "stop"             # kept between runs
    assert set(after) == {"fight_end", "boss_defeated"}


# ---- playing ---------------------------------------------------------------------------------------------------------
def test_a_cue_plays_for_who_it_is_about_or_for_everybody_and_the_music_is_the_same_for_all(tmp_path):
    async def scenario():
        hub = Hub()
        lib = library(tmp_path)
        director = AudioDirector(hub, lib)
        (_, ana), (_, mina) = conn_of(hub, 1), conn_of(hub, 2)
        boom = lib.add("boom.mp3", MP3)
        theme = lib.add("tema.ogg", OGG, "music")
        lib.update(boom["id"], {"volume": 50})
        lib.set_cue("black_flash", boom["id"], 80, "all")
        lib.set_cue("qte_start", boom["id"], 100, "target")
        out = {"none": await director.dispatch("boss_defeated", {})}                          # nothing is bound to it
        out["bf"] = await director.dispatch("black_flash", {"user": 1})
        out["qte"] = await director.dispatch("qte", {"mode": "single", "difficulty": "easy", "user": 2})
        out["unknown_target"] = await director.dispatch("qte", {"mode": "fake", "difficulty": "easy", "user": None})
        await director.start_music(theme["id"], 70)
        late, late_sink = conn_of(hub, 3)
        await director.set_music_volume(30)
        await director.stop_music()
        return out, ana.frames, mina.frames, late_sink.frames, director.welcome()

    out, ana, mina, late, welcome = run(scenario())
    assert out == {"none": False, "bf": True, "qte": True, "unknown_target": True}
    plays_ana = [f for f in ana if f["op"] == "play"]
    plays_mina = [f for f in mina if f["op"] == "play"]
    assert [f["volume"] for f in plays_ana] == [40, 50] and [f["volume"] for f in plays_mina] == [40, 50, 50]      # cue volume x the sound's own volume
    assert plays_ana[0]["sound"]["file"].startswith("files/audio/") and "at" in plays_ana[0]
    assert len(plays_mina) == 3 and len(plays_ana) == 2                                      # the QTE cue was for Mina (and for all when it names nobody)
    music = [f for f in mina if f["op"] == "music"]
    assert [m["music"] and m["music"]["volume"] for m in music] == [70, 30, None] and music[1]["keep"] is True
    assert music[0]["music"]["sound"]["name"] == "tema" and music[0]["music"]["loop"] is True and "startedAt" in music[0]["music"]
    assert [f["op"] for f in late] == ["music", "music"]                                      # somebody who came in late hears the changes from then on
    assert welcome["music"] is None and len(welcome["library"]) == 2


def test_a_player_who_comes_in_while_music_plays_is_told_where_it_started(tmp_path):
    async def scenario():
        hub = Hub()
        lib = library(tmp_path)
        director = AudioDirector(hub, lib)
        theme = lib.add("tema.ogg", OGG, "music")
        await director.start_music(theme["id"], 90, loop=False)
        await asyncio.sleep(0.05)
        return director.welcome()["music"], hub.now_ms()

    music, now = run(scenario())
    assert music["sound"]["name"] == "tema" and music["loop"] is False and music["volume"] == 90
    assert 0 < music["now"] - music["startedAt"] < 5000 and music["now"] <= now


# ---- the panel's requests ----------------------------------------------------------------------------------------------
def test_the_audio_tab_works_for_game_masters_only_and_every_change_is_heard_and_signed(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            store = media.MediaStore(tmp_path / "media")
            rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
            rig.server.files = store
            gm, _ = await rig.login(ME)
            player, _ = await rig.login(OTHER)
            base = f"http://127.0.0.1:{rig.port}"
            async with rig.http.post(f"{base}/api/audio", data=MP3, headers={"X-Dev": "Ana", "X-Filename": "bum%20bum.mp3", "X-Kind": "sfx"}) as r:
                refused = (r.status, (await r.json())["error"])                                   # a test window that did not ask to be a GM
            async with rig.http.post(f"{base}/api/audio", data=b"not audio", headers={"X-Dev": "Ana", "X-Gm": "1"}) as r:
                junk = (r.status, (await r.json())["error"])
            async with rig.http.post(f"{base}/api/audio", data=MP3, headers={"X-Dev": "Ana", "X-Gm": "1", "X-Filename": "bum%20bum.mp3", "X-Kind": "sfx"}) as r:
                uploaded = (r.status, await r.json())
            sound = uploaded[1]["sound"]
            state = await rig.ask(gm, "gm.audio")
            bad_for_player, before = await ask_seeing(rig, player, "gm.audio")
            library_announced = [f for f in before if f["t"] == "audio"]
            cue = await rig.ask(gm, "gm.cue_set", event="boss_defeated", sound=sound["id"], volume=70, scope="all")
            music = await rig.ask(gm, "gm.music_play", id=sound["id"], volume=60, loop=True)
            heard = [*library_announced, await frame(player, "audio")]                              # the library announcement, then the music
            await rig.ask(gm, "gm.audio_play", id=sound["id"], volume=90)
            played = await frame(player, "audio")
            tested, around = await ask_seeing(rig, gm, "gm.cue_test", event="boss_defeated")              # the sound reaches the screen of who asked, only
            mine = next(f for f in around if f["t"] == "audio")
            untested = await rig.ask(gm, "gm.cue_test", event="black_flash")
            rig.app.emit_event = None
            rig.bridge.on_event("boss_defeated", {"name": "Rey"})                                 # the game says the boss fell
            cued = await frame(player, "audio")
            volume = await rig.ask(gm, "gm.music_volume", volume=20)
            stopped = await rig.ask(gm, "gm.music_stop")
            removed = await rig.ask(gm, "gm.audio_delete", id=sound["id"])
            history = rig.bridge.gm.log.recent()
            async with rig.http.get(f"{base}/{sound['file']}") as r:
                gone = r.status
            return refused, junk, uploaded, state, bad_for_player, cue, music, heard, played, tested, mine, untested, cued, volume, stopped, removed, history, gone

    (refused, junk, uploaded, state, bad_for_player, cue, music, heard, played, tested, mine, untested, cued, volume, stopped, removed, history, gone) = run(scenario())
    assert refused[0] == 403 and "equipo de GM" in refused[1] and junk[0] == 400 and "audios" in junk[1]
    assert uploaded[0] == 200 and uploaded[1]["sound"]["name"] == "bum bum" and state["data"]["usage"]["files"] == 1
    assert [s["id"] for s in state["data"]["library"]] == [uploaded[1]["sound"]["id"]] and state["data"]["canStore"] is True
    assert {e["id"] for e in state["data"]["events"]} == set(EVENTS)
    assert bad_for_player["t"] == "rpc_err" and "equipo de GM" in bad_for_player["reason"]
    assert cue["data"]["cues"]["boss_defeated"]["volume"] == 70 and music["data"]["music"]["volume"] == 60
    assert [h["op"] for h in heard] == ["library", "music"] and heard[1]["music"]["sound"]["name"] == "bum bum"
    assert played["op"] == "play" and played["volume"] == 90 and tested["t"] == "rpc_ok" and mine["op"] == "play" and mine["volume"] == 70
    assert untested["t"] == "rpc_err" and "todavía no tiene sonido" in untested["reason"]
    assert cued["op"] == "play" and cued["volume"] == 70
    assert volume["data"]["music"]["volume"] == 20 and stopped["data"]["music"] is None and removed["data"]["library"] == [] and gone == 404
    assert any("Subió el sonido" in e["action"] for e in history) and any("Puso la música" in e["action"] for e in history)
