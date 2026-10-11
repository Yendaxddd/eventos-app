"""The performance test and the capacity model."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
