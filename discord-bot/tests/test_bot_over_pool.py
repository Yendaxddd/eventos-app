"""The bot's own send / react code on top of the sender pool, with "20 players answered at once"."""
import asyncio
import sys
import time
from pathlib import Path

import discord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app import multibot, paths  # noqa: E402
from fake_discord import FakeDiscord  # noqa: E402
from test_multibot import CHANNEL, LIMIT, POOL_WINDOW, REACTION_WINDOW, SPACING, WINDOW  # noqa: E402

PLAYERS = 20


def burst_of_replies(tmp_path, monkeypatch, helpers: int, latency: float = 0.05):
    """Each of PLAYERS players answers: the bot posts a result message and reacts to the player's message."""
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setenv("DISCORD_TOKEN", "tok-primary")
    monkeypatch.setenv("EVENTOS_RESET_ON_START", "0")
    monkeypatch.setenv("EVENTOS_HOTKEYS", "0")
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module

    async def scenario():
        server = FakeDiscord(limit=LIMIT, window=WINDOW, latency=latency, reaction_window=REACTION_WINDOW)
        server.add_bot("tok-primary", 100)
        tokens = [f"tok-h{i}" for i in range(helpers)]
        for i, token in enumerate(tokens):
            server.add_bot(token, 101 + i)
        await server.start()
        bot = module.AdvancedQTEBot()
        await bot.bot.login("tok-primary")
        pool = multibot.SenderPool(limit=LIMIT, window=POOL_WINDOW, reaction_spacing=SPACING)
        pool.install(bot.bot.http, "p", bot.bot.user.id)
        for token in tokens:
            await pool.add_helper(token)
        bot._min_message_interval = 0.0  # what the app sets once the pool is running
        channel = discord.PartialMessageable(state=bot.bot._connection, id=CHANNEL)
        bot.qte_channel_id = CHANNEL
        bot.bot.get_channel = lambda i: channel
        typed = [server.add_message(CHANNEL, "tok-primary", "*evade*") for _ in range(PLAYERS)]

        async def reply(mid):  # what handle_*_qte_response does for one player, minus the game rules
            player_message = discord.PartialMessage(channel=channel, id=mid)
            await bot.webhook_send(content=f"❌ <@{mid}> **evade too slow!**")
            await bot.safe_add_reaction(player_message, "❌")

        started = time.monotonic()
        await asyncio.gather(*(reply(m) for m in typed))
        elapsed = time.monotonic() - started
        out = (elapsed, len(server.messages) - PLAYERS, sum(1 for r in server.reactions if r["status"] == 204),
               [r for r in server.requests if r["status"] == 429] + [r for r in server.reactions if r["status"] == 429])
        await pool.close()
        await bot.bot.close()
        await server.stop()
        module.flush_saves()
        return out

    return asyncio.run(scenario())


def test_twenty_players_answering_at_once_with_five_bots(tmp_path, monkeypatch):
    elapsed, messages, reactions, rate_limited = burst_of_replies(tmp_path, monkeypatch, helpers=4)
    assert (messages, reactions) == (PLAYERS, PLAYERS)  # every player got their message and their reaction
    assert rate_limited == []
    # 20 messages = 4 per bot x 5 bots: one round trip. 20 reactions = 4 per bot spaced 0.27 s: ~0.9 s.
    assert elapsed < 1.6, elapsed


def test_the_same_burst_with_one_bot_is_much_slower(tmp_path, monkeypatch):
    alone, *_ = burst_of_replies(tmp_path, monkeypatch, helpers=0)
    team, *_ = burst_of_replies(tmp_path, monkeypatch, helpers=4)
    assert alone > 2.5 * team, (alone, team)
