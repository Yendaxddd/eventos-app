"""The sender pool, run against a fake Discord REST API (see fake_discord.py) using discord.py's real
HTTP client, so routing, ownership, pacing and fallbacks are exercised for real."""
import asyncio
import io
import sys
import time
from pathlib import Path

import aiohttp
import discord
from discord.http import MultipartParameters

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app import multibot  # noqa: E402
from fake_discord import FakeDiscord  # noqa: E402

CHANNEL = 555
LIMIT, WINDOW = 5, 1.0       # the fake server's real limit: 5 messages per second per bot per channel
POOL_WINDOW = WINDOW * 1.06  # the pool plans with a little margin, like multibot.WINDOW_SECONDS
REACTION_WINDOW = 0.25
SPACING = 0.27               # multibot.REACTION_SPACING


def make_pool(**kwargs):
    return multibot.SenderPool(limit=LIMIT, window=POOL_WINDOW, reaction_spacing=SPACING, **kwargs)


class World:
    """A fake server, a primary bot (HTTP only) and `helpers` helper tokens."""

    def __init__(self, helpers: int, latency: float = 0.02, **server_options) -> None:
        options = {"reaction_window": REACTION_WINDOW, **server_options}
        self.server = FakeDiscord(limit=LIMIT, window=WINDOW, latency=latency, **options)
        self.server.add_bot("tok-primary", 100)
        self.helper_tokens = []
        for i in range(helpers):
            token = f"tok-h{i}"
            self.server.add_bot(token, 101 + i)
            self.helper_tokens.append(token)
        self.pool = make_pool()

    async def __aenter__(self):
        await self.server.start()
        self.primary = discord.Client(intents=discord.Intents.none())
        await self.primary.login("tok-primary")
        self.channel = discord.PartialMessageable(state=self.primary._connection, id=CHANNEL)
        self.pool.install(self.primary.http, str(self.primary.user), self.primary.user.id)
        for token in self.helper_tokens:
            await self.pool.add_helper(token)
        return self

    async def __aexit__(self, *exc):
        await self.pool.close()
        await self.primary.close()
        await self.server.stop()

    def count_by(self, token: str) -> int:
        return len(self.server.sent_by(token))


def run(coro):
    return asyncio.run(coro)


async def burst(world: World, n: int) -> float:
    started = time.monotonic()
    await asyncio.gather(*(world.channel.send(f"qte {i}") for i in range(n)))
    return time.monotonic() - started


# ---- sending ---------------------------------------------------------------------------------
def test_helpers_remove_the_rate_limit_wait():
    async def scenario():
        async with World(helpers=0) as alone:
            t_alone = await burst(alone, 12)
        async with World(helpers=2) as trio:
            t_trio = await burst(trio, 12)
            counts = [trio.count_by(t) for t in ("tok-primary", "tok-h0", "tok-h1")]
        return t_alone, t_trio, counts

    t_alone, t_trio, counts = run(scenario())
    # one bot: 12 messages at 5 per window need 3 windows; three bots: 4 each, all inside the limit
    assert t_alone > 1.8, t_alone
    assert t_trio < 0.5 * WINDOW, t_trio
    assert counts == [4, 4, 4]


def test_load_is_spread_evenly_and_never_exceeds_the_limit():
    async def scenario():
        async with World(helpers=3) as w:
            elapsed = await burst(w, 16)
            per_bot = {t: w.count_by(t) for t in ["tok-primary"] + w.helper_tokens}
            rate_limited = [r for r in w.server.requests if r["status"] == 429]
            return elapsed, per_bot, rate_limited

    elapsed, per_bot, rate_limited = run(scenario())
    assert sorted(per_bot.values()) == [4, 4, 4, 4]
    assert rate_limited == []  # the pool never pushed a bot past its limit
    assert elapsed < 0.5 * WINDOW


def test_sends_of_one_bot_run_in_parallel_without_a_window_stall():
    # discord.py would serialise these and make the last ones wait for the window to reset; with the
    # open buckets all five go out together and each returns after about one round trip
    async def scenario():
        async with World(helpers=0, latency=0.1) as w:
            started = time.monotonic()
            finished = []

            async def one(i):
                await w.channel.send(f"m{i}")
                finished.append(time.monotonic() - started)

            await asyncio.gather(*(one(i) for i in range(5)))
            return sorted(finished), max(w.server.max_in_flight.values())

    finished, in_flight = run(scenario())
    assert in_flight >= 4  # really overlapping on the wire
    assert finished[-1] < 0.5, finished  # ~1 RTT (0.1 s), not 5 in a row and not a window (1 s)


