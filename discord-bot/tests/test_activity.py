"""The Activity: server, clock sync, auth, mirrored messages, tunnel."""
import asyncio
import json
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import discord  # noqa: E402
from eventos_app.activity import (ActivityBridge, ActivityServer, AuthError, Conn, DiscordAuth, Hub, Tunnel,  # noqa: E402
                                  serialize_message)
from eventos_app.activity import tunnel as tunnel_module  # noqa: E402
from fake_discord import FakeDiscord  # noqa: E402

ALLOWED = {111: "Ana", 222: "Luis"}


def run(coro):
    return asyncio.run(coro)


class Rig:
    """A fake Discord, a hub, the server on a free port, and helpers to connect like the client does."""

    def __init__(self, tmp_path: Path | None = None, *, secret: str = "s3cret", dev: bool = True, web: bool = False):
        self.discord = FakeDiscord()
        self.hub = Hub()
        self.tmp_path, self.secret, self.dev, self.web = tmp_path, secret, dev, web
        self.http: aiohttp.ClientSession | None = None

    async def authorize(self, user_id: int) -> dict:
        if user_id not in ALLOWED:
            raise AuthError("No eres miembro del servidor del evento.")
        return {"name": ALLOWED[user_id], "avatar": f"https://cdn.example/{user_id}.png"}

    async def __aenter__(self):
        await self.discord.start()
        web_dir = self.tmp_path or Path("/nonexistent")
        if self.web and self.tmp_path:
            (self.tmp_path / "index.html").write_text("<h1>hola</h1>", encoding="utf-8")
            (self.tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
        self.auth = DiscordAuth(client_id=42, client_secret=self.secret,
                                api_base=f"http://127.0.0.1:{self.discord.port}/api/v10")
        self.server = ActivityServer(self.hub, auth=self.auth, authorize=self.authorize, web_dir=web_dir, client_id=42,
                                     port=0, allow_dev=self.dev)
        self.port = await self.server.start()
        self.http = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc):
        await self.http.close()
        await self.server.stop()
        await self.auth.close()
        await self.discord.stop()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    async def login(self, user_id: int, headers: dict | None = None):
        """The real flow: trade the OAuth code for a token through /api/token, then say hello on the WebSocket."""
        self.discord.add_oauth_user(f"code{user_id}", user_id, ALLOWED.get(user_id, "stranger"))
        async with self.http.post(self.url("/api/token"), json={"code": f"code{user_id}"}) as r:
            token = (await r.json())["access_token"]
        return await self.hello({"t": "hello", "token": token}, headers)

    async def hello(self, frame: dict, headers: dict | None = None):
        ws = await self.http.ws_connect(self.url("/ws"), headers=headers)
        await ws.send_json(frame)
        return ws, await ws.receive_json()


async def frame(ws, skip=("users",), timeout=2.0):
    """The next frame that is not a (frequent, harmless) who-is-online update."""
    while True:
        got = await asyncio.wait_for(ws.receive_json(), timeout)
        if got["t"] not in skip:
            return got


# ---- sign in -----------------------------------------------------------------------------------------------------
def test_a_player_signs_in_with_the_oauth_code_and_gets_the_channel_state():
    async def scenario():
        async with Rig() as rig:
            rig.hub.channel_name = "qte-evento"
            await rig.hub.push_message({"id": "1", "text": "hola"})
            ws, welcome = await rig.login(111)
            await ws.close()
            return welcome

    welcome = run(scenario())
    assert welcome["t"] == "welcome" and welcome["you"]["name"] == "Ana" and welcome["channel"] == "qte-evento"
    assert welcome["backlog"] == [{"id": "1", "text": "hola"}] and welcome["users"][0]["id"] == "111"
    assert abs(welcome["serverTime"] - time.time() * 1000) < 2000


def test_someone_outside_the_server_or_with_a_bad_token_is_turned_away_with_a_reason():
    async def scenario():
        async with Rig() as rig:
            ws, stranger = await rig.login(999)
            _, bad = await rig.hello({"t": "hello", "token": "nope"})
            _, late = await rig.hello({"t": "ping"})
            return stranger, bad, late, rig.hub.participants()

    stranger, bad, late, people = run(scenario())
    assert stranger["t"] == "error" and "miembro" in stranger["reason"]
    assert bad["t"] == "error" and "sesión" in bad["reason"] and late["t"] == "error"
    assert people == []


