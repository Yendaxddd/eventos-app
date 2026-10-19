"""The Activity as a place to play: writing in the channel and answering QTEs with buttons."""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import ActivityBridge, ActivityServer, DiscordAuth, Hub  # noqa: E402
from eventos_app.activity.qte import ActivityInput, QteBook, describe, response_seconds  # noqa: E402
from fake_discord import FakeDiscord  # noqa: E402

TIMES = {"easy": {"evade_window": 6.0, "parry_window": (4.0, 7.0)}}


def run(coro):
    return asyncio.run(coro)


async def frame(ws, want=None, timeout=2.0):
    """The next frame of kind `want` (or any that is not the frequent who-is-online update)."""
    while True:
        got = await asyncio.wait_for(ws.receive_json(), timeout)
        if (want and got["t"] == want) or (not want and got["t"] != "users"):
            return got


# ---- the pieces ---------------------------------------------------------------------------------------------------
def test_the_qte_book_is_a_plain_dict_that_says_when_a_qte_starts_and_ends():
    seen = []
    book = QteBook()
    book.on_start = lambda k, v: seen.append(("start", k))
    book.on_end = lambda k, v: seen.append(("end", k))
    book[1] = {"mode": "single"}
    book[1]["message"] = "x"              # changing the inside is not a new QTE
    book[1] = {"mode": "single", "again": True}
    book.pop(2, None)                      # nothing to end
    book.pop(1, None)
    book[3] = {}
    del book[3]
    assert seen == [("start", 1), ("end", 1), ("start", 3), ("end", 3)] and 1 not in book

    def broken(*_):
        raise RuntimeError("listener bug")

    book.on_start = broken
    book[9] = {}                           # the game goes on
    assert 9 in book


def test_the_client_clock_is_trusted_only_within_what_a_human_and_the_real_time_allow():
    assert response_seconds(1000, 100, 5000) == 1.05                # dt + half the round trip
    assert response_seconds(50, 0, 5000) is None                    # nobody is that fast
    assert response_seconds(float("nan"), 0, 5000) is None and response_seconds(999999, 0, 5000) is None
    assert abs(response_seconds(4000, 0, 2000) - 2.15) < 1e-9       # cannot have taken longer than it has been
    assert response_seconds(500, 10_000_000, 60_000) == (500 + 2500) / 1000   # the round trip counts at most 5 s


def test_a_qte_is_described_without_leaking_its_windows():
    target = NS(id=5, display_name="Ana", name="ana")
    out = describe(7, {"difficulty": "easy", "mode": "single", "target": target, "participants": {}}, TIMES, 123.0)
    assert out["id"] == "7" and out["target"] == {"id": "5", "name": "Ana"} and out["timeout"] == 7.0
    assert out["tGo"] == 123.0 and out["commands"] == ["evade", "parry", "save", "adapt"]
    assert "parry_window" not in str(out) and "evade_window" not in str(out)
    group = describe(8, {"difficulty": "easy", "mode": "group", "target": None, "participants": {1: {}, 2: {}}}, TIMES, 1)
    assert group["target"] is None and group["participants"] == ["1", "2"]


def test_a_button_press_reads_like_a_chat_message_and_keeps_the_verdict_reaction():
    async def scenario():
        echoed = []
        qte_message = NS(add_reaction=lambda e: echoed.append(e) or asyncio.sleep(0))
        press = ActivityInput(NS(id=1), NS(guild="g"), "*evade*", user_id=1)
        press.mirror_to = qte_message
        await press.add_reaction("✅")
        return press, echoed

    press, echoed = run(scenario())
    assert press.content == "*evade*" and press.activity_user_id == 1 and press.guild == "g"
    assert press.reactions == ["✅"] and echoed == ["✅"] and press.created_at.tzinfo is not None