def test_a_burst_bigger_than_all_windows_still_delivers_everything():
    async def scenario():
        async with World(helpers=1) as w:
            elapsed = await burst(w, 25)  # 2 bots x 5 per window
            return elapsed, len(w.server.messages), [r for r in w.server.requests if r["status"] == 429]

    elapsed, delivered, rate_limited = run(scenario())
    assert delivered == 25
    assert rate_limited == []  # waited for free slots instead of being refused
    assert elapsed < 5.0  # about three windows, not 25 serialised sends


def test_edit_and_delete_go_to_the_bot_that_wrote_the_message():
    async def scenario():
        async with World(helpers=2) as w:
            messages = await asyncio.gather(*(w.channel.send(f"m{i}") for i in range(9)))
            await asyncio.gather(*(m.edit(content=f"edited {m.id}") for m in messages))
            editors = {m.id: w.server.messages[m.id]["edited_by"] for m in messages}
            authors = {m.id: w.server.messages[m.id]["author_token"] for m in messages}
            await asyncio.gather(*(m.delete() for m in messages))
            return editors, authors, len(w.server.messages)

    editors, authors, left = run(scenario())
    assert editors == authors  # every edit reached its author (the fake rejects anyone else)
    assert len(set(authors.values())) == 3  # and the messages really were spread over three bots
    assert left == 0


def test_a_helper_without_access_is_skipped_and_the_message_still_arrives():
    async def scenario():
        async with World(helpers=2) as w:
            w.server.deny("tok-h0", CHANNEL)
            await burst(w, 12)
            first = sum(1 for r in w.server.requests if r["token"] == "tok-h0")
            delivered = len(w.server.messages)
            await burst(w, 12)  # h0 is now known to be useless here: nobody should try it again
            second = sum(1 for r in w.server.requests if r["token"] == "tok-h0")
            blocked = [s["blocked_channels"] for s in w.pool.snapshot() if s["name"].endswith("101")]
            return first, second, delivered, len(w.server.messages), blocked

    first, second, delivered, total, blocked = run(scenario())
    assert delivered == 12 and total == 24  # nothing lost
    assert first <= LIMIT  # at most its share of the very first burst, before the first 403 came back
    assert second == first
    assert blocked == [1]


def test_checking_access_up_front_spares_the_first_burst():
    async def scenario():
        async with World(helpers=2) as w:
            w.server.deny("tok-h0", CHANNEL)
            await w.pool.check_access(CHANNEL)
            access = {s["name"]: s["access"] for s in w.pool.snapshot()}
            await burst(w, 12)
            return access, sum(1 for r in w.server.requests if r["token"] == "tok-h0"), len(w.server.messages)

    access, h0_attempts, delivered = run(scenario())
    assert access["bot101"] == "no" and access["bot102"] == "ok"
    assert h0_attempts == 0 and delivered == 12


def test_messages_with_buttons_stay_on_the_primary():
    async def scenario():
        async with World(helpers=2) as w:
            params = MultipartParameters(
                payload={"content": "click me", "components": [{"type": 1, "components": []}]},
                multipart=None, files=None)
            for _ in range(6):
                await w.primary.http.send_message(CHANNEL, params=params)
            return w.count_by("tok-primary"), w.count_by("tok-h0"), w.count_by("tok-h1")

    assert run(scenario()) == (6, 0, 0)


def test_attachments_survive_falling_back_through_several_senders():
    async def scenario():
        async with World(helpers=2) as w:
            w.server.deny("tok-h0", CHANNEL)
            w.server.deny("tok-h1", CHANNEL)
            w.pool.primary.penalty_until = time.monotonic() + 0.3  # make the helpers the first choices
            payload = b"gif-bytes-" * 5000
            await w.channel.send("domain!", file=discord.File(io.BytesIO(payload), filename="domain.gif"))
            (message,) = w.server.messages.values()
            return message["author_token"], message["files"], len(payload)

    author, files, size = run(scenario())
    assert author == "tok-primary"
    assert files == [{"name": "domain.gif", "size": size}]  # complete, not truncated by the retries


