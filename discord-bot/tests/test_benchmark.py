"""The performance test and the capacity model."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import discord  # noqa: E402

from eventos_app import benchmark, capacity  # noqa: E402
from test_multibot import CHANNEL, World, run  # noqa: E402


# ---- the model -----------------------------------------------------------------------------------
def test_every_bot_adds_the_same_capacity():
    one, five = capacity.capacity(1), capacity.capacity(5)
    assert five.players == 5 * one.players
    assert five.messages_per_minute == 5 * one.messages_per_minute
    assert 55 <= one.messages_per_minute <= 60  # Discord: 5 per 5 s


def test_the_limiting_resource_is_named():
    assert capacity.capacity(3).limiting in {"mensajes", "ediciones"}
    assert capacity.capacity(3, messages_per_player=0, edits_per_player=0, reactions_per_player=1).limiting == "reacciones"


def test_a_longer_deadline_lets_in_more_players_only_once_a_new_window_opens():
    short, long = capacity.capacity(2, deadline=3.0), capacity.capacity(2, deadline=6.0)
    assert long.players == 2 * short.players
    assert capacity.capacity(2, deadline=3.0).players == capacity.capacity(2, deadline=5.0).players


def test_replies_that_need_less_traffic_fit_more_players():
    assert capacity.capacity(4, messages_per_player=0.5, edits_per_player=0.5).players == 2 * capacity.capacity(4).players


def test_the_table_has_a_row_per_bot():
    rows = capacity.table(4)
    assert [r["bots"] for r in rows] == [1, 2, 3, 4] and rows[0]["players_3s"] < rows[3]["players_3s"]


# ---- the test itself ---------------------------------------------------------------------------------
def test_it_measures_everything_and_leaves_the_channel_clean():
    lines = []

    async def scenario():
        async with World(helpers=2) as w:
            report = await benchmark.run(w.pool, CHANNEL, profile="rapida", say=lines.append, sustained_seconds=2.0)
            return report, len(w.server.messages)

    report, left = run(scenario())
    assert report["bots"] == 3 and all(not s["error"] and s["rtt_ms"] > 0 for s in report["senders"])
    assert [b["size"] for b in report["bursts"]] == [15, 21]
    assert report["reactions"]["count"] > 0 and report["sustained"]["messages"] > 0
    assert report["rate_limits"] == 0 and not report["aborted"]
    assert left == 0  # every test message was deleted
    assert set(report["capacity"]) == {"2", "3", "5"} and report["capacity"]["3"]["players"] > 0
    text = "\n".join(benchmark.format_report(report))
    assert "PRUEBA DE RENDIMIENTO" in text and "Ráfaga de 15 mensajes" in text and "Cada bot auxiliar" in text
    assert any("Borrando" in line for line in lines)


def test_a_bot_that_cannot_write_is_reported_and_the_test_goes_on_without_it():
    async def scenario():
        async with World(helpers=2) as w:
            w.server.deny("tok-h0", CHANNEL)
            report = await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)
            return report, len(w.server.messages)

    report, left = run(scenario())
    errors = [s["error"] for s in report["senders"]]
    assert errors.count("") == 2 and any("no puede escribir" in e for e in errors)
    assert report["bursts"][0]["size"] == 10  # sized for the two bots that work
    assert left == 0


def test_it_can_be_cancelled_and_still_cleans_up():
    async def scenario():
        async with World(helpers=1) as w:
            stop = asyncio.Event()
            stop.set()
            report = await benchmark.run(w.pool, CHANNEL, say=lambda _: None, stop=stop)
            return report, len(w.server.messages)

    report, left = run(scenario())
    assert report["aborted"] == "cancelada" and left == 0


def test_it_never_posts_more_than_the_cap(monkeypatch):
    monkeypatch.setattr(benchmark, "MAX_MESSAGES", 12)

    async def scenario():
        async with World(helpers=4) as w:
            report = await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)
            return report

    report = run(scenario())
    assert all(b["size"] <= 6 for b in report["bursts"])


def test_the_first_burst_is_not_slowed_by_the_latency_phase():
    # phase 1 uses 3 slots per bot; the burst must wait for them to come back instead of spilling into the next window
    async def scenario():
        async with World(helpers=2) as w:
            return await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)

    report = run(scenario())
    first = report["bursts"][0]
    assert first["size"] == 15 and first["failed"] == 0
    assert first["last_ms"] < 600, first          # one round trip or so, not a whole window (1 s here)
    assert first["max_wait_ms"] < 100, first      # nobody had to queue
    assert report["rate_limits"] == 0


def test_the_overflow_burst_shows_how_much_of_the_tail_is_queueing():
    async def scenario():
        async with World(helpers=1) as w:
            return await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)

    report = run(scenario())
    second = report["bursts"][1]          # 14 messages over 2 bots that take 10 per window
    assert second["max_wait_ms"] > 500 and second["last_ms"] >= second["max_wait_ms"]
    assert "esperando turno" in "\n".join(benchmark.format_report(report))


def test_the_report_is_ready_before_the_cleanup_starts():
    seen = {}

    async def scenario():
        async with World(helpers=1) as w:
            def on_report(report):
                seen["messages"] = len(w.server.messages)
                seen["capacity"] = "capacity" in report and report["cleanup"] is None

            report = await benchmark.run(w.pool, CHANNEL, say=lambda _: None, on_report=on_report, sustained_seconds=0)
            return report, len(w.server.messages)

    report, left = run(scenario())
    assert seen["messages"] > 20 and seen["capacity"]   # the test messages were still there
    assert left == 0 and report["cleanup"]["deleted"] == report["cleanup"]["requested"] > 20


def test_a_failing_phase_keeps_the_report_and_still_cleans_up():
    async def scenario():
        async with World(helpers=1) as w:
            async def boom(*args, **kwargs):
                raise discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "kaboom")

            w.pool.add_reaction = boom
            report = await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)
            return report, len(w.server.messages)

    report, left = run(scenario())
    assert report["reactions"]["failed"] == report["reactions"]["count"] > 0
    assert report["bursts"] and report["capacity"] and any("500" in e for e in report["errors"]), report["errors"]
    assert left == 0
    assert "✗" in "\n".join(benchmark.format_report(report))


# ---- deleting many messages ----------------------------------------------------------------------------
def test_with_manage_messages_everything_goes_in_one_call():
    async def scenario():
        async with World(helpers=2) as w:
            w.server.manage.add("tok-primary")
            ids = [m.id for m in await asyncio.gather(*(w.channel.send(f"m{i}") for i in range(30)))]
            result = await w.pool.delete_many(CHANNEL, ids)
            return result, len(w.server.messages), w.server.bulk_calls

    result, left, bulk = run(scenario())
    assert left == 0 and result["deleted"] == 30 and result["bulk"] == 30 and result["failed"] == 0
    assert bulk == [("tok-primary", 30)]


def test_without_manage_messages_each_bot_deletes_its_own_in_parallel_without_wasted_calls():
    async def scenario():
        async with World(helpers=2, delete_limit=5, delete_window=1.0) as w:
            ids = [m.id for m in await asyncio.gather(*(w.channel.send(f"m{i}") for i in range(30)))]
            result = await w.pool.delete_many(CHANNEL, ids)
            return result, len(w.server.messages), w.server.delete_attempts, w.server.bulk_calls

    result, left, attempts, bulk = run(scenario())
    assert left == 0 and result["deleted"] == 30 and result["failed"] == 0
    assert len(bulk) == 1                          # asked once, refused, and not asked again
    assert not [a for a in attempts if a[1] == 403]   # every delete went straight to the author
    assert result["seconds"] < 4.0                 # 10 each at 5 per second per bot, all three at once


def test_bulk_refusal_is_remembered_and_unknown_authors_are_found():
    async def scenario():
        async with World(helpers=1) as w:
            mine = [w.server.add_message(CHANNEL, "tok-h0") for _ in range(4)]   # the pool never saw these
            await w.pool.delete_many(CHANNEL, mine[:2])
            await w.pool.delete_many(CHANNEL, mine[2:])
            return len(w.server.messages), w.server.bulk_calls

    left, bulk = run(scenario())
    assert left == 0
    assert bulk == [("tok-primary", 2)]   # refused once, and never asked again