def test_the_token_endpoint_explains_problems_in_spanish():
    async def scenario():
        async with Rig(secret="") as no_secret:
            no_secret.discord.add_oauth_user("c", 111)
            async with no_secret.http.post(no_secret.url("/api/token"), json={"code": "c"}) as r:
                a = (r.status, await r.json())
            async with no_secret.http.post(no_secret.url("/api/token"), data="not json") as r:
                b = r.status
        async with Rig() as rig:
            async with rig.http.post(rig.url("/api/token"), json={"code": "wrong"}) as r:
                c = (r.status, await r.json())
        return a, b, c

    a, b, c = run(scenario())
    assert a[0] == 400 and "Client Secret" in a[1]["error"] and b == 400
    assert c[0] == 400 and "no aceptó" in c[1]["error"]


# ---- test window from this very PC ------------------------------------------------------------------------------------
def test_the_local_test_login_never_works_through_the_tunnel():
    async def scenario():
        async with Rig() as rig:
            _, local = await rig.hello({"t": "hello", "dev": "Ana"})
            _, tunneled = await rig.hello({"t": "hello", "dev": "Ana"}, {"Cf-Ray": "abc", "CF-Connecting-IP": "1.2.3.4"})
            _, forwarded = await rig.hello({"t": "hello", "dev": "Ana"}, {"X-Forwarded-For": "1.2.3.4"})
            _, other_host = await rig.hello({"t": "hello", "dev": "Ana"}, {"Host": "abc.trycloudflare.com"})
        async with Rig(dev=False) as off:
            _, disabled = await off.hello({"t": "hello", "dev": "Ana"})
        return local, tunneled, forwarded, other_host, disabled

    local, tunneled, forwarded, other_host, disabled = run(scenario())
    assert local["t"] == "welcome" and local["you"]["name"] == "Ana (prueba local)" and local["you"]["dev"]
    for refused in (tunneled, forwarded, other_host, disabled):
        assert refused["t"] == "error" and "este mismo PC" in refused["reason"]


# ---- clock sync ---------------------------------------------------------------------------------------------------------
def test_ping_pong_gives_the_server_clock_and_the_clients_conclusion_is_kept():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.hello({"t": "hello", "dev": "Ana"})
            sent = time.time() * 1000
            await ws.send_json({"t": "ping", "c": 123.5})
            pong = await frame(ws)
            await ws.send_json({"t": "sync", "rtt": 42.5, "offset": -17.0})
            await ws.send_json({"t": "sync", "rtt": "garbage", "offset": None})     # ignored, no crash
            await ws.send_json({"t": "ping", "c": 1})
            await frame(ws)
            stats = rig.hub.stats()
            await ws.close()
            return pong, sent, stats

    pong, sent, stats = run(scenario())
    assert pong["t"] == "pong" and pong["c"] == 123.5 and abs(pong["s"] - sent) < 1000
    assert stats[0]["rtt_ms"] == 42.5 and stats[0]["offset_ms"] == -17.0


def test_a_connection_that_floods_is_told_to_slow_down_instead_of_being_served():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.hello({"t": "hello", "dev": "Ana"})
            for _ in range(200):
                await ws.send_json({"t": "ping", "c": 1})
            kinds = []
            try:
                while True:
                    kinds.append((await asyncio.wait_for(ws.receive_json(), 0.5))["t"])
            except asyncio.TimeoutError:
                pass
            return kinds

    kinds = run(scenario())
    assert "slow" in kinds and kinds.count("pong") < 200


def test_chat_frames_are_refused_while_the_mirror_is_read_only():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.hello({"t": "hello", "dev": "Ana"})
            await ws.send_json({"t": "chat", "text": "hola"})
            return await frame(ws)

    reply = run(scenario())
    assert reply["t"] == "error" and reply["code"] == "readonly"


