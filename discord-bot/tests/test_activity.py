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


def test_writing_is_refused_when_the_server_has_no_actions():
    async def scenario():
        async with Rig() as rig:
            ws, _ = await rig.hello({"t": "hello", "dev": "Ana"})
            await ws.send_json({"t": "say", "text": "hola"})
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


def test_the_hosts_own_window_is_not_listed_among_the_players_but_still_counts_as_a_connection():
    async def scenario():
        async with Rig() as rig:
            ana, ana_welcome = await rig.hello({"t": "hello", "dev": "Ana"})
            host, host_welcome = await rig.hello({"t": "hello", "dev": "Anfitrión", "gm": True, "host": True})
            rig.discord.add_oauth_user("code222", 222, ALLOWED.get(222, "stranger"))           # a Discord player who says «host» in their hello
            async with rig.http.post(rig.url("/api/token"), json={"code": "code222"}) as r:
                token = (await r.json())["access_token"]
            player, player_welcome = await rig.hello({"t": "hello", "token": token, "host": True, "gm": True})
            listed = [u["name"] for u in rig.hub.participants()]
            stats = {c["name"]: c["hidden"] for c in rig.hub.stats()}
            return ana_welcome, host_welcome, player_welcome, listed, stats, [c.gm for c in rig.hub.conns.values()]

    ana_welcome, host_welcome, player_welcome, listed, stats, gm_flags = run(scenario())
    assert [u["name"] for u in ana_welcome["users"]] == ["Ana (prueba local)"]
    assert [u["name"] for u in host_welcome["users"]] == ["Ana (prueba local)"]                        # it is not even in the list it is first shown
    assert player_welcome["t"] == "welcome" and ALLOWED[222] in listed                                  # a Discord player can not hide (or take the panel) by saying so
    assert "Anfitrión (prueba local)" not in listed and "Ana (prueba local)" in listed
    assert stats["Anfitrión (prueba local)"] is True and stats["Ana (prueba local)"] is False and stats[ALLOWED[222]] is False
    assert sorted(gm_flags) == [False, False, True]                                                     # only the host's window asked for the panel and got it


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
    assert frame["embeds"][0]["title"] == "Black Flash" and frame["embeds"][0]["image"] == "https://i/x.gif"
    assert frame["embeds"][0]["color"] == "#ff0000" and frame["reactions"] == [] and frame["reply"] is None
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
    assert registered[:3] == ["on_message", "on_message_edit", "on_message_delete"] and "on_reaction_add" in registered
    assert after == []


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


# ---- the fixed Tailscale Funnel address ----------------------------------------------------------------------------------------------
def tailscale(tmp_path, *, status: dict | str, funnel: str = "Available on the internet:\\nhttps://pc.tail1234.ts.net/\\n", funnel_code: int = 0,
              listed: str = "https://pc.tail1234.ts.net (Funnel on)", name: str = "tailscale"):
    """A fake `tailscale` that answers like the real CLI and writes down every command it was given."""
    calls = tmp_path / f"{name}.calls"
    script = fake_cloudflared(tmp_path, f"""
        import json, sys
        args = sys.argv[1:]
        open({str(calls)!r}, "a").write(" ".join(args) + "\\n")
        if args[:1] == ["status"]:
            print({status if isinstance(status, str) else json.dumps(status)!r})
        elif args[:2] == ["funnel", "status"]:
            print({listed!r})
        elif args[:1] == ["funnel"] and "off" not in args:
            print({funnel!r}.replace("\\\\n", "\\n"))
            sys.exit({funnel_code})
    """, name)
    async def known(name):
        return True
    tunnel = tunnel_module.TailscaleTunnel(8765, command=lambda binary, args: [sys.executable, str(script), *args], dns_lookup=known)
    tunnel.find_binary = lambda: Path(sys.executable)
    return tunnel, calls


RUNNING = {"BackendState": "Running", "Self": {"DNSName": "pc.tail1234.ts.net."}}


async def _known(name):
    return True


def test_until_the_public_dns_knows_the_funnel_address_the_app_says_so(tmp_path):
    tunnel, _ = tailscale(tmp_path, status=RUNNING)
    answers = iter([False, False, True])
    asked = []

    async def lookup(name):
        asked.append(name)
        return next(answers)
    tunnel._dns_lookup = lookup

    async def scenario():
        await tunnel.start()
        seen = []
        tunnel._watch.cancel()
        tunnel._watch = asyncio.get_running_loop().create_task(tunnel._watch_public("pc.tail1234.ts.net", every=0.01))
        for _ in range(100):
            seen.append(tunnel.public)
            if tunnel.public:
                break
            await asyncio.sleep(0.01)
        await tunnel.stop()
        return seen

    seen = run(scenario())
    assert False in seen and seen[-1] is True and asked[0] == "pc.tail1234.ts.net"


