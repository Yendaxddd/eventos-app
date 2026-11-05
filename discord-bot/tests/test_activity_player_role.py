"""The participant role: whoever opens the Activity gets it (so the bot tracks their HP and QTEs), `/join` gives it to whoever is
not in the Activity, and the game masters switch the automatic part on and off."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import discord

sys.path.insert(0, str(Path(__file__).parent))

from eventos_app.activity.staff import OP_PERMS  # noqa: E402
from test_activity_gm_socket import GmRig  # noqa: E402
from test_activity_panel import ME, OTHER  # noqa: E402
from test_activity_play import run  # noqa: E402


class Member:
    def __init__(self, uid, roles=(), fail=None):
        self.id, self.name, self.display_name, self.bot = uid, f"u{uid}", f"U{uid}", False
        self.roles, self.fail, self.guild = list(roles), fail, None

    async def add_roles(self, role, reason=None):
        if self.fail:
            raise self.fail
        self.roles.append(role)
        self.reason = reason


def test_the_bot_gives_the_role_once_and_says_why_not(tmp_path, monkeypatch):
    from eventos_app import paths
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module
    bot = object.__new__(module.AdvancedQTEBot)
    refreshed = []

    async def refresh():
        refreshed.append(1)
    bot.update_qte_player_cache = refresh
    role = NS(id=55, name="Participante")
    guild = NS(get_role=lambda rid: role if rid == 55 else None)

    def member(**kw):
        m = Member(9, **kw)
        m.guild = guild
        return m

    bot.qte_player_role_id = 0
    assert run(bot.grant_player_role(member())) == "no_role"
    bot.qte_player_role_id = 55
    fresh = member()
    assert run(bot.grant_player_role(fresh, "test")) == "added" and fresh.roles == [role] and fresh.reason == "test" and refreshed == [1]
    assert run(bot.grant_player_role(fresh)) == "had" and refreshed == [1]
    forbidden = discord.Forbidden(NS(status=403, reason="Forbidden"), "Missing Permissions")
    assert run(bot.grant_player_role(member(fail=forbidden))) == "forbidden"
    assert run(bot.grant_player_role(member(fail=RuntimeError("x")))) == "error"
    src = Path(module.__file__).read_text(encoding="utf-8")
    assert '@self.bot.tree.command(name="join"' in src and '"auto_player_role": getattr(self, "auto_player_role", True)' in src


def test_opening_the_activity_gives_the_role_but_not_to_who_runs_the_event():
    async def scenario():
        async with GmRig() as rig:
            given = []

            async def grant(member, reason=""):
                given.append(member.id)
                return "added"
            rig.app.grant_player_role = grant
            rig.app.auto_player_role = False
            off, _ = await rig.login(OTHER)
            await asyncio.sleep(0.05)
            before = list(given)
            rig.app.auto_player_role = True
            player, _ = await rig.login(OTHER)
            gm, _ = await rig.login(ME)                                   # Ana runs the event (a host): no role for her
            await asyncio.sleep(0.05)
            refused = await rig.ask(player, "gm.auto_role", on=False)
            state = await rig.ask(gm, "gm.players")
            switched = await rig.ask(gm, "gm.auto_role", on=False)
            again = await rig.ask(gm, "gm.auto_role", on=True)
            return before, list(given), refused, state, switched, again, rig.app.auto_player_role, rig.bridge.gm.log.recent()

    before, given, refused, state, switched, again, final, history = run(scenario())
    assert before == [] and given[0] == OTHER and ME not in given
    assert refused["t"] == "rpc_err"
    assert state["data"]["autoRole"]["on"] is True
    assert switched["data"]["on"] is False and again["data"]["on"] is True and final is True
    assert again["data"]["given"] >= 1                                     # switched on: Mina, who is in, gets it now
    assert any("Rol de participante para Mina" in e["action"] for e in history)
    assert any("automático: desactivado" in e["action"] for e in history)


def test_the_switch_needs_the_players_box():
    assert OP_PERMS["gm.auto_role"] == "players"