# ---- the mirrored channel ---------------------------------------------------------------------------------------------------
def test_everyone_connected_sees_new_edited_and_deleted_messages_and_who_is_online():
    async def scenario():
        async with Rig() as rig:
            ana, _ = await rig.hello({"t": "hello", "dev": "Ana"})
            luis, _ = await rig.hello({"t": "hello", "dev": "Luis"})
            await rig.hub.push_message({"id": "7", "text": "uno"})
            await rig.hub.edit_message({"id": "7", "text": "dos"})
            await rig.hub.delete_message("7")
            got = [[(await frame(w))["t"] for _ in range(3)] for w in (ana, luis)]
            late, welcome = await rig.hello({"t": "hello", "dev": "Eva"})
            await ana.close()
            await luis.close()
            await asyncio.sleep(0.1)
            return got, welcome["backlog"], [u["name"] for u in welcome["users"]], len(rig.hub.participants())

    got, backlog, users, remaining = run(scenario())
    assert got == [["msg", "edit", "del"]] * 2
    assert backlog == [] and len(users) == 3 and remaining == 1      # Eva is still connected


def test_two_windows_of_the_same_person_count_once_and_the_backlog_is_capped():
    async def scenario():
        hub = Hub(backlog=3)
        a = Conn(1, 5, "Ana", "", None)
        b = Conn(2, 5, "Ana", "", None)
        hub.conns = {1: a, 2: b}
        for i in range(10):
            hub.backlog.append({"id": str(i)})
        return hub.participants(), [m["id"] for m in hub.backlog]

    people, kept = run(scenario())
    assert len(people) == 1 and kept == ["7", "8", "9"]


def test_the_first_player_to_join_triggers_one_read_of_the_channel_history():
    async def scenario():
        hub = Hub()
        calls = []

        async def loader():
            calls.append(1)
            return [{"id": "1"}, {"id": "2"}]

        hub.loader = loader
        first = await hub.load_backlog()
        second = await hub.load_backlog()
        hub.reset_channel("otro")
        await hub.load_backlog()
        return first, second, len(calls), hub.channel_name

    first, second, calls, name = run(scenario())
    assert first == second == [{"id": "1"}, {"id": "2"}] and calls == 2 and name == "otro"


# ---- static files ------------------------------------------------------------------------------------------------------------------
def test_the_client_is_served_also_under_the_discord_proxy_prefix_and_a_missing_build_says_so(tmp_path):
    async def scenario():
        async with Rig(tmp_path, web=True) as rig:
            out = {}
            for path in ("/", "/app.js", "/.proxy/", "/.proxy/app.js", "/healthz", "/.proxy/api/config"):
                async with rig.http.get(rig.url(path)) as r:
                    out[path] = (r.status, await r.text())
        async with Rig() as bare:
            async with bare.http.get(bare.url("/")) as r:
                out["missing"] = (r.status, await r.text())
        return out

    out = run(scenario())
    assert out["/"] == (200, "<h1>hola</h1>") and out["/.proxy/"][1] == "<h1>hola</h1>"
    assert out["/app.js"][1] == out["/.proxy/app.js"][1] == "console.log(1)"
    assert json.loads(out["/healthz"][1])["ok"] and json.loads(out["/.proxy/api/config"][1])["clientId"] == "42"
    assert out["missing"][0] == 503 and "todavía no está construida" in out["missing"][1]


def test_a_second_copy_of_the_app_takes_the_next_free_port():
    async def scenario():
        discord = FakeDiscord()
        auth = DiscordAuth(client_id=1, client_secret="x")
        servers = [ActivityServer(Hub(), auth=auth, authorize=None, web_dir=Path("/nonexistent"), client_id=1, port=18765)
                   for _ in range(2)]
        ports = [await s.start() for s in servers]
        for s in servers:
            await s.stop()
        return ports

    ports = run(scenario())
    assert ports[0] == 18765 and ports[1] == 18766


# ---- the bridge with the bot -----------------------------------------------------------------------------------------------------
def fake_message(mid=5, channel=10, text="hola **mundo**", webhook=None, bot=False, attachments=(), embeds=(), edited=False):
    author = NS(id=77, display_name="Ana", name="ana", bot=bot, color=NS(value=0x336699),
                display_avatar=NS(url="https://cdn.example/a.png"))
    return NS(id=mid, channel=NS(id=channel), author=author, webhook_id=webhook, clean_content=text,
              created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), edited_at=datetime.now() if edited else None,
              attachments=list(attachments), embeds=list(embeds))