def test_an_unreachable_helper_does_not_lose_the_message():
    async def scenario():
        async with World(helpers=1) as w:
            helper = w.pool.helpers[0]

            async def down(*args, **kwargs):
                raise aiohttp.ClientConnectionError("network down")

            helper.endpoints = multibot.Endpoints(down, down, down, down, down, down)
            w.pool.primary.penalty_until = time.monotonic() + 0.3
            await w.channel.send("still delivered")
            return w.count_by("tok-primary")

    assert run(scenario()) == 1


# ---- reactions ---------------------------------------------------------------------------------
def test_reactions_are_spread_over_all_bots_and_stay_inside_their_limit():
    async def scenario():
        async with World(helpers=2) as w:
            (message,) = await asyncio.gather(w.channel.send("qte"))
            emojis = ["⭐", "❗", "✅", "❌", "🔒", "🪞", "💚", "🔥", "⚡", "🎯", "🛡️", "👍"]
            started = time.monotonic()
            await asyncio.gather(*(message.add_reaction(e) for e in emojis))
            elapsed = time.monotonic() - started
            per_bot = {t: sum(1 for r in w.server.reactions if r["token"] == t and r["status"] == 204)
                       for t in ["tok-primary"] + w.helper_tokens}
            return elapsed, per_bot, [r for r in w.server.reactions if r["status"] == 429]

    elapsed, per_bot, rate_limited = run(scenario())
    assert sorted(per_bot.values()) == [4, 4, 4]
    assert rate_limited == []
    # one bot would need 12 x 0.27 s = 3.2 s; three bots in parallel need about a third of that
    assert elapsed < 1.7, elapsed


def test_a_helper_that_cannot_react_falls_back_and_the_reaction_still_lands():
    async def scenario():
        async with World(helpers=1) as w:
            message = await w.channel.send("qte")
            w.server.deny("tok-h0", CHANNEL)
            w.pool.primary.penalty_until = time.monotonic() + 0.3  # helper is the first choice
            await message.add_reaction("⭐")
            return [(r["token"], r["status"]) for r in w.server.reactions]

    attempts = run(scenario())
    assert ("tok-h0", 403) in attempts and ("tok-primary", 204) in attempts


def test_reacting_to_a_deleted_message_raises_like_before():
    async def scenario():
        async with World(helpers=1) as w:
            message = await w.channel.send("qte")
            del w.server.messages[message.id]
            try:
                await message.add_reaction("⭐")
            except discord.NotFound:
                return True
            return False

    assert run(scenario())


# ---- the machinery -------------------------------------------------------------------------------
def test_message_reaction_and_ping_buckets_are_open_but_other_routes_keep_discordpys_own():
    async def scenario():
        async with World(helpers=0) as w:
            await w.channel.send("learn the bucket hash")
            get = w.primary.http.get_ratelimit
            return (get("POST /channels/{channel_id}/messages:555") is multibot._OPEN,
                    get("send-555-tok-primary:555") is multibot._OPEN,  # the hash Discord reported
                    get("GET /gateway:") is multibot._OPEN,
                    get("PATCH /channels/{channel_id}/messages/{message_id}:555") is multibot._OPEN)

    assert run(scenario()) == (True, True, True, False)


def test_without_get_ratelimit_it_falls_back_to_one_send_at_a_time(monkeypatch):
    monkeypatch.setattr(multibot, "can_open_buckets", lambda http: False)

    async def scenario():
        async with World(helpers=1) as w:
            await burst(w, 10)
            return max(w.server.max_in_flight.values()), len(w.server.messages)

    in_flight, delivered = run(scenario())
    assert in_flight == 1 and delivered == 10


def test_keepalive_pings_every_sender_with_several_connections(monkeypatch):
    monkeypatch.setattr(multibot, "WARM_INTERVAL", 0.05)

    async def scenario():
        async with World(helpers=1) as w:
            w.pool.start_background()
            await asyncio.sleep(0.4)
            return dict(w.server.gateway_hits), [s["pings"] for s in w.pool.snapshot()]

    hits, pings = run(scenario())
    assert hits.get("tok-primary", 0) >= multibot.WARM_CONNECTIONS and hits.get("tok-h0", 0) >= multibot.WARM_CONNECTIONS
    assert all(p >= multibot.WARM_CONNECTIONS for p in pings)


def test_a_sender_that_was_just_used_is_not_pinged():
    async def scenario():
        async with World(helpers=0) as w:
            await w.channel.send("busy")
            before = w.server.gateway_hits.get("tok-primary", 0)
            await w.pool.primary.warm()
            return w.server.gateway_hits.get("tok-primary", 0) - before

    assert run(scenario()) == 0