# ---- the whole path: client -> server -> bridge -> bot --------------------------------------------------------------
class Rig:
    def __init__(self, *, lanes: bool = True):
        self.fake = FakeDiscord()
        self.hub = Hub()
        self.calls, self.on_message_calls, self.posted, self.channel_sends, self.only = [], [], [], [], []
        self.lanes = lanes
        self.verdict = "✅"
        self.characters = {111: ["Kuro", "Shiro"]}

    async def __aenter__(self):
        await self.fake.start()
        member = NS(id=111, display_name="Ana", display_avatar=NS(url="https://cdn/ana.png"))
        rig = self

        async def send(content, **kwargs):
            rig.channel_sends.append((content, kwargs))

        self.channel = NS(id=10, name="qte", guild=NS(), send=send, permissions_for=lambda m: NS(view_channel=True, read_message_history=True))

        async def handle(message, measured=None, only=None):
            rig.calls.append((message.content, measured, message.activity_user_id))
            rig.only.append(only)
            await message.add_reaction(rig.verdict)

        async def on_message(message):
            rig.on_message_calls.append((message.content, message.author.id))

        self.app = NS(bot=NS(add_listener=lambda f, n: None, remove_listener=lambda f, n: None,
                             get_channel=lambda c: self.channel if c == 10 else None, on_message=on_message),
                      qte_channel_id=10, own_webhook_ids=set(), qte_times=TIMES, active_qtes=QteBook(),
                      resolve_event_guild=lambda: NS(get_member=lambda uid: member if uid == 111 else None),
                      get_user_characters=lambda uid: rig.characters.get(uid, []), handle_qte_response=handle)

        async def send_as(channel_id, *, content, username, avatar_url=None):
            if not rig.lanes:
                return None
            rig.posted.append((channel_id, content, username, avatar_url))
            return {"id": "1"}

        self.bridge = ActivityBridge(self.hub, self.app, pool=lambda: NS(send_as=send_as))
        self.bridge.start()
        self.auth = DiscordAuth(client_id=42, client_secret="s", api_base=f"http://127.0.0.1:{self.fake.port}/api/v10")
        self.server = ActivityServer(self.hub, auth=self.auth, authorize=self.bridge.authorize, web_dir=Path("/nonexistent"),
                                     client_id=42, port=0, actions=self.bridge)
        self.port = await self.server.start()
        self.http = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc):
        await self.http.close()
        await self.server.stop()
        await self.auth.close()
        await self.fake.stop()

    async def login(self, user_id=111):
        self.fake.add_oauth_user(f"c{user_id}", user_id, "Ana")
        async with self.http.post(f"http://127.0.0.1:{self.port}/api/token", json={"code": f"c{user_id}"}) as r:
            token = (await r.json())["access_token"]
        ws = await self.http.ws_connect(f"http://127.0.0.1:{self.port}/ws")
        await ws.send_json({"t": "hello", "token": token})
        return ws, await ws.receive_json()

    def start_qte(self, qte_id=7, target=None):
        self.app.active_qtes[qte_id] = {"difficulty": "easy", "mode": "single", "target": target or NS(id=111, display_name="Ana", name="ana"),
                                        "participants": {}, "responses": set(), "message": None}


def test_a_player_hears_about_a_qte_when_it_starts_and_when_it_ends_even_if_already_running():
    async def scenario():
        async with Rig() as rig:
            ws, welcome = await rig.login()
            rig.start_qte()
            started = await frame(ws, "qte")
            rig.app.active_qtes.pop(7, None)
            ended = await frame(ws, "qte_end")
            rig.start_qte(8)
            await asyncio.sleep(0.05)
            late, late_welcome = await rig.login()
            return welcome, started, ended, late_welcome

    welcome, started, ended, late = run(scenario())
    assert welcome["qtes"] == [] and welcome["characters"] == ["Kuro", "Shiro"] and welcome["canWrite"]
    assert started["q"]["id"] == "7" and started["q"]["target"]["id"] == "111" and started["q"]["difficulty"] == "easy"
    assert ended == {"t": "qte_end", "id": "7"}
    assert [q["id"] for q in late["qtes"]] == ["8"]                # whoever comes in late still sees it


def test_a_button_press_is_timed_by_the_players_screen_and_reaches_the_bots_handler():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            await ws.send_json({"t": "sync", "rtt": 100.0, "offset": 0.0})
            rig.start_qte()
            q = (await frame(ws, "qte"))["q"]
            await asyncio.sleep(0.4)
            await ws.send_json({"t": "press", "id": q["id"], "command": "evade", "dt": 300})
            result = await frame(ws, "qte_result")
            await ws.send_json({"t": "press", "id": q["id"], "command": "parry", "dt": 10})        # not human
            refused = await frame(ws, "error")
            return rig.calls, result, refused

    calls, result, refused = run(scenario())
    assert calls == [("*evade*", 0.35, 111)]                         # 300 ms on screen + half the 100 ms round trip
    assert result["ok"] is True and result["ms"] == 350 and result["reactions"] == ["✅"]
    assert refused["code"] == "press" and "creíble" in refused["reason"]


