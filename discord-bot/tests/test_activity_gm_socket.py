"""The game-master panel as the Activity reaches it: over the socket, through the real bridge and server, with the bot's role check
deciding who gets in. The operations themselves are tested in test_activity_gm.py; here it is about WHO may ask and that every
request is wired to something."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import ActivityBridge, Hub  # noqa: E402
from test_activity_gm import Rig as GmBot  # noqa: E402
from test_activity_panel import ME, OTHER, PanelRig  # noqa: E402

NOT_GM = "Esto es solo para el equipo de GM."
GENERIC_FAILURE = "Algo falló al procesarlo; inténtalo otra vez."


def run(coro):
    return asyncio.run(coro)


def handlers() -> list[str]:
    """The name of every request the panel answers, as the page writes it (`gm.boss_hp`)."""
    return sorted("gm." + name[len("rpc_gm_"):] for name in dir(ActivityBridge) if name.startswith("rpc_gm_"))


def _no_constants(name):
    raise ValueError(f"the page cannot read {name} in JSON")


class GmRig(PanelRig):
    """The play rig with a real bridge that keeps its GM files in a temp folder, and behind it the fake bot of the GM tests.
    Ana (111) has the GM role; Mina (222) is a player. `admins` is the bot's idea of who has the role, and can change at any time."""

    async def __aenter__(self):
        self._gm_tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._gm_tmp.name)
        self.bridge_args = {"data_dir": self.base / "data", "gm_log_file": self.base / "gm_log.jsonl", "values_file": self.base / "gm_values.json"}
        self.admins = {ME}
        await super().__aenter__()
        people = {uid: NS(id=uid, display_name=name, name=name.lower(), display_avatar=NS(url=f"https://cdn.discordapp.com/avatars/{uid}/a.png"))
                  for uid, name in ((ME, "Ana"), (OTHER, "Mina"))}
        self.bot = GmBot(self.base, app=self.app, guild=NS(get_member=people.get))
        self.app.is_admin = lambda member: member.id in self.admins
        return self

    async def __aexit__(self, *exc):
        await super().__aexit__(*exc)
        self._gm_tmp.cleanup()

    async def ask(self, ws, op, **args):
        """The answer to a request, read the way the page reads it: a number the page could not parse (NaN, Infinity) is an error."""
        self.calls_made = getattr(self, "calls_made", 0) + 1
        call = f"g{self.calls_made}"
        await ws.send_json({"t": "rpc", "id": call, "op": op, "args": args})
        while True:
            raw = await asyncio.wait_for(ws.receive_str(), 3)
            got = json.loads(raw)
            if got.get("id") == call and got["t"] in ("rpc_ok", "rpc_err"):
                return json.loads(raw, parse_constant=_no_constants)

    async def dev(self, name="Ana", gm=False):
        ws = await self.http.ws_connect(f"http://127.0.0.1:{self.port}/ws")
        await ws.send_json({"t": "hello", "dev": name, **({"gm": True} if gm else {})})
        return ws, await ws.receive_json()

    async def ask_all(self, ops, user_id=ME, **args):
        """Every request in `ops`, each with the same arguments, over as many connections as the per-connection rate limit needs."""
        answers, ws = {}, None
        for index, op in enumerate(ops):
            if index % 30 == 0:
                if ws is not None:
                    await ws.close()
                ws, _ = await self.login(user_id)
            answers[op] = await self.ask(ws, op, **args)
        await ws.close()
        return answers


# ---- who may ask ----------------------------------------------------------------------------------------------------------------
def test_the_panel_has_something_for_every_part_of_the_event():
    names = handlers()
    assert len(names) >= 50
    for expected in ("gm.state", "gm.launch", "gm.batch", "gm.fight", "gm.boss_register", "gm.boss_hp", "gm.players", "gm.player", "gm.hp", "gm.values", "gm.value_set",
                     "gm.qte_set", "gm.data", "gm.file_get", "gm.file_save", "gm.achievements", "gm.objects", "gm.obj_approve", "gm.history"):
        assert expected in names


def test_nobody_without_the_role_gets_anything_from_any_request_and_nothing_happens():
    async def scenario():
        async with GmRig() as rig:
            ws, welcome = await rig.login(OTHER)
            before = json.dumps(rig.bridge.gm.state(), sort_keys=True)
            await ws.close()
            answers = await rig.ask_all(handlers(), user_id=OTHER)           # no arguments: the role is checked before anything else
            ws, _ = await rig.login(OTHER)
            lawful = await rig.ask(ws, "panel.profile")                      # the player's own panel still works
            full = await rig.ask(ws, "gm.launch", mode="group", difficulty="easy")        # and so does not a well-formed request
            return welcome, answers, lawful, full, rig.bot.calls, rig.bot.sent, json.dumps(rig.bridge.gm.state(), sort_keys=True) == before, rig.bridge.gm.log.recent()

    welcome, answers, lawful, full, calls, sent, unchanged, log = run(scenario())
    assert welcome["perms"] == {"gm": False}
    assert set(answers) == set(handlers())
    assert {op: a.get("reason") for op, a in answers.items() if a["t"] != "rpc_err" or a.get("reason") != NOT_GM} == {}
    assert lawful["t"] == "rpc_ok" and full["t"] == "rpc_err" and full["reason"] == NOT_GM
    assert calls == [] and sent == [] and unchanged and log == []