def test_the_tailscale_address_is_the_machines_public_name_and_the_funnel_stays_on_when_the_bot_stops(tmp_path):
    tunnel, calls = tailscale(tmp_path, status=RUNNING)

    async def scenario():
        url = await tunnel.start()
        state = (tunnel.state, tunnel.fixed)
        await tunnel.stop()
        return url, state, tunnel.state

    url, state, after = run(scenario())
    assert url == "https://pc.tail1234.ts.net" and state == ("up", True) and after == "idle"
    lines = calls.read_text().splitlines()
    assert lines[0] == "status --json" and lines[1] == "funnel --bg --https=443 http://127.0.0.1:8765"
    # switching it off would take the address out of the public DNS for minutes or hours (Discord: «Error 1016»)
    assert not any("off" in line for line in lines)


def test_tailscale_problems_say_what_to_do(tmp_path):
    cases = {
        "login": dict(status={"BackendState": "NeedsLogin"}),
        "stopped": dict(status={"BackendState": "Stopped"}),
        "nodns": dict(status={"BackendState": "Running", "Self": {"DNSName": ""}}),
        "garbage": dict(status="not json"),
        "unapproved": dict(status=RUNNING, funnel="Funnel is not enabled on your tailnet.\\nTo enable, visit:\\n https://login.tailscale.com/f/funnel?node=n123\\n",
                           funnel_code=1),
        "failed": dict(status=RUNNING, funnel="listener already exists for port 443", funnel_code=1),
        "unconfirmed": dict(status=RUNNING, listed="No serve config"),
    }

    async def scenario():
        out = {}
        for name, options in cases.items():
            tunnel, _ = tailscale(tmp_path, name=f"ts_{name}", **options)
            try:
                await tunnel.start()
                out[name] = "started"
            except tunnel_module.TunnelError as exc:
                out[name] = (str(exc), tunnel.state)
        return out

    out = run(scenario())
    assert "inicia sesión" in out["login"][0] and "desconectado" in out["stopped"][0]
    assert "MagicDNS" in out["nodns"][0] and "no respondió" in out["garbage"][0]
    assert "https://login.tailscale.com/f/funnel?node=n123" in out["unapproved"][0] and "una vez" in out["unapproved"][0]
    assert "listener already exists" in out["failed"][0] and "no confirmó" in out["unconfirmed"][0]
    assert all(v[1] == "error" for v in out.values())


def test_without_tailscale_installed_the_error_gives_the_download(tmp_path):
    tunnel = tunnel_module.TailscaleTunnel(1)
    tunnel.find_binary = lambda: None

    async def scenario():
        try:
            await tunnel.start()
        except tunnel_module.TunnelError as exc:
            return str(exc)

    assert "tailscale.com/download" in run(scenario())


def test_the_settings_check_reads_tailscales_state(monkeypatch):
    assert tunnel_module.read_status(json.dumps(RUNNING)) == ("pc.tail1234.ts.net", "")
    monkeypatch.setattr(tunnel_module, "find_tailscale", lambda: None)
    ok, message = tunnel_module.check_tailscale()
    assert not ok and "no está instalado" in message


def test_through_the_funnel_the_local_test_login_stays_refused():
    async def scenario():
        async with Rig() as rig:
            # what a request arriving through Tailscale Funnel looks like: the public name as Host, forwarding headers
            funnel = {"Host": "pc.tail1234.ts.net", "X-Forwarded-For": "203.0.113.9"}
            _, via_funnel = await rig.hello({"t": "hello", "dev": "Ana"}, funnel)
            _, host_only = await rig.hello({"t": "hello", "dev": "Ana"}, {"Host": "pc.tail1234.ts.net"})
            return via_funnel, host_only

    for refused in run(scenario()):
        assert refused["t"] == "error" and "este mismo PC" in refused["reason"]


# ---- pictures through our own server -------------------------------------------------------------------------------------------------
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_pictures_come_through_the_server_only_from_discord_hosts_and_are_cached(tmp_path):
    calls = []

    async def fetch(url):
        calls.append(url)
        if url.endswith("big.png"):
            raise ValueError("size")
        if url.endswith("page.png"):
            raise ValueError("type")
        if url.endswith("down.png"):
            raise OSError("HTTP 500")
        return "image/png", PNG

    async def scenario():
        async with Rig() as rig:
            rig.server._media_fetch = fetch
            rig.server.media_dir = tmp_path / "cache"
            out = {}
            good = "https://cdn.discordapp.com/avatars/1/a.png"
            for name, u in (("ok", good), ("again", good), ("ext", "https://images-ext-1.discordapp.net/external/x/y.png"),
                            ("evil", "https://evil.example/a.png"), ("lookalike", "https://cdn.discordapp.com.evil.example/a.png"),
                            ("http", "http://cdn.discordapp.com/a.png"), ("creds", "https://u:p@cdn.discordapp.com/a.png"),
                            ("big", "https://cdn.discordapp.com/big.png"), ("page", "https://cdn.discordapp.com/page.png"),
                            ("down", "https://cdn.discordapp.com/down.png")):
                async with rig.http.get(rig.url("/media"), params={"u": u}) as r:
                    out[name] = (r.status, r.headers.get("Content-Type"), await r.read())
            async with rig.http.get(rig.url("/.proxy/media"), params={"u": good}, headers={"Range": "bytes=0-3"}) as r:
                out["range"] = (r.status, await r.read())
            return out

    out = run(scenario())
    assert out["ok"] == (200, "image/png", PNG) and out["again"][2] == PNG and out["ext"][0] == 200
    assert [c for c in calls if c.endswith("a.png")] == ["https://cdn.discordapp.com/avatars/1/a.png"]      # the second came from disk
    assert out["evil"][0] == out["lookalike"][0] == out["creds"][0] == 403 and out["http"][0] == 400
    assert (out["big"][0], out["page"][0], out["down"][0]) == (413, 415, 502)
    assert out["range"] == (206, PNG[:4])                                    # Safari needs ranges to play a clip
    assert all("evil" not in c and "http://" not in c for c in calls)


