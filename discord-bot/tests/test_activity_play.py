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
    assert out["tGo"] == 123.0 and out["commands"] == ["evade", "parry", "adapt"]
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
        self.calls, self.on_message_calls, self.posted, self.channel_sends = [], [], [], []
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

        async def handle(message, measured=None):
            rig.calls.append((message.content, measured, message.activity_user_id))
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