def test_a_game_master_is_one_only_while_the_bot_says_so():
    async def scenario():
        async with GmRig() as rig:
            ws, welcome = await rig.login(ME)
            allowed = await rig.ask(ws, "gm.state")
            rig.admins.discard(ME)                                     # the role is taken away while the panel is open
            refused = await rig.ask(ws, "gm.state")
            refused_write = await rig.ask(ws, "gm.hp", id=str(OTHER), current=1)
            hp_after = rig.app.player_hp[OTHER]["current"]
            late, late_welcome = await rig.login(ME)
            rig.admins.add(ME)
            back = await rig.ask(late, "gm.state")
            return welcome, allowed, refused, refused_write, hp_after, late_welcome, back

    welcome, allowed, refused, refused_write, hp_after, late_welcome, back = run(scenario())
    assert welcome["perms"] == {"gm": True} and allowed["t"] == "rpc_ok" and allowed["data"]["fight"] is False
    assert refused["reason"] == NOT_GM and refused_write["reason"] == NOT_GM and hp_after == 100
    assert late_welcome["perms"] == {"gm": False} and back["t"] == "rpc_ok"


def test_a_test_window_on_this_pc_gets_the_panel_only_if_it_asks_and_discord_users_cannot_ask():
    async def scenario():
        async with GmRig() as rig:
            plain_ws, plain = await rig.dev("Ana")
            gm_ws, gm = await rig.dev("Gus", gm=True)
            asked_no = await rig.ask(plain_ws, "gm.state")
            asked_yes = await rig.ask(gm_ws, "gm.state")
            rig.fake.add_oauth_user("c222", OTHER, "Mina")             # a Discord user who adds the flag to their hello
            async with rig.http.post(f"http://127.0.0.1:{rig.port}/api/token", json={"code": "c222"}) as r:
                token = (await r.json())["access_token"]
            cheat = await rig.http.ws_connect(f"http://127.0.0.1:{rig.port}/ws")
            await cheat.send_json({"t": "hello", "token": token, "gm": True, "dev": ""})
            cheated = await cheat.receive_json()
            return plain, gm, asked_no, asked_yes, cheated, await rig.ask(cheat, "gm.state")

    plain, gm, asked_no, asked_yes, cheated, cheat_ask = run(scenario())
    assert plain["perms"] == {"gm": False} and gm["perms"] == {"gm": True}
    assert asked_no["reason"] == NOT_GM and asked_yes["t"] == "rpc_ok"
    assert cheated["perms"] == {"gm": False} and cheat_ask["reason"] == NOT_GM


# ---- using it ----------------------------------------------------------------------------------------------------------------------
def test_every_request_is_wired_to_something_that_answers_without_falling_over():
    async def scenario():
        async with GmRig() as rig:
            return await rig.ask_all(handlers())

    answers = run(scenario())
    assert set(answers) == set(handlers())
    broken = {op: a.get("reason") for op, a in answers.items() if a["t"] == "rpc_err" and a["reason"] in (GENERIC_FAILURE, NOT_GM)}
    assert broken == {}                                                  # a refusal says why; an exception would show up as the generic failure