def test_a_message_becomes_plain_data_for_the_client():
    attachment = NS(url="https://cdn.example/x.png", filename="x.png", content_type="image/png")
    embed = NS(title="Black Flash", description="boom", color=NS(value=0xFF0000), image=NS(url="https://i/x.gif"), thumbnail=None)
    frame = serialize_message(fake_message(attachments=[attachment], embeds=[embed], webhook=900), own_webhooks={900})
    assert frame["id"] == "5" and frame["ts"] == 1767225600000 and frame["text"] == "hola **mundo**"
    assert frame["author"] == {"id": "77", "name": "Ana", "avatar": "https://cdn.example/a.png", "bot": False,
                               "webhook": True, "ours": True, "color": "#336699"}
    assert frame["attachments"] == [{"url": "https://cdn.example/x.png", "name": "x.png", "image": True}]
    assert frame["embeds"][0] == {"title": "Black Flash", "description": "boom", "image": "https://i/x.gif", "color": "#ff0000"}
    json.dumps(frame)      # it must be JSON-able as it is


def test_the_bridge_mirrors_only_the_event_channel_and_checks_who_may_see_it():
    async def scenario():
        sent = []

        class Bot:
            def __init__(self):
                self.listeners = []

            def add_listener(self, fn, name):
                self.listeners.append(name)

            def remove_listener(self, fn, name):
                self.listeners.remove(name)

            def get_channel(self, cid):
                return CHANNEL if cid == 10 else None

        member = NS(display_name="Ana", display_avatar=NS(url="u"))
        CHANNEL = NS(name="qte", id=10,
                     permissions_for=lambda m: NS(view_channel=m is member, read_message_history=True))
        async def fetch_member(uid):
            raise discord.NotFound(type("R", (), {"status": 404, "reason": "x"})(), "Unknown Member")

        guild = NS(get_member=lambda uid: member if uid == 111 else (NS() if uid == 333 else None),
                   fetch_member=fetch_member)
        app = NS(bot=Bot(), qte_channel_id=10, own_webhook_ids=set(), resolve_event_guild=lambda: guild)
        hub = Hub()
        hub.push_message = lambda frame: sent.append(frame) or asyncio.sleep(0)
        bridge = ActivityBridge(hub, app)
        bridge.start()
        await bridge._on_message(fake_message(channel=10))
        await bridge._on_message(fake_message(mid=6, channel=99))        # another channel: ignored
        ok = await bridge.authorize(111)
        errors = []
        for uid in (333, 444):
            try:
                await bridge.authorize(uid)
            except AuthError as exc:
                errors.append(str(exc))
        registered = list(app.bot.listeners)
        bridge.stop()
        return sent, ok, errors, registered, app.bot.listeners, hub.channel_name

    sent, ok, errors, registered, after, name = run(scenario())
    assert [m["id"] for m in sent] == ["5"] and ok == {"name": "Ana", "avatar": "u"} and name == "qte"
    assert "acceso al canal" in errors[0] and "miembro" in errors[1]
    assert registered == ["on_message", "on_message_edit", "on_message_delete"] and after == []


# ---- the tunnel -----------------------------------------------------------------------------------------------------------------------
def fake_cloudflared(tmp_path: Path, body: str, name: str = "fake_cloudflared") -> Path:
    script = tmp_path / f"{name}.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return script


def test_the_tunnel_reads_its_public_address_from_cloudflareds_output(tmp_path):
    script = fake_cloudflared(tmp_path, """
        import sys, time
        print("2026-01-01 INF Requesting new quick Tunnel on trycloudflare.com...", flush=True)
        print("2026-01-01 INF |  https://calm-river-1234.trycloudflare.com  |", flush=True)
        time.sleep(30)
    """)
    changes = []

    async def scenario():
        tunnel = Tunnel(8765, command=lambda b, port, proto: [sys.executable, str(script)], on_change=lambda: changes.append(1))
        tunnel.find_binary = lambda: Path(sys.executable)
        url = await tunnel.start()
        state = tunnel.state
        await tunnel.stop()
        return url, state, tunnel.state, tunnel.url

    url, state, after, left = run(scenario())
    assert url == "https://calm-river-1234.trycloudflare.com" and state == "up" and after == "idle" and left == ""
    assert changes