def test_a_failed_press_shows_the_cross_and_a_dead_qte_or_unknown_button_is_explained():
    async def scenario():
        async with Rig() as rig:
            rig.verdict = "❌"
            ws, _ = await rig.login()
            rig.start_qte()
            q = (await frame(ws, "qte"))["q"]
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "press", "id": q["id"], "command": "evade", "dt": 150})
            failed = await frame(ws, "qte_result")
            await ws.send_json({"t": "press", "id": "999", "command": "evade", "dt": 500})
            gone = await frame(ws, "error")
            await ws.send_json({"t": "press", "id": q["id"], "command": "explode", "dt": 500})
            unknown = await frame(ws, "error")
            return failed, gone, unknown

    failed, gone, unknown = run(scenario())
    assert failed["ok"] is False and "terminó" in gone["reason"] and "desconocido" in unknown["reason"]


def test_a_claimed_time_longer_than_the_qte_has_lasted_is_trimmed_to_the_real_time():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            rig.start_qte()
            q = (await frame(ws, "qte"))["q"]
            await asyncio.sleep(0.3)
            await ws.send_json({"t": "press", "id": q["id"], "command": "evade", "dt": 100000})   # "I waited 100 s"
            await frame(ws, "qte_result")
            return rig.calls[0][1]

    assert run(scenario()) < 1.0


def test_adapt_and_attack_go_through_the_bots_normal_message_handler():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            await ws.send_json({"t": "press", "id": "", "command": "attack"})
            await frame(ws, "qte_result")
            await ws.send_json({"t": "press", "id": "", "command": "adapt"})
            await frame(ws, "qte_result")
            return rig.on_message_calls, rig.calls

    on_message, calls = run(scenario())
    assert on_message == [("*attack*", 111), ("*adapt*", 111)] and calls == []


# ---- writing --------------------------------------------------------------------------------------------------------------
def test_what_a_player_writes_appears_under_their_name_or_one_of_their_characters_and_the_bot_hears_it():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            await ws.send_json({"t": "say", "text": "hola a todos"})
            await asyncio.sleep(0.5)
            await ws.send_json({"t": "say", "text": "*attack* ahora", "as": "Kuro"})
            await asyncio.sleep(0.2)
            return rig.posted, rig.on_message_calls

    posted, on_message = run(scenario())
    assert posted == [(10, "hola a todos", "Ana", "https://cdn/ana.png"), (10, "*attack* ahora", "Kuro", "https://cdn/ana.png")]
    assert on_message == [("hola a todos", 111), ("*attack* ahora", 111)]


def test_a_character_picture_seen_in_the_channel_is_used_and_other_peoples_characters_are_refused():
    async def scenario():
        async with Rig() as rig:
            rig.bridge.avatars["Kuro"] = "https://cdn/kuro.png"
            ws, _ = await rig.login()
            await ws.send_json({"t": "say", "text": "yo", "as": "Kuro"})
            await asyncio.sleep(0.5)
            await ws.send_json({"t": "say", "text": "soy otro", "as": "Gojo"})
            refused = await frame(ws, "error")
            return rig.posted, refused

    posted, refused = run(scenario())
    assert posted == [(10, "yo", "Kuro", "https://cdn/kuro.png")] and "no es tuyo" in refused["reason"]


def test_without_a_webhook_lane_the_bot_says_it_for_them_and_nobody_is_pinged():
    async def scenario():
        async with Rig(lanes=False) as rig:
            ws, _ = await rig.login()
            await ws.send_json({"t": "say", "text": "hola @everyone"})
            await asyncio.sleep(0.2)
            return rig.channel_sends

    (content, kwargs), = run(scenario())
    assert content == "**Ana:** hola @everyone" and kwargs["allowed_mentions"].everyone is False