def test_a_funnel_command_that_hangs_is_explained_or_accepted_if_the_funnel_is_already_on(tmp_path, monkeypatch):
    monkeypatch.setattr(tunnel_module, "CLI_TIMEOUT", 0.6)
    hang = """
        import json, sys, time
        a = sys.argv[1:]
        if a[:1] == ["status"]:
            print(json.dumps({"BackendState": "Running", "Self": {"DNSName": "pc.tail1234.ts.net."}}))
        elif a[:2] == ["funnel", "status"]:
            print(%r)
        elif a[:1] == ["funnel"] and "off" not in a:
            print("Waiting for approval...", flush=True); time.sleep(30)
    """
    out = {}

    async def scenario():
        for name, listed in (("off", "No serve config"), ("on", "https://pc.tail1234.ts.net (Funnel on)")):
            script = fake_cloudflared(tmp_path, hang % listed, f"ts_hang_{name}")
            tunnel = tunnel_module.TailscaleTunnel(8765, command=lambda b, args, s=script: [sys.executable, str(s), *args], dns_lookup=_known)
            tunnel.find_binary = lambda: Path(sys.executable)
            try:
                out[name] = await tunnel.start()
            except tunnel_module.TunnelError as exc:
                out[name] = str(exc)
            await tunnel.stop()

    run(scenario())
    assert "tardó demasiado" in out["off"] and "Waiting for approval" in out["off"] and "tailscale funnel --bg 8765" in out["off"]
    assert out["on"] == "https://pc.tail1234.ts.net"


# ---- what the app's log learns about the Activity ------------------------------------------------------------------------------------
def test_the_app_log_hears_about_page_requests_the_pages_own_progress_and_refused_logins():
    notes = []

    async def scenario():
        async with Rig(web=False) as rig:
            rig.server.on_event = notes.append
            async with rig.http.get(rig.url("/healthz")) as r:
                await r.read()
            async with rig.http.get(rig.url("/.proxy/api/config"), headers={"User-Agent": "Mozilla/5.0 [odd]", "X-Forwarded-For": "1.2.3.4"}) as r:
                await r.read()
            for stage, detail in (("SDK de Discord listo", ""), ("error", "x is not defined (app.js:3)")):
                async with rig.http.post(rig.url("/.proxy/api/report"), json={"stage": stage, "detail": detail}) as r:
                    assert r.status == 200
            async with rig.http.post(rig.url("/api/report"), data="garbage") as r:
                assert r.status == 400
            ws, _ = await rig.login(999)                                           # not in the server: refused
            await ws.close()
            ws, _ = await rig.login(111)
            await ws.close()
            for _ in range(60):                                                    # past the cap: told to stop, nothing logged
                async with rig.http.post(rig.url("/api/report"), json={"stage": "error", "detail": "spam"}) as r:
                    last = r.status
            return last

    last = run(scenario())
    text = "\n".join(notes)
    assert "GET /healthz → 200 (desde este PC" in text and "GET /api/config → 200 (por el túnel, Mozilla/5.0 [odd]" in text
    assert "la página dice: SDK de Discord listo" in text and "la página dice: error — x is not defined (app.js:3)" in text
    assert "entrada rechazada: No eres miembro" in text and "Ana entró a la Actividad" in text
    assert last == 429 and text.count("spam") < 40


def test_the_page_names_the_version_of_its_files_and_the_files_are_always_rechecked(tmp_path):
    async def scenario():
        async with Rig(tmp_path, web=True) as rig:
            (tmp_path / "index.html").write_text('<link href="./style.css"><script src="./app.js"></script>', encoding="utf-8")
            (tmp_path / "style.css").write_text("body{}", encoding="utf-8")
            async with rig.http.get(rig.url("/")) as r:
                first = await r.text()
                index_cache = r.headers.get("Cache-Control")
            async with rig.http.get(rig.url("/app.js")) as r:
                js_cache = r.headers.get("Cache-Control")
            (tmp_path / "app.js").write_text("console.log(2)", encoding="utf-8")        # a new version of the client
            async with rig.http.get(rig.url("/")) as r:
                second = await r.text()
            return first, second, index_cache, js_cache

    first, second, index_cache, js_cache = run(scenario())
    assert "app.js?v=" in first and "style.css?v=" in first and first != second       # a changed file changes its address
    assert index_cache == "no-cache" and js_cache == "no-cache"