def test_when_the_first_protocol_gives_no_address_the_second_is_tried_and_failure_is_explained(tmp_path, monkeypatch):
    monkeypatch.setattr(tunnel_module, "URL_WAIT_SECONDS", 1.0)
    tried = []
    good = fake_cloudflared(tmp_path, """
        import time
        print("https://second-try.trycloudflare.com", flush=True)
        time.sleep(30)
    """, "good")
    silent = fake_cloudflared(tmp_path, "import time\ntime.sleep(30)\n", "silent")

    async def scenario():
        def command(binary, port, proto):
            tried.append(proto)
            return [sys.executable, str(silent if proto == "quic" else good)]

        tunnel = Tunnel(1, command=command)
        tunnel.find_binary = lambda: Path(sys.executable)
        first = await tunnel.start()
        await tunnel.stop()
        broken = Tunnel(1, command=lambda b, p, proto: [sys.executable, str(silent)])
        broken.find_binary = lambda: Path(sys.executable)
        try:
            await broken.start()
        except tunnel_module.TunnelError as exc:
            return first, str(exc), broken.state
        return first, "", broken.state

    first, message, state = run(scenario())
    assert first == "https://second-try.trycloudflare.com" and tried == ["quic", "http2"]
    assert state == "error" and "ninguna dirección" in message


def test_a_missing_cloudflared_tells_how_to_get_it_outside_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(tunnel_module.sys, "platform", "linux")

    async def scenario():
        tunnel = Tunnel(1, tools_dir=tmp_path)
        tunnel.find_binary = lambda: None
        try:
            await tunnel.start()
        except tunnel_module.TunnelError as exc:
            return str(exc), tunnel.state

    message, state = run(scenario())
    assert "Instala cloudflared" in message and state == "error"


def test_the_build_check_finds_the_client_and_serves_it():
    from eventos_app.main import activity_check
    web = Path(__file__).resolve().parents[1] / "eventos_app" / "activity" / "web"
    if not (web / "app.js").exists():
        import pytest
        pytest.skip("activity client not built")
    assert activity_check() == {"activity_client_bundled": True, "activity_server": True}


def test_the_runner_starts_and_stops_the_activity_and_reports_it_to_the_window(monkeypatch):
    from eventos_app import activity as activity_pkg, console_bridge, runner
    from eventos_app.settings import Settings

    lines: list[str] = []
    console_bridge.console.set_sink(lambda segments: lines.append("".join(s.text for s in segments)))

    class FakeTunnel:
        def __init__(self, port, **kwargs):
            self.port, self.state, self.detail, self.url = port, "idle", "", ""

        async def start(self):
            self.state, self.url = "up", "https://quiet-lake-42.trycloudflare.com"
            return self.url

        async def stop(self):
            self.state, self.url = "idle", ""

    monkeypatch.setattr(activity_pkg, "Tunnel", FakeTunnel)

    class Bot:
        application_id = 4242
        user = NS(id=1)

        def add_listener(self, fn, name):
            pass

        def remove_listener(self, fn, name):
            pass

        def get_channel(self, cid):
            return NS(name="qte-evento", id=cid)

    async def scenario():
        r = runner.BotRunner()
        r._app = NS(bot=Bot(), qte_channel_id=10, own_webhook_ids=set())
        before = r.activity_info()
        await r._start_activity(Settings(activity_enabled=False))
        disabled = r.activity_info()
        await r._start_activity(Settings(activity_enabled=True, activity_client_secret="  sec  "))
        await r._activity_task
        info = r.activity_info()
        async with aiohttp.ClientSession() as http, http.get(f"http://127.0.0.1:{info['port']}/healthz") as health:
            alive = (await health.json())["ok"]
        await r._stop_activity()
        return before, disabled, info, alive, r.activity_info()

    try:
        before, disabled, info, alive, after = run(scenario())
    finally:
        console_bridge.console.set_sink(None)
    assert before == disabled == after == {"running": False}
    assert info["running"] and info["tunnel"] == "up" and info["url"].endswith("trycloudflare.com") and info["secret_set"]
    assert alive and info["users"] == [] and info["port"] >= 8765
    text = "\n".join(lines)
    assert "Servidor de la Actividad" in text and "quiet-lake-42.trycloudflare.com" in text and "URL Mappings" in text