def test_a_typed_answer_is_timed_from_the_start_of_the_qte_and_empty_long_or_fast_messages_are_refused():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            rig.start_qte()
            await frame(ws, "qte")
            await asyncio.sleep(0.3)
            await ws.send_json({"t": "say", "text": "*evade*"})
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "say", "text": "   "})              # nothing to send: nothing happens
            await ws.send_json({"t": "say", "text": "x" * 2001})
            long = await frame(ws, "error")
            await ws.send_json({"t": "say", "text": "uno"})
            await ws.send_json({"t": "say", "text": "dos"})              # right after: too fast
            fast = await frame(ws, "error")
            return rig.calls, long, fast

    calls, long, fast = run(scenario())
    assert calls[0][0] == "*evade*" and 0.2 < calls[0][1] < 1.5
    assert "2000" in long["reason"] and "rápido" in fast["reason"]


# ---- characters --------------------------------------------------------------------------------------------------------
def test_a_command_acts_as_the_chosen_character_and_only_one_of_the_players_own():
    from eventos_app.activity.qte import CharacterAuthor

    async def scenario():
        async with Rig() as rig:
            seen = []

            async def on_message(message):
                seen.append((message.content, message.author.display_name, message.author.id))

            rig.app.bot.on_message = on_message
            ws, _ = await rig.login()
            await ws.send_json({"t": "press", "id": "", "command": "adapt", "as": "Kuro"})
            await frame(ws, "qte_result")
            await ws.send_json({"t": "press", "id": "", "command": "attack"})                      # as themselves
            await frame(ws, "qte_result")
            await ws.send_json({"t": "press", "id": "", "command": "attack", "as": "Gojo"})        # not theirs
            refused = await frame(ws, "error")
            await ws.send_json({"t": "say", "text": "*power1*", "as": "Shiro"})
            await asyncio.sleep(0.3)
            return seen, refused

    seen, refused = run(scenario())
    assert seen == [("*adapt*", "Kuro", 111), ("*attack*", "Ana", 111), ("*power1*", "Shiro", 111)]
    assert "no es tuyo" in refused["reason"]
    member = NS(id=5, display_name="Ana", mention="<@5>")
    author = CharacterAuthor(member, "Kuro")
    assert author.display_name == "Kuro" and author.id == 5 and author.mention == "<@5>" and author == member


def test_the_pictures_of_characters_are_remembered_between_runs(tmp_path):
    file = tmp_path / "avatars.json"
    app = NS(own_webhook_ids=set(), bot=NS(), qte_channel_id=1)
    first = ActivityBridge(Hub(), app, avatar_file=file)
    from datetime import datetime, timezone

    message = NS(id=1, channel=NS(id=1), webhook_id=77, clean_content="hola", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                 edited_at=None, attachments=[], embeds=[],
                 author=NS(id=9, display_name="Kuro", name="kuro", bot=True, color=NS(value=0), display_avatar=NS(url="https://cdn/kuro.png")))
    first._frame(message)
    second = ActivityBridge(Hub(), app, avatar_file=file)           # a new run of the app
    assert second.avatars == {"Kuro": "https://cdn/kuro.png"}


# ---- the bar's windows and the game state -----------------------------------------------------------------------------------
def test_the_bar_gets_the_windows_of_this_player_the_real_timeout_and_a_fake_qte_does_not_say_who_it_is_for():
    times = {"hard": {"evade_window": 4.0, "parry_window": (2.5, 4.5), "perfect_parry": 3.5}}
    target = NS(id=5, display_name="Ana", name="ana")
    data = {"difficulty": "hard", "mode": "single", "target": target, "participants": {}}
    plain = describe(1, data, times, 0.0, timeouts={"hard": 5.75}, bf_window=0.2)
    assert plain["timeout"] == 5.75 and plain["windows"] == {"evade": [0.0, 4.0], "parry": [2.5, 4.5], "bf": [3.3, 3.7]}
    revenge = describe(1, data, times, 0.0, timeouts={"hard": 5.75}, bf_window=0.2, adjust=lambda d, u: (2.0, 3.0) if u == 5 else (2.5, 4.5))
    assert revenge["windows"]["parry"] == [2.0, 3.0] and revenge["windows"]["bf"] == [2.3, 2.7]
    no_timeouts = describe(1, data, times, 0.0)
    assert no_timeouts["timeout"] == 4.5 and no_timeouts["windows"]["bf"] is None
    combo = describe(2, {**data, "mode": "combo"}, times, 0.0)
    assert combo["windows"] is None and combo["mode"] == "combo"
    fake = describe(3, {**data, "mode": "fake"}, times, 0.0)
    assert fake["target"] is None and fake["participants"] == []


