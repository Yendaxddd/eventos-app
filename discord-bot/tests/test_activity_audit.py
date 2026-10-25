"""What the 2.0 review of the Activity's server found, kept fixed: who may open the GM panel, the QTE clock, image downloads, the
login flood guard, slow sockets, the backups and the history read."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eventos_app.activity.safe_fetch as safe_fetch  # noqa: E402
from eventos_app.activity.auth import AuthError, DiscordAuth, FAILURES_PER_MINUTE  # noqa: E402
from eventos_app.activity.hub import Hub  # noqa: E402
from eventos_app.activity.qte import response_seconds  # noqa: E402
from test_activity import Rig, frame  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def test_a_web_page_open_on_the_host_cannot_use_the_local_test_login_or_the_gm_panel():
    async def scenario():
        async with Rig() as rig:
            _, evil = await rig.hello({"t": "hello", "dev": "x", "gm": True}, headers={"Origin": "https://evil.example"})
            _, local = await rig.hello({"t": "hello", "dev": "x", "gm": True}, headers={"Origin": f"http://127.0.0.1:{rig.port}"})
            _, plain = await rig.hello({"t": "hello", "dev": "y"})                              # no Origin (not a browser page): this PC
            return evil, local, plain

    evil, local, plain = run(scenario())
    assert evil["t"] == "error" and "este mismo PC" in evil["reason"]
    assert local["t"] == "welcome" and plain["t"] == "welcome"


def test_the_players_stopwatch_counts_but_never_beyond_what_a_human_or_the_real_time_allow():
    honest = response_seconds(900, 40, 900 + 80 + 30)
    assert abs(honest - 0.94) < 1e-9                                       # the player's own stopwatch, plus the trip to them
    assert response_seconds(2000, 40, 4500) == 2.04                        # a slow trip back (lag) is not held against the player
    assert response_seconds(40, 40, 4500) is None                          # faster than a human: refused
    assert response_seconds(9000, 40, 4500) <= (4500 + 150) / 1000         # never longer than the QTE has existed


def test_a_redirect_to_a_private_address_is_never_followed(monkeypatch):
    async def scenario():
        app = web.Application()
        hits = []

        async def start(request):
            raise web.HTTPFound("/inside")

        async def inside(request):
            hits.append(1)
            return web.Response(body=b"\x89PNG\r\n\x1a\n")

        app.router.add_get("/start", start)
        app.router.add_get("/inside", inside)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        checked = []

        def check(url):                       # this machine stands for "the internet"; /inside for the house's own network
            checked.append(url)
            if url.endswith("/inside"):
                raise safe_fetch.FetchError("Ese enlace apunta a una dirección que no es pública.")
            return url

        monkeypatch.setattr(safe_fetch, "check_url", check)
        try:
            with pytest.raises(safe_fetch.FetchError):
                await safe_fetch.fetch_bytes(f"http://127.0.0.1:{port}/start", max_bytes=1000)
        finally:
            await runner.cleanup()
        return hits, checked

    hits, checked = run(scenario())
    assert hits == [] and checked[-1].endswith("/inside")


def test_made_up_tokens_are_not_all_taken_to_discord():
    calls = []

    class Session:
        def get(self, url, headers):
            calls.append(headers["Authorization"])

            class Response:
                status = 401

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def json(self, content_type=None):
                    return {}

            return Response()

    async def scenario():
        auth = DiscordAuth(client_id=1, client_secret="s", session=Session())
        refused = 0
        for token in ["", "short", *[f"made-up-token-number-{i:04d}" for i in range(FAILURES_PER_MINUTE + 30)]]:
            try:
                await auth.identify(token)
            except AuthError:
                refused += 1
        again = len(calls)
        try:
            await auth.identify("made-up-token-number-0000")              # one Discord already refused: not asked again
        except AuthError:
            pass
        return refused, again, len(calls)

    refused, asked, after = run(scenario())
    assert refused == FAILURES_PER_MINUTE + 32 and asked == FAILURES_PER_MINUTE and after == asked


def test_a_screen_that_stops_reading_does_not_hold_up_the_others(monkeypatch):
    import eventos_app.activity.hub as hub_module
    monkeypatch.setattr(hub_module, "SEND_TIMEOUT", 0.1)

    class Stuck:
        closed = False

        async def send_json(self, frame):
            await asyncio.sleep(30)

        async def close(self):
            Stuck.closed = True

    class Quick:
        got = []

        async def send_json(self, frame):
            Quick.got.append(frame)

    async def scenario():
        hub = Hub()
        stuck = NS(id=1, user_id=1, ws=Stuck(), name="x", hidden=False)
        quick = NS(id=2, user_id=2, ws=Quick(), name="y", hidden=False)
        hub.conns = {1: stuck, 2: quick}
        loop = asyncio.get_running_loop()
        began = loop.time()
        sent = await hub.broadcast({"t": "x"})
        await asyncio.sleep(0.01)
        return sent, loop.time() - began

    sent, took = run(scenario())
    assert sent == 1 and took < 1 and Quick.got == [{"t": "x"}] and Stuck.closed


def test_the_history_is_read_once_and_what_arrives_meanwhile_is_kept_after_it_once():
    async def scenario():
        hub = Hub()
        reads = []
        gate = asyncio.Event()

        async def loader():
            reads.append(1)
            await gate.wait()
            return [{"id": "1"}, {"id": "2"}]

        hub.loader = loader
        first = asyncio.ensure_future(hub.load_backlog())
        second = asyncio.ensure_future(hub.load_backlog())
        await asyncio.sleep(0)
        await hub.push_message({"id": "2"})                       # already in the history: not twice
        await hub.push_message({"id": "3"})
        gate.set()
        return await first, await second, reads

    first, second, reads = run(scenario())
    assert reads == [1] and [m["id"] for m in first] == ["1", "2", "3"] and first == second


def test_backups_of_files_with_the_same_name_in_different_folders_stay_apart(tmp_path):
    from eventos_app.activity.gm.data import DataOps  # noqa: PLC0415
    a, b = tmp_path / "objects" / "sword.json", tmp_path / "pending" / "sword.json"
    assert DataOps._backup_prefix(a) != DataOps._backup_prefix(b)
