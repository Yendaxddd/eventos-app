"""Cinematics: scripts of texts, sounds, pictures and channel messages at set moments. How they are checked and kept, how a run starts,
stops and writes its messages, what starts one by itself, and that only game masters can touch any of it."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import Hub, media  # noqa: E402
from eventos_app.activity.audio import AudioLibrary  # noqa: E402
from eventos_app.activity.cinema import MAX_STEPS, CinemaBook, CinemaDirector, clean_cinema, text_duration  # noqa: E402
from eventos_app.activity.hub import Conn, RpcError  # noqa: E402
from test_activity_gm_socket import GmRig, handlers  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402
from test_activity_play import frame, run  # noqa: E402
from test_audio import MP3, Sink, conn_of  # noqa: E402

PIC = "files/images/" + "a" * 24 + ".png"


def library(tmp_path):
    lib = AudioLibrary(media.MediaStore(tmp_path / "media"), tmp_path / "audio.json")
    lib.add("boom.mp3", MP3)
    return lib


def script(**extra):
    return {"name": "Llegada del Rey", "steps": [
        {"type": "text", "at": 4, "speaker": "Rey", "text": "Así que habéis venido.", "duration": 3},
        {"type": "scene", "at": 0, "color": "#110011", "image": PIC, "dim": 60},
        {"type": "audio", "at": 1.5, "mode": "play", "sound": "SOUND", "volume": 80},
        {"type": "effect", "at": 8, "effect": "shake"},
        {"type": "post", "at": 9, "text": "⚔️ El rey desenvaina."}], **extra}


def valid(tmp_path, **extra):
    lib = library(tmp_path)
    raw = script(**extra)
    raw["steps"][2]["sound"] = lib.public()[0]["id"]
    return lib, raw


# ---- checking ------------------------------------------------------------------------------------------------------------
def test_a_script_is_checked_step_by_step_put_in_time_order_and_measured(tmp_path):
    lib, raw = valid(tmp_path, triggers=["boss_spawn", "boss_spawn", "qte_hard", "nonsense"])
    cinema = clean_cinema(raw, lib)
    assert [s["type"] for s in cinema["steps"]] == ["scene", "audio", "text", "effect", "post"] and [s["at"] for s in cinema["steps"]] == [0, 1.5, 4, 8, 9]
    assert cinema["triggers"] == ["boss_spawn"]                                           # no duplicates, no unknown event, and a QTE is not an event to start one
    assert cinema["duration"] == 10.0 and cinema["bars"] is True and len(cinema["id"]) == 8
    text = cinema["steps"][2]
    assert text == {"type": "text", "at": 4.0, "text": "Así que habéis venido.", "speaker": "Rey", "avatar": None, "duration": 3.0, "effect": "type", "color": None, "size": "normal",
                    "side": "bottom"}
    assert cinema["see"] is False
    assert cinema["steps"][3]["duration"] == 0.6 and cinema["steps"][3]["color"] == "#ffffff"      # defaults for what was not said
    assert text_duration("hola") == 2.0 and text_duration("x" * 200) == 15.29 and text_duration("x" * 2000) == 20.0


@pytest.mark.parametrize("change, message", [
    (lambda r: r.update(name="  "), "necesita un nombre"), (lambda r: r.update(steps=[]), "al menos un paso"), (lambda r: r.update(steps="x"), "al menos un paso"),
    (lambda r: r["steps"].append({"type": "boom"}), "no existe"), (lambda r: r["steps"].append("x"), "no es un paso válido"),
    (lambda r: r["steps"][1].update(at=-1), "Paso 2, momento"), (lambda r: r["steps"][1].update(at="soon"), "número de segundos"),
    (lambda r: r["steps"][1].update(color="red"), "#ff8800"), (lambda r: r["steps"][1].update(image="https://evil/x.png"), "no es de la biblioteca"),
    (lambda r: r["steps"][1].update(image="files/images/../../x.png"), "no es de la biblioteca"),
    (lambda r: r["steps"][0].update(text=" "), "texto está vacío"), (lambda r: r["steps"][0].update(duration=0), "Paso 1, duración"),
    (lambda r: r["steps"][2].update(sound="zzzz"), "ya no está"), (lambda r: r["steps"][2].update(sound=""), "elige un sonido"),
    (lambda r: r["steps"][4].update(text=""), "mensaje está vacío"), (lambda r: r["steps"].extend({"type": "effect", "at": 1} for _ in range(MAX_STEPS)), "hasta 200"),
])
def test_what_is_wrong_in_a_script_is_said_in_spanish_with_the_step(tmp_path, change, message):
    lib, raw = valid(tmp_path)
    change(raw)
    with pytest.raises(RpcError, match=message):
        clean_cinema(raw, lib)


def test_the_creator_steps_dialogue_screen_effects_camera_titles_and_weather_are_kept_in_range(tmp_path):
    lib, raw = valid(tmp_path, see=True)
    raw["steps"] += [
        {"type": "text", "at": 2, "speaker": "Kuro", "text": "¿Quién eres?", "side": "left", "avatar": PIC},
        {"type": "text", "at": 4, "speaker": "Shiro", "text": "Tu sombra.", "side": "right", "effect": "pop"},
        {"type": "effect", "at": 3, "effect": "blur", "intensity": 300, "duration": 2},
        {"type": "effect", "at": 3, "effect": "nope"},
        {"type": "scene", "at": 5, "image": PIC, "camera": "pan_left", "camera_time": 20, "transition": "flash"},
        {"type": "image", "at": 6, "image": PIC, "enter": "slide_left", "size": "full", "camera": "zoom_in"},
        {"type": "title", "at": 7, "text": "  Capítulo II  ", "subtitle": "La caída", "style": "chapter"},
        {"type": "weather", "at": 0, "weather": "snow", "intensity": 30},
        {"type": "weather", "at": 9, "weather": "tornado"}]
    cinema = clean_cinema(raw, lib)
    steps = cinema["steps"]
    left, right = [s for s in steps if s["type"] == "text" and s["side"] != "bottom"]
    assert left["side"] == "left" and left["avatar"] == PIC and right["side"] == "right" and right["effect"] == "pop"
    blur, fallback = [s for s in steps if s["type"] == "effect" and s["at"] == 3]
    assert blur["effect"] == "blur" and blur["intensity"] == 100 and fallback["effect"] == "flash" and fallback["intensity"] == 60
    scene = next(s for s in steps if s["type"] == "scene" and s["at"] == 5)
    assert scene["camera"] == "pan_left" and scene["camera_time"] == 20 and scene["transition"] == "flash"
    image = next(s for s in steps if s["type"] == "image")
    assert (image["enter"], image["size"], image["camera"], image["position"]) == ("slide_left", "full", "zoom_in", "center")
    title = next(s for s in steps if s["type"] == "title")
    assert title["text"] == "Capítulo II" and title["subtitle"] == "La caída" and title["style"] == "chapter" and title["duration"] == 3.5
    weather = [s for s in steps if s["type"] == "weather"]
    assert weather[0] == {"type": "weather", "at": 0.0, "weather": "snow", "intensity": 30} and weather[1]["weather"] == "rain"
    assert cinema["see"] is True
    with pytest.raises(RpcError, match="título está vacío"):
        clean_cinema({**raw, "steps": [{"type": "title", "at": 0, "text": " "}]}, lib)


# ---- keeping --------------------------------------------------------------------------------------------------------------
def test_a_visual_effect_step_keeps_its_look_in_range_and_counts_in_the_length(tmp_path):
    lib, raw = valid(tmp_path)
    raw["steps"].append({"type": "vfx", "at": 10, "preset": "dominio", "color": "#FF0000", "intensity": 999, "speed": 1, "banner": "  ¡Ryōiki!  ", "duration": 2.5, "extra": "x"})
    cinema = clean_cinema(raw, lib)
    step = next(s for s in cinema["steps"] if s["type"] == "vfx")
    assert step == {"type": "vfx", "at": 10.0, "preset": "dominio", "color": "#ff0000", "intensity": 200, "speed": 50, "banner": "¡Ryōiki!", "duration": 2.5}
    assert cinema["duration"] >= 12.5
    raw["steps"][-1] = {"type": "vfx", "at": 1, "preset": "nope"}
    again = next(s for s in clean_cinema(raw, lib)["steps"] if s["type"] == "vfx")
    assert again["preset"] == "impacto" and again["duration"] == 1.5                        # an unknown look falls back, a missing length is a second and a half


def test_scripts_are_saved_duplicated_deleted_and_survive_a_restart_even_if_the_file_was_edited_badly(tmp_path):
    lib, raw = valid(tmp_path)
    book = CinemaBook(tmp_path / "cinematics.json", lib)
    first = book.put(raw)
    copy = book.duplicate(first["id"])
    assert copy["name"].endswith("(copia)") and copy["id"] != first["id"] and len(book.listing()) == 2
    edited = book.put({**raw, "id": first["id"], "name": "Otro nombre"})
    assert edited["id"] == first["id"] and len(book.listing()) == 2 and book.get(first["id"])["name"] == "Otro nombre"
    stranger = book.put({**raw, "id": "deadbeef"})                                          # an id the book never gave: it becomes a new script
    assert stranger["id"] != "deadbeef" and len(book.listing()) == 3
    again = CinemaBook(tmp_path / "cinematics.json", lib)
    assert [c["name"] for c in again.listing()] == ["Otro nombre", "Llegada del Rey (copia)", "Llegada del Rey"]
    data = json.loads((tmp_path / "cinematics.json").read_text(encoding="utf-8"))
    data["cinemas"].append({"id": "abcdef01", "name": "rota", "steps": [{"type": "nope"}]})
    data["cinemas"].append("basura")
    (tmp_path / "cinematics.json").write_text(json.dumps(data), encoding="utf-8")
    assert len(CinemaBook(tmp_path / "cinematics.json", lib).listing()) == 3                # the broken ones are left out
    (tmp_path / "cinematics.json").write_text("{ not json", encoding="utf-8")
    assert CinemaBook(tmp_path / "cinematics.json", lib).listing() == []
    book.delete(first["id"])
    with pytest.raises(RpcError):
        book.delete(first["id"])
    with pytest.raises(RpcError):
        book.duplicate(first["id"])


# ---- playing ---------------------------------------------------------------------------------------------------------------
def test_a_run_starts_for_everybody_writes_its_messages_at_their_moment_and_can_be_stopped(tmp_path):
    async def scenario():
        hub = Hub()
        lib, raw = valid(tmp_path)
        raw["steps"][4]["at"] = 0.1
        raw["steps"][3]["at"] = 0.1
        said = []

        async def post(text):
            said.append(text)

        book = CinemaBook(None, lib)
        director = CinemaDirector(hub, book, post=post)
        (_, ana), (_, mina) = conn_of(hub, 1), conn_of(hub, 2)
        cinema = book.put(raw)
        started = await director.play(cinema["id"])
        before = director.current()
        await asyncio.sleep(0.3)
        await director.stop()
        await asyncio.sleep(0.05)
        late, late_sink = conn_of(hub, 3)
        return ana.frames, mina.frames, said, before, director.current(), started["id"]

    ana, mina, said, before, after, cid = run(scenario())
    assert ana == mina and [f["op"] for f in ana] == ["start", "stop"]
    assert ana[0]["run"]["id"] == cid and ana[0]["run"]["cinema"]["name"] == "Llegada del Rey" and "startedAt" in ana[0]["run"] and "now" in ana[0]["run"]
    assert said == ["⚔️ El rey desenvaina."] and before["id"] == cid and after is None


def test_a_second_run_replaces_the_first_a_stopped_run_writes_nothing_and_a_long_gone_run_is_not_joined(tmp_path):
    async def scenario():
        hub = Hub()
        lib, raw = valid(tmp_path)
        raw["steps"][4]["at"] = 0.2
        said = []

        async def post(text):
            said.append(text)

        book = CinemaBook(None, lib)
        director = CinemaDirector(hub, book, post=post)
        a, b = book.put(raw), book.put({**raw, "name": "Segunda"})
        await director.play(a["id"])
        await director.play(b["id"])                                       # the first one's messages must not come out
        await director.stop()
        await asyncio.sleep(0.4)
        await director.play(a["id"])
        director.run["startedAt"] -= 3_600_000                             # an hour ago
        gone = director.current()
        with pytest.raises(RpcError):
            await director.play("00000000")
        return said, gone

    said, gone = run(scenario())
    assert said == [] and gone is None


def test_a_script_bound_to_an_event_starts_by_itself_unless_one_is_already_playing_or_the_game_masters_switched_it_off(tmp_path):
    async def scenario():
        hub = Hub()
        lib, raw = valid(tmp_path, triggers=["boss_defeated"])
        book = CinemaBook(None, lib)
        director = CinemaDirector(hub, book)
        conn_of(hub, 1)
        cinema = book.put(raw)
        out = {"other": await director.on_event("boss_spawn")}
        out["first"] = await director.on_event("boss_defeated", {"name": "Rey"})
        out["busy"] = await director.on_event("boss_defeated")
        await director.stop()
        director.on_event_enabled = False
        out["off"] = await director.on_event("boss_defeated")
        return out, cinema["id"]

    out, _ = run(scenario())
    assert out == {"other": False, "first": True, "busy": False, "off": False}


# ---- the panel -------------------------------------------------------------------------------------------------------------------
def test_the_cinematics_tab_works_for_game_masters_only_and_every_change_is_heard_and_signed(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            store = media.MediaStore(tmp_path / "media")
            rig.bridge.audio.library.store, rig.bridge.audio.library.path = store, tmp_path / "audio.json"
            rig.bridge.cinema.book.path = tmp_path / "cinematics.json"
            rig.server.files = store
            sound = rig.bridge.audio.library.add("boom.mp3", MP3)
            posted = []

            async def send(content=None, **kwargs):
                posted.append((content, kwargs.get("allowed_mentions") is not None))
            rig.channel.send = send
            gm, _ = await rig.login(ME)
            player, _ = await rig.login(OTHER)
            base = f"http://127.0.0.1:{rig.port}"
            png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
            async with rig.http.post(f"{base}/api/image", data=png, headers={"X-Dev": "Ana", "X-Filename": "fondo.png"}) as r:
                no_gm = (r.status, (await r.json())["error"])
            async with rig.http.post(f"{base}/api/image", data=b"<html>", headers={"X-Dev": "Ana", "X-Gm": "1"}) as r:
                junk = (r.status, (await r.json())["error"])
            async with rig.http.post(f"{base}/api/image", data=png, headers={"X-Dev": "Ana", "X-Gm": "1", "X-Filename": "fondo.png"}) as r:
                picture = (await r.json())["path"]
            raw = script(triggers=["boss_defeated"])
            raw["steps"][1]["image"] = picture
            raw["steps"][2]["sound"] = sound["id"]
            raw["steps"][4]["at"] = 0.05
            refused = await rig.ask(player, "gm.cinemas")
            state = await rig.ask(gm, "gm.cinemas")
            bad = await rig.ask(gm, "gm.cinema_save", cinema={**raw, "name": ""})
            saved = await rig.ask(gm, "gm.cinema_save", cinema=raw)
            cid = saved["data"]["saved"]["id"]
            copy = await rig.ask(gm, "gm.cinema_duplicate", id=cid)
            played = await rig.ask(gm, "gm.cinema_play", id=cid)
            heard = await frame(player, "cine")
            await asyncio.sleep(0.2)
            late, welcome = await rig.login(OTHER)
            stopped = await rig.ask(gm, "gm.cinema_stop")
            auto = await rig.ask(gm, "gm.cinema_auto", enabled=False)
            deleted = await rig.ask(gm, "gm.cinema_delete", id=cid)
            return (no_gm, junk, picture, refused, state, bad, saved, copy, played, heard, welcome["cine"], stopped, auto, deleted, posted, rig.bridge.gm.log.recent(),
                    store.exists(media.IMAGES, picture.rsplit("/", 1)[1]))

    (no_gm, junk, picture, refused, state, bad, saved, copy, played, heard, joined, stopped, auto, deleted, posted, history, stored) = run(scenario())
    assert no_gm[0] == 403 and "equipo de GM" in no_gm[1] and junk[0] == 400 and "imágenes" in junk[1] and picture.startswith("files/images/") and stored
    assert refused["t"] == "rpc_err" and "equipo de GM" in refused["reason"]
    assert state["data"]["cinemas"] == [] and {e["id"] for e in state["data"]["events"]} >= {"boss_defeated", "domain", "player_down"} and "qte_hard" not in {e["id"] for e in state["data"]["events"]}
    assert state["data"]["sounds"][0]["name"] == "boom" and state["data"]["canStore"] is True
    assert bad["t"] == "rpc_err" and "nombre" in bad["reason"] and saved["data"]["saved"]["duration"] == 9.6
    assert copy["data"]["saved"]["name"].endswith("(copia)") and len(copy["data"]["cinemas"]) == 2
    assert played["data"]["running"] == cid_of(saved) and heard["op"] == "start" and heard["run"]["cinema"]["name"] == "Llegada del Rey"
    assert joined and joined["id"] == cid_of(saved)                                           # who comes in while it plays joins it
    assert stopped["data"]["running"] is None and auto["data"]["autoplay"] is False and len(deleted["data"]["cinemas"]) == 1
    assert posted == [("⚔️ El rey desenvaina.", True)]                                       # written once, without pinging anybody
    assert any("Puso la cinemática" in e["action"] for e in history) and any("Guardó la cinemática" in e["action"] for e in history)


def cid_of(answer):
    return answer["data"]["saved"]["id"]


def test_every_request_of_the_cinematics_tab_is_part_of_the_role_checked_panel():
    names = handlers()
    for expected in ("gm.cinemas", "gm.cinema_save", "gm.cinema_delete", "gm.cinema_duplicate", "gm.cinema_play", "gm.cinema_stop", "gm.cinema_auto"):
        assert expected in names


def test_a_script_made_for_one_boss_only_starts_for_that_boss_and_wins_over_one_for_any_boss(tmp_path):
    async def scenario():
        hub = Hub()
        lib, raw = valid(tmp_path)
        book = CinemaBook(tmp_path / "c.json", lib)
        director = CinemaDirector(hub, book, post=None)
        general = book.put({**raw, "name": "Cualquier jefe", "triggers": ["boss_defeated"]})
        rey = book.put({**raw, "name": "Solo el Rey", "triggers": ["boss_defeated"], "boss": "  rey de las maldiciones "})
        assert rey["boss"] == "rey de las maldiciones" and general["boss"] == ""
        first = await director.on_event("boss_defeated", {"name": "Rey de las Maldiciones"})
        started = director.current()["id"]
        await director.stop()
        other = await director.on_event("boss_defeated", {"name": "Goblin"})
        second = director.current()["id"]
        await director.stop()
        return first, started == rey["id"], other, second == general["id"]

    assert run(scenario()) == (True, True, True, True)


def test_one_cinematic_is_chosen_for_a_moment_of_the_fight_and_the_others_lose_that_trigger(tmp_path):
    async def scenario():
        async with GmRig() as rig:
            lib, raw = valid(tmp_path)
            rig.bridge.cinema.book.library, rig.bridge.cinema.book.path = lib, tmp_path / "c.json"
            first = rig.bridge.cinema.book.put({**raw, "name": "Uno", "triggers": ["boss_spawn", "boss_defeated"]})
            second = rig.bridge.cinema.book.put({**raw, "name": "Dos", "triggers": []})
            gm, _ = await rig.login(ME)
            player, _ = await rig.login(OTHER)
            moved = await rig.ask(gm, "gm.cinema_link", event="boss_spawn", id=second["id"])
            triggers = {c["name"]: c["triggers"] for c in rig.bridge.cinema.book.listing()}
            bad = await rig.ask(gm, "gm.cinema_link", event="qte_start", id=second["id"])
            gone = await rig.ask(gm, "gm.cinema_link", event="boss_spawn", id="nope")
            cleared = await rig.ask(gm, "gm.cinema_link", event="boss_defeated", id="")
            await player.send_json({"t": "rpc", "id": "p", "op": "gm.cinema_link", "args": {"event": "boss_spawn", "id": ""}})
            refused = None
            while refused is None:
                got = await asyncio.wait_for(player.receive_json(), 3)
                if got.get("id") == "p":
                    refused = got
            return moved, triggers, bad, gone, cleared, refused, {c["name"]: c["triggers"] for c in rig.bridge.cinema.book.listing()}

    moved, triggers, bad, gone, cleared, refused, after = run(scenario())
    assert moved["t"] == "rpc_ok" and triggers == {"Uno": ["boss_defeated"], "Dos": ["boss_spawn"]}
    assert bad["t"] == "rpc_err" and "no puede" in bad["reason"] and gone["t"] == "rpc_err" and "ya no existe" in gone["reason"]
    assert cleared["t"] == "rpc_ok" and after == {"Uno": [], "Dos": ["boss_spawn"]}
    assert refused["t"] == "rpc_err" and "equipo de GM" in refused["reason"]