def test_the_game_state_is_sent_when_it_changes_and_only_to_the_person_it_belongs_to():
    async def scenario():
        async with Rig() as rig:
            app = rig.app
            app.active_boss = {"name": "Sukuna", "hp_current": 700, "hp_max": 1000}
            app.fight_active = True
            app.qte_players = [NS(id=111, display_name="Ana", name="ana"), NS(id=222, display_name="Luis", name="luis")]
            app.player_hp = {111: {"current": 80, "max": 100, "revenge_mode": True}, 222: {"current": 40, "max": 100}}
            app.power_charges = {111: {"power1": 45.0, "power2": 100.0}, 222: {"power1": 7.0}}
            app.player_stats = {111: {"evade_streak": 3}}
            app.ultimate_cost = 100
            ws, welcome = await rig.login()
            await ws.send_json({"t": "ping", "c": 1})
            await frame(ws, "pong")
            app.active_boss["hp_current"] = 650
            app.player_stats[111]["evade_streak"] = 4
            await rig.bridge.push_state()
            state, me = await frame(ws, "state"), await frame(ws, "me")
            await rig.bridge.push_state()                             # nothing changed: nothing is sent
            await ws.send_json({"t": "ping", "c": 2})
            quiet = await frame(ws)
            return welcome, state, me, quiet

    welcome, state, me, quiet = run(scenario())
    assert welcome["state"]["boss"] == {"name": "Sukuna", "hp": 700, "max": 1000} and welcome["state"]["fight"]
    assert [p["name"] for p in welcome["state"]["players"]] == ["Ana", "Luis"] and welcome["state"]["players"][0]["revenge"]
    assert {k: welcome["me"][k] for k in ("charges", "cost", "streak")} == {"charges": {"power1": 45.0, "power2": 100.0}, "cost": 100, "streak": 3}
    assert state["s"]["boss"]["hp"] == 650 and me["me"]["streak"] == 4
    assert quiet["t"] == "pong"                                       # no repeated state frame


# ---- several QTEs, combos, directions, saves, powers and cooldowns ----------------------------------------------------------
def test_a_button_answers_exactly_the_qte_it_names_and_buttons_the_qte_does_not_offer_are_refused():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            rig.start_qte(7)
            rig.start_qte(8)
            first, second = (await frame(ws, "qte"))["q"], (await frame(ws, "qte"))["q"]
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "press", "id": second["id"], "command": "evade", "dt": 150})
            await frame(ws, "qte_result")
            await ws.send_json({"t": "press", "id": first["id"], "command": "left", "dt": 150})       # a direction pad on a plain QTE
            refused = await frame(ws, "error")
            return rig.only, refused

    only, refused = run(scenario())
    assert only == [8] and "no sirve" in refused["reason"]


def test_a_combo_shows_the_next_step_only_to_who_earned_it_and_a_save_goes_to_the_qte_of_somebody_else():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            steps = ["parry", "evade", "evade", "parry", "evade"]
            rig.app.active_qtes[3] = {"difficulty": "easy", "mode": "combo", "target": NS(id=111, display_name="Ana", name="ana"),
                                      "participants": {}, "responses": set(), "message": None, "combo_sequence": steps,
                                      "combo_index": 0, "combo_length": 5}
            opened = (await frame(ws, "qte"))["q"]
            handled = rig.app.handle_qte_response

            async def combo(message, measured=None, only=None):
                await handled(message, measured, only)
                rig.app.active_qtes[3]["combo_index"] += 1       # what the engine does for a right answer

            rig.app.handle_qte_response = combo
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "press", "id": "3", "command": "parry", "dt": 150})
            step = await frame(ws, "qte_step")
            # a QTE of somebody else: the save travels with the command `save`
            rig.app.handle_qte_response = handled
            rig.start_qte(4, target=NS(id=222, display_name="Luis", name="luis"))
            other = (await frame(ws, "qte"))["q"]
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "press", "id": "4", "command": "save", "dt": 150})
            await frame(ws, "qte_result")
            return opened, step, other, rig.calls

    opened, step, other, calls = run(scenario())
    assert opened["combo"] == {"length": 5, "index": 0, "step": "parry"} and opened["commands"] == ["evade", "parry"]
    assert step == {"t": "qte_step", "id": "3", "index": 1, "step": "evade"}
    assert other["commands"] == ["evade", "parry", "save", "adapt"] and calls[-1][0] == "*save*"