def test_a_game_master_runs_the_event_over_the_socket_and_the_changes_are_kept_and_signed():
    async def scenario():
        async with GmRig() as rig:
            ws, _ = await rig.login(ME)
            started = await rig.ask(ws, "gm.launch", mode="single", difficulty="hard", target=str(OTHER))
            await asyncio.sleep(0.05)
            players = await rig.ask(ws, "gm.players")
            detail = await rig.ask(ws, "gm.player", id=str(OTHER))
            hp = await rig.ask(ws, "gm.hp", id=str(OTHER), current=40, max=120)
            value = await rig.ask(ws, "gm.value_set", key="black_flash_cap", value=35)
            qte = await rig.ask(ws, "gm.qte_set", difficulty="easy", evade=5, parryStart=3, parryEnd=6, perfect=4.5, timeout=7, damageMin=2, damageMax=4)
            too_big = await rig.ask(ws, "gm.hp", id=str(OTHER), current=5000)
            registered = await rig.ask(ws, "gm.boss_register", name="Rey", hp=500, image="https://cdn.discordapp.com/boss.png")
            history = await rig.ask(ws, "gm.history")
            saved = json.loads((rig.base / "gm_values.json").read_text(encoding="utf-8"))
            lines = (rig.base / "gm_log.jsonl").read_text(encoding="utf-8").count("\n")
            return rig, started, players, detail, hp, value, qte, too_big, registered, history, saved, lines

    rig, started, players, detail, hp, value, qte, too_big, registered, history, saved, lines = run(scenario())
    assert started["t"] == "rpc_ok" and [c[0] for c in rig.bot.calls][:1] == ["trigger_single_qte"] and rig.bot.calls[0][2]["target_member"].id == OTHER
    rows = {r["id"]: r for r in players["data"]["players"]}
    assert rows[str(ME)]["name"] == "Ana" and rows[str(ME)]["online"] is True and rows[str(OTHER)]["name"] == "Mina" and rows[str(OTHER)]["online"] is False
    assert rows[str(OTHER)]["avatar"].endswith("222/a.png")
    assert detail["data"]["row"]["id"] == str(OTHER) and detail["data"]["catalog"]["achievements"] and {"inventory", "profile", "skills", "titles"} <= set(detail["data"])
    assert hp["data"]["row"]["hp"]["current"] == 40 and hp["data"]["row"]["hp"]["max"] == 120 and rig.app.player_hp[OTHER]["max"] == 120
    items = {i["key"]: i for g in value["data"]["groups"] for i in g["items"]}
    assert items["black_flash_cap"]["value"] == 35.0 and rig.app.black_flash_cap == 0.35 and saved["black_flash_cap"] == 35.0
    assert qte["data"]["qte"]["easy"] == {"evade": 5.0, "parryStart": 3.0, "parryEnd": 6.0, "perfect": 4.5, "timeout": 7.0, "damageMin": 2, "damageMax": 4}
    assert saved["qte_timeout_durations"]["easy"] == 7.0 and ("save_qte", (), {}) in rig.bot.calls
    assert too_big["t"] == "rpc_err" and "va de 1 a 120" in too_big["reason"] and rig.app.player_hp[OTHER]["current"] == 40          # refused: nothing moved
    assert registered["data"]["active"]["name"] == "Rey" and rig.app.fight_active and rig.bot.sent and "embed" in rig.bot.sent[0]
    who = {e["who"] for e in history["data"]["entries"]}
    assert who == {"Ana"} and history["data"]["entries"][0]["action"].startswith("Registró al jefe") and len(history["data"]["entries"]) == 5
    assert lines == 5                                                    # every change is also written to the file, one line each


def test_content_files_are_checked_backed_up_and_loaded_into_the_running_bot_over_the_socket():
    async def scenario():
        async with GmRig() as rig:
            ws, _ = await rig.login(ME)
            data = await rig.ask(ws, "gm.data")
            current = await rig.ask(ws, "gm.file_get", key="achievements")
            broken = await rig.ask(ws, "gm.file_save", key="achievements", text="{ not json")
            wrong = await rig.ask(ws, "gm.file_save", key="achievements", text=json.dumps({"achievements": {"x": {"name": ""}}}))
            file_after_refusals = (rig.base / "data" / "achievements" / "achievements_config.json").read_text(encoding="utf-8")
            config = json.loads(current["data"]["text"])
            config["achievements"]["socket_test"] = {"name": "Prueba", "description": "Hecha desde el panel", "category": next(iter(config["categories"])), "icon": "🧪",
                                                    "trigger": "manual", "reward": {}}
            saved = await rig.ask(ws, "gm.file_save", key="achievements", text=json.dumps(config))
            listed = await rig.ask(ws, "gm.achievements")
            backups = [f.name for f in (rig.base / "data" / "backups").glob("*-achievements_config.*.json")]
            return rig, data, current, broken, wrong, file_after_refusals, saved, listed, backups

    rig, data, current, broken, wrong, file_after_refusals, saved, listed, backups = run(scenario())
    keys = [f["key"] for f in data["data"]["files"]]
    assert "achievements" in keys and "i18n" in keys and any(k.startswith("tree:") for k in keys) and data["data"]["templates"]
    assert broken["t"] == "rpc_err" and "JSON no es válido" in broken["reason"] and wrong["t"] == "rpc_err" and "necesita un nombre" in wrong["reason"]
    assert file_after_refusals == current["data"]["text"]                                      # refused: the file is untouched
    assert saved["t"] == "rpc_ok" and saved["data"]["warnings"] == [] and "socket_test" in rig.app.achievements_config["achievements"]
    assert any(a["id"] == "socket_test" and a["name"] == "Prueba" for a in listed["data"]["achievements"])
    assert len(backups) == 1                                                                    # the old file was kept first


def test_the_numbers_a_game_master_set_come_back_when_the_bot_starts_again():
    async def scenario():
        async with GmRig() as rig:
            ws, _ = await rig.login(ME)
            await rig.ask(ws, "gm.value_set", key="black_flash_cap", value=35)
            await rig.ask(ws, "gm.value_set", key="save_limit", value=7)
            await rig.ask(ws, "gm.qte_mode", mode="direction", weights={"combo": 40})
            rig.app.black_flash_cap, rig.app.save_limit, rig.app.current_qte_mode = 0.2, 2, "standard"       # the bot restarts with its own defaults
            rig.app.qte_variations["combo"]["weight"] = 15
            again = ActivityBridge(Hub(), rig.app, values_file=rig.base / "gm_values.json")
            again.start()
            again.stop()
            return rig.app.black_flash_cap, rig.app.save_limit, rig.app.current_qte_mode, rig.app.qte_variations["combo"]["weight"]

    assert run(scenario()) == (0.35, 7, "direction", 40)
