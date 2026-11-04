"""Development tool: the Activity running against a made-up bot (the same fakes the tests use), on a fixed port, until Ctrl+C.
    python activity_client/devserver.py [port]
Open http://127.0.0.1:8799/?dev=Ana&gm=1 (GM) or ?dev=Mina (player). Rebuild the client with `node build.mjs --dev` and reload.
Not shipped with the app."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_activity_play  # noqa: E402
from eventos_app.activity.server import ActivityServer, dev_identity  # noqa: E402
from preview import BACKLOG  # noqa: E402
from preview_gm import PIXEL, WEB, seed  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8799


class FixedPortServer(ActivityServer):
    def __init__(self, *args, **kwargs):
        kwargs["port"] = PORT
        super().__init__(*args, **kwargs)


test_activity_play.ActivityServer = FixedPortServer


async def main():
    me = dev_identity("Ana")[0]
    rig = GmRig(me=me)
    rig.web_dir = WEB
    async with rig:
        seed(rig)
        rig.admins.add(me)

        async def media(url):
            return "image/png", PIXEL
        rig.server._media_fetch = media
        rig.hub.channel_name = "evento-principal"
        rig.hub.backlog.extend(BACKLOG)

        async def dev_fight(conn, args):
            """Dev only: a short made-up fight, so the results screens have something to count. Run from the console:
            await window.__eventos.rpc("dev.fight")"""
            players = list(rig.app.qte_players)
            say = rig.bridge.on_event
            say("fight_start"); say("boss_spawn", {"name": "Rey de las Maldiciones"})
            for i, p in enumerate(players):
                for _ in range(3 - i):
                    say("black_flash", {"user": p.id, "damage": 25 + 5 * i, "ms": 240 + 30 * i})
                say("parry_ok", {"user": p.id, "ms": 180 + 70 * i})
                say("evade_ok", {"user": p.id, "ms": 300 + 40 * i})
                say("player_hit", {"user": p.id, "amount": 10 * (i + 1)})
                say("boss_hit", {"amount": 40})
            if len(players) > 1:
                say("rescue_ok", {"user": players[1].id, "ms": 410})
            say("qte_fail", {"user": players[-1].id})
            if args.get("end", True):
                say("boss_defeated", {"name": "Rey de las Maldiciones"})
            return {"ok": True}
        rig.bridge.rpc_dev_fight = dev_fight
        print(f"Activity dev server: http://127.0.0.1:{rig.port}/?dev=Ana&gm=1", flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