def test_a_direction_qte_is_described_with_its_arrow_and_a_bf_chain_with_only_the_parry():
    times = {"easy": {"evade_window": 6.0, "parry_window": (4.0, 7.0), "perfect_parry": 5.5, "timeout": 3.0}}
    target = NS(id=5, display_name="Ana", name="ana")
    arrow = describe(1, {"difficulty": "easy", "mode": "direction", "target": target, "shown_arrow": "⬆️"}, times, 0.0)
    assert arrow["arrow"] == "⬆️" and arrow["commands"] == ["up", "down", "left", "right"] and arrow["timeout"] == 4.0
    assert arrow["windows"] == {"evade": [0.0, 4.0], "bf": None}                     # the bot gives up after 4 s however wide the window is
    chain = describe(2, {"difficulty": "easy", "mode": "bf_chain", "target": target, "chain_level": 3}, times, 0.0, chain_window=0.15)
    assert chain["commands"] == ["parry"] and chain["timeout"] == 3.0 and chain["chain"] == 3
    assert chain["windows"]["parry"] == [4.0, 7.0] and chain["windows"]["bf"] == [5.35, 5.65]


def test_the_players_cooldowns_travel_as_moments_on_the_servers_clock_so_they_do_not_change_every_second():
    async def scenario():
        async with Rig() as rig:
            app, now = rig.app, time.time()
            app.save_time_window, app.save_limit = 60, 2
            app.save_timestamps = {111: [now - 50, now - 5, now - 120]}        # two recent saves: none left until the older expires
            app.player_parry_cooldown = {111: now + 12}
            app.counter_enabled_players, app.counter_deadlines = {111: 4}, {111: now + 3}
            app.fight_active = True
            app.character_powers = {"Kuro": {"power1": {"name": "Rayo"}, "power2": {"name": "Escudo"}}}
            app.power_cooldowns = {111: {"power2": now + 40}}
            app.player_achievements = {"111": {"domains": ["d1"]}}
            first = rig.bridge.me_of(111)
            await asyncio.sleep(0.05)
            second = rig.bridge.me_of(111)
            app.fight_active = False                                           # between fights the cooldown waits
            app.ultimate_fight_cooldowns = {111: {"power2": 25}}
            paused = rig.bridge.me_of(111)
            return first, second, paused, now

    first, second, paused, now = run(scenario())
    assert first == second                                                     # nothing to resend while time merely passes
    assert first["saves"]["left"] == 0 and abs(first["saves"]["until"] - (now - 50 + 60) * 1000) < 2
    assert first["parryUntil"] and first["counterUntil"] and first["domain"] is True
    assert first["powers"]["Kuro"]["power1"] == {"name": "Rayo", "until": None, "paused": None}
    assert first["powers"]["Kuro"]["power2"]["until"] and first["powers"]["Kuro"]["power2"]["paused"] is None
    assert paused["powers"]["Kuro"]["power2"] == {"name": "Escudo", "until": None, "paused": 25}


def test_a_combos_first_step_is_known_even_though_the_bot_fills_the_sequence_in_after_creating_the_qte():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.login()
            data = {"difficulty": "easy", "mode": "combo", "target": NS(id=111, display_name="Ana", name="ana"), "participants": {},
                    "responses": set(), "message": None, "combo_sequence": [], "combo_index": 0, "combo_length": 5}
            rig.app.active_qtes[3] = data
            data["combo_sequence"] = ["evade", "parry", "parry", "evade", "evade"]      # as trigger_combo_qte does, right after
            opened = (await frame(ws, "qte"))["q"]
            data2 = {**data, "combo_sequence": []}
            rig.app.active_qtes[4] = data2
            rig.app.active_qtes.pop(4)                                                    # answered/ended before the frame went out
            await asyncio.sleep(0.1)
            return opened, list(rig.hub.qtes)

    opened, running = run(scenario())
    assert opened["combo"]["step"] == "evade" and running == ["3"]