def test_latency_is_measured_per_sender():
    async def scenario():
        async with World(helpers=1, latency=0.05) as w:
            await burst(w, 8)
            return w.pool.snapshot()

    for sender in run(scenario()):
        assert sender["sent"] == 4 and 40 <= sender["p50_ms"] < 400 and sender["p95_ms"] >= sender["p50_ms"]


def test_who_wrote_the_hp_bar_messages_survives_a_restart(tmp_path):
    # HP bar embeds are edited all session long; after a restart the pool must still know which bot
    # wrote each one, or every first edit goes to the wrong bot and gets a 403
    async def scenario():
        async with World(helpers=2) as w:
            w.pool.sticky_channels = {CHANNEL}
            w.pool.owners_file = tmp_path / "owners.json"
            ids = [m.id for m in await asyncio.gather(*(w.channel.send(f"hp {i}") for i in range(9)))]
            w.pool.save_owners()

            # "restart": a new primary, a new pool, the same bots
            primary2 = discord.Client(intents=discord.Intents.none())
            await primary2.login("tok-primary")
            pool2 = make_pool()
            pool2.owners_file = tmp_path / "owners.json"
            pool2.install(primary2.http, "p", primary2.user.id)
            for token in w.helper_tokens:
                await pool2.add_helper(token)
            w.server.edit_attempts.clear()
            params = MultipartParameters(payload={"content": "edited"}, multipart=None, files=None)
            for mid in ids:
                await primary2.http.edit_message(CHANNEL, mid, params=params)
            await pool2.close()
            await primary2.close()
            return list(w.server.edit_attempts)

    attempts = run(scenario())
    assert len(attempts) == 9 and all(status == 200 for _, status in attempts)  # no wasted 403s


# ---- management ------------------------------------------------------------------------------------
def test_the_same_bot_cannot_be_added_twice_and_bad_tokens_are_rejected():
    async def scenario():
        async with World(helpers=1) as w:
            errors = []
            for token in ("tok-primary", "tok-h0", "not-a-token"):
                try:
                    await w.pool.add_helper(token)
                except (ValueError, discord.LoginFailure) as exc:
                    errors.append(type(exc).__name__)
            return errors, len(w.pool.helpers)

    errors, helpers = run(scenario())
    assert errors == ["ValueError", "ValueError", "LoginFailure"]
    assert helpers == 1


def test_uninstall_restores_the_original_http_methods():
    async def scenario():
        async with World(helpers=1) as w:
            routed = (w.primary.http.send_message, w.primary.http.add_reaction)
            w.pool.uninstall()
            restored = (w.primary.http.send_message, w.primary.http.add_reaction)
            await w.channel.send("direct")
            return routed != restored, w.count_by("tok-primary"), w.count_by("tok-h0"), "get_ratelimit" in vars(w.primary.http)

    changed, primary, helper, patched = run(scenario())
    assert changed and (primary, helper) == (1, 0) and not patched


def test_removing_a_helper_stops_using_it():
    async def scenario():
        async with World(helpers=1) as w:
            await burst(w, 6)
            await w.pool.remove_helper(w.pool.helpers[0])
            before = w.count_by("tok-h0")
            await burst(w, 6)
            return before, w.count_by("tok-h0"), len(w.pool.snapshot())

    before, after, senders = run(scenario())
    assert before == after and senders == 1


def test_test_send_posts_and_removes_a_message(monkeypatch):
    async def scenario():
        async with World(helpers=1) as w:
            real_sleep = asyncio.sleep
            monkeypatch.setattr(asyncio, "sleep", lambda s: real_sleep(0))
            problem = await w.pool.test_send(w.pool.helpers[0], CHANNEL)
            w.server.deny("tok-h0", CHANNEL)
            denied = await w.pool.test_send(w.pool.helpers[0], CHANNEL)
            return problem, denied, len(w.server.messages)

    problem, denied, left = run(scenario())
    assert problem == "" and left == 0
    assert "permiso" in denied or "Missing" in denied


def test_invite_link_asks_for_the_permissions_the_helper_needs():
    url = multibot.invite_url(123)
    assert "client_id=123" in url and "scope=bot" in url
    perms = discord.Permissions(int(url.split("permissions=")[1].split("&")[0]))
    assert perms.send_messages and perms.embed_links and perms.attach_files and perms.read_message_history
    assert perms.add_reactions
    assert not perms.administrator
