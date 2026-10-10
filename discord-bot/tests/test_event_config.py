"""Event configuration (server / channel / roles), using stand-ins for Discord objects."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import discord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eventos_app import paths, runner  # noqa: E402


def make_bot(tmp_path, monkeypatch, guilds=(), channels=()):
    """An AdvancedQTEBot shell: only the attributes the event-config code touches."""
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module

    bot = object.__new__(module.AdvancedQTEBot)
    bot.qte_channel_id = bot.hp_bar_thread_id = bot.qte_player_role_id = bot.admin_role_id = 0
    bot.event_guild_id = 0
    bot.last_cache_update = "stale"
    by_id = {c.id: c for c in channels}
    bot.bot = NS(guilds=list(guilds), get_channel=lambda i: by_id.get(i),
                 get_guild=lambda i: next((g for g in guilds if g.id == i), None))
    return bot, module


def role(i, name, position=1, managed=False, default=False):
    return NS(id=i, name=name, position=position, managed=managed, is_default=lambda: default)


class FakeChannel:
    def __init__(self, i, name, guild, threads=(), category=None, can_send=True):
        self.id, self.name, self.guild, self.threads, self.category = i, name, guild, list(threads), category
        self.created = []
        self._can_send = can_send

    async def archived_threads(self, limit=50):
        return
        yield  # noqa: B901 - makes this an (empty) async generator

    async def create_thread(self, **kwargs):
        thread = NS(id=9000 + len(self.created), name=kwargs["name"], send=_async_noop)
        self.created.append(thread)
        return thread

    def permissions_for(self, member):
        return NS(view_channel=True, send_messages=self._can_send)


async def _async_noop(*a, **k):
    return None


def make_guild(i, name, roles):
    guild = NS(id=i, name=name, text_channels=[], roles=roles, me=object(),
               get_role=lambda rid, _r=roles: next((r for r in _r if r.id == rid), None))
    return guild


def test_configure_event_creates_the_hp_thread_and_saves_everything(tmp_path, monkeypatch):
    guild = make_guild(1, "ULTRAVERSE", [role(10, "Jugadores"), role(11, "Staff")])
    channel = FakeChannel(500, "qte", guild)
    bot, module = make_bot(tmp_path, monkeypatch, [guild], [channel])

    result = asyncio.run(bot.configure_event(channel, player_role_id=10, admin_role_id=11))

    assert result["created"] and channel.created[0].name == "📊 HP Bars"
    assert (bot.event_guild_id, bot.qte_channel_id, bot.hp_bar_thread_id) == (1, 500, channel.created[0].id)
    assert (bot.qte_player_role_id, bot.admin_role_id) == (10, 11)
    assert bot.last_cache_update is None  # player list will be rebuilt for the new channel/role
    saved = module.load_data("channel_config", {})
    assert saved == {"guild_id": 1, "qte_channel_id": 500, "hp_bar_thread_id": channel.created[0].id,
                     "qte_player_role_id": 10, "admin_role_id": 11}


def test_configure_event_reuses_an_existing_hp_thread_and_keeps_roles_when_not_given(tmp_path, monkeypatch):
    guild = make_guild(1, "S", [role(10, "Jugadores")])
    existing = NS(id=777, name="📊 HP Bars")
    channel = FakeChannel(500, "qte", guild, threads=[existing])
    bot, _ = make_bot(tmp_path, monkeypatch, [guild], [channel])
    bot.qte_player_role_id, bot.admin_role_id = 10, 11

    result = asyncio.run(bot.configure_event(channel))  # roles untouched

    assert not result["created"] and channel.created == [] and bot.hp_bar_thread_id == 777
    assert (bot.qte_player_role_id, bot.admin_role_id) == (10, 11)
    asyncio.run(bot.configure_event(channel, admin_role_id=0))  # 0 clears the admin role
    assert bot.admin_role_id == 0


def test_configure_event_surfaces_missing_permissions(tmp_path, monkeypatch):
    guild = make_guild(1, "S", [])
    channel = FakeChannel(500, "qte", guild)

    async def forbidden(**kwargs):
        raise discord.Forbidden(NS(status=403, reason="Forbidden"), "Missing Permissions")

    channel.create_thread = forbidden
    bot, _ = make_bot(tmp_path, monkeypatch, [guild], [channel])
    try:
        asyncio.run(bot.configure_event(channel))
    except discord.Forbidden as exc:
        assert "Gestionar hilos" in runner.describe_discord_error(exc)
    else:
        raise AssertionError("expected Forbidden")


def test_roles_are_found_even_when_no_channel_is_set(tmp_path, monkeypatch):
    # the bug in the log: with 3 servers and no channel, saved roles showed "NOT FOUND"
    g1, g2, g3 = (make_guild(i, f"S{i}", [role(100 + i, f"R{i}")]) for i in (1, 2, 3))
    bot, _ = make_bot(tmp_path, monkeypatch, [g1, g2, g3])
    bot.qte_player_role_id = 102  # belongs to the second server
    assert bot.resolve_event_guild() is g2
    bot.event_guild_id = 3
    assert bot.resolve_event_guild() is g3  # an explicit server wins
    bot.event_guild_id, bot.qte_player_role_id = 0, 0
    assert bot.resolve_event_guild() is None  # several servers and nothing chosen: don't guess


def test_a_single_server_is_used_without_asking(tmp_path, monkeypatch):
    only = make_guild(1, "Only", [])
    bot, _ = make_bot(tmp_path, monkeypatch, [only])
    assert bot.resolve_event_guild() is only


def test_servers_snapshot_lists_only_usable_channels_and_real_roles(tmp_path, monkeypatch):
    roles = [role(1, "@everyone", 0, default=True), role(2, "Jugadores", 5), role(3, "BotRole", 9, managed=True),
             role(4, "Staff", 7)]
    guild = make_guild(1, "ULTRAVERSE", roles)
    guild.text_channels = [FakeChannel(10, "qte", guild, category=NS(name="EVENTOS")),
                           FakeChannel(11, "solo-lectura", guild, can_send=False)]
    bot, _ = make_bot(tmp_path, monkeypatch, [guild], guild.text_channels)
    bot.qte_channel_id = 10
    r = runner.BotRunner()
    r._app = NS(bot=bot.bot, qte_channel_id=10, hp_bar_thread_id=0, qte_player_role_id=2, admin_role_id=0,
                resolve_event_guild=bot.resolve_event_guild)

    snapshot = asyncio.run(r._servers_snapshot())

    (g,) = snapshot["guilds"]
    assert [c["name"] for c in g["channels"]] == ["qte"] and g["channels"][0]["group"] == "EVENTOS"
    assert [x["name"] for x in g["roles"]] == ["Staff", "Jugadores"]  # highest first; no @everyone, no bot role
    assert snapshot["current"]["guild_id"] == 1 and snapshot["current"]["player_role_id"] == 2


def test_config_check_table_reports_what_it_finds(tmp_path, monkeypatch):
    guild = make_guild(1, "ULTRAVERSE", [role(10, "Jugadores")])
    channel = FakeChannel(500, "qte", guild)
    bot, module = make_bot(tmp_path, monkeypatch, [guild], [channel])
    bot.qte_channel_id, bot.qte_player_role_id, bot.admin_role_id = 500, 10, 99
    lines = []
    module.console.set_sink(lambda segments: lines.append("".join(s.text for s in segments)))
    try:
        bot.print_config_check()
    finally:
        module.console.set_sink(None)
    table = "\n".join(lines)
    assert "ULTRAVERSE" in table and "#qte" in table and "@Jugadores" in table
    assert table.count("NOT FOUND") == 1  # only the admin role (99) is missing


# ---- fixed-damage hits (boss abilities / boss counters) -------------------------------------
def test_boss_style_fixed_damage_hits_the_player(tmp_path, monkeypatch):
    # damage_player(user, 12) used to raise KeyError (it looked 12 up as a difficulty name), so boss
    # abilities with a fixed damage and the boss counter never hurt anyone
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("EVENTOS_RESET_ON_START", "0")
    monkeypatch.setenv("EVENTOS_HOTKEYS", "0")
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module

    async def scenario():
        bot = module.AdvancedQTEBot()
        uid = 4242
        bot.player_hp[uid] = {"current": 100, "max": 100, "alive": True}
        await bot.damage_player(uid, 12)  # exact amount
        after_fixed = bot.player_hp[uid]["current"]
        await bot.damage_player(uid, "easy")  # still rolls from the difficulty range
        return after_fixed, bot.player_hp[uid]["current"], bot.damage_ranges["easy"]

    after_fixed, after_easy, (low, high) = asyncio.run(scenario())
    assert after_fixed == 88
    assert 88 - high <= after_easy <= 88 - low


def test_servers_snapshot_survives_a_missing_self_member(tmp_path, monkeypatch):
    guild = make_guild(1, "S", [])
    guild.me = None  # member cache not filled yet
    guild.text_channels = [FakeChannel(10, "qte", guild)]
    bot, _ = make_bot(tmp_path, monkeypatch, [guild], guild.text_channels)
    r = runner.BotRunner()
    r._app = NS(bot=bot.bot, qte_channel_id=0, hp_bar_thread_id=0, qte_player_role_id=0, admin_role_id=0,
                resolve_event_guild=bot.resolve_event_guild)
    (g,) = asyncio.run(r._servers_snapshot())["guilds"]
    assert [c["name"] for c in g["channels"]] == ["qte"]
