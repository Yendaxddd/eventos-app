"""Seeing what Discord answers: the request tracer, the 429 explanations, adapting to stricter reaction limits."""
import asyncio
import json
import sys
import time
from pathlib import Path

import discord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app import benchmark, diagnostics, multibot  # noqa: E402
from test_multibot import CHANNEL, World, burst, run  # noqa: E402


def test_requests_are_classified_by_what_they_do():
    c = diagnostics.classify
    base = "https://discord.com/api/v10"
    assert c("POST", f"{base}/channels/42/messages") == ("send", 42)
    assert c("PUT", f"{base}/channels/42/messages/7/reactions/%E2%9C%85/@me") == ("react", 42)
    assert c("PATCH", f"{base}/channels/42/messages/7") == ("edit", 42)
    assert c("DELETE", f"{base}/channels/42/messages/7") == ("delete", 42)
    assert c("POST", f"{base}/channels/42/messages/bulk-delete") == ("bulk", 42)
    assert c("GET", f"{base}/gateway") == ("ping", 0)
    assert c("GET", f"{base}/users/@me")[0] == "other"


def test_every_bots_requests_are_traced_with_discords_own_headers():
    async def scenario():
        async with World(helpers=1) as w:
            await burst(w, 8)
            return list(w.pool.tracer.events), dict(w.pool.tracer.observed)

    events, observed = run(scenario())
    sends = [e for e in events if e["kind"] == "send"]
    assert len(sends) == 8 and {e["status"] for e in sends} == {200}
    assert len({e["bot"] for e in sends}) == 2          # the main bot's session and the helper's, both watched
    assert all(e["limit"] == 5 and e["reset_after"] is not None and e["ms"] >= 0 for e in sends)
    assert {kind for _, kind in observed} == {"send"}


def test_a_429_is_recorded_explained_and_makes_the_bot_space_reactions_out():
    async def scenario():
        async with World(helpers=0, reaction_window=0.6) as w:    # stricter than the pool's 0.27 s plan
            message = await w.channel.send("qte")
            seen = []
            w.pool.tracer.listeners.append(lambda e: seen.append(e) if e["status"] == 429 else None)
            started = time.monotonic()
            await asyncio.gather(*(message.add_reaction(e) for e in ["⭐", "❗", "✅", "❌", "🔒", "💚"]))
            elapsed = time.monotonic() - started
            return seen, w.pool.primary.react_spacing, elapsed, len(w.server.messages[message.id]["reactions"])

    seen, spacing, elapsed, landed = run(scenario())
    assert landed == 6                                   # nothing lost
    assert seen and all(e["kind"] == "react" and e["reset_after"] is not None for e in seen)
    assert spacing >= 0.55                               # learned Discord's real spacing from the headers
    text = diagnostics.explain_429(seen[0])
    assert "reacción" in text and "ms" in text and "Discord pidió esperar" in text


def test_a_reaction_discord_gave_up_on_is_retried_not_lost():
    async def scenario():
        async with World(helpers=1) as w:
            message = await w.channel.send("qte")
            real = {s: s.endpoints.add_reaction for s in w.pool._all()}
            calls = []

            def flaky(sender):
                async def add(*args, **kwargs):
                    calls.append(sender.name)
                    if len(calls) <= 2:    # what discord.py raises after its 5 rate-limited tries
                        raise discord.HTTPException(type("R", (), {"status": 429, "reason": "x"})(), "rate limited")
                    return await real[sender](*args, **kwargs)
                return add

            for sender in w.pool._all():
                sender.endpoints = sender.endpoints._replace(add_reaction=flaky(sender))
            await message.add_reaction("⭐")
            return len(calls), len(w.server.messages[message.id]["reactions"]), sum(s.stats.failed for s in w.pool._all())

    calls, landed, failed = run(scenario())
    assert calls == 3 and landed == 1 and failed == 2


def test_after_many_clean_reactions_the_spacing_relaxes_again():
    async def scenario():
        async with World(helpers=0) as w:
            sender = w.pool.primary
            sender.react_spacing = 0.9
            for _ in range(60):
                w.pool._learn({"kind": "react", "bot": sender.name, "status": 204, "reset_after": 0.25})
            return sender.react_spacing

    assert run(scenario()) < 0.9


def test_a_429_that_is_not_ours_is_called_out():
    event = {"bot": "Bot#1", "kind": "send", "retry_after_ms": 1000, "reset_after_ms": 820, "scope": "user",
             "global": False, "ours": {"reservas": 2, "ventana_s": 5.3}}
    assert "820 ms" in diagnostics.explain_429(event) and "no fue por exceso nuestro" in diagnostics.explain_429(event)
    event["ours"]["reservas"] = 9
    assert "no fue por exceso nuestro" not in diagnostics.explain_429(event)
    assert "GLOBAL" in diagnostics.explain_429({**event, "global": True})


def test_the_loop_monitor_notices_a_blocked_event_loop():
    async def scenario():
        warnings = []
        monitor = diagnostics.LoopMonitor(on_warning=warnings.append)
        monitor.start()
        await asyncio.sleep(0.2)
        monitor.take_max()
        time.sleep(0.5)                  # something heavy running on the loop
        await asyncio.sleep(0.2)
        lag = monitor.take_max()
        monitor.stop()
        return lag, warnings

    lag, warnings = run(scenario())
    assert lag > 0.3 and warnings


def test_every_request_is_written_to_the_log_file(tmp_path):
    async def scenario():
        world = World(helpers=1)
        world.pool.trace_file = tmp_path / "requests.jsonl"
        async with world as w:
            await burst(w, 6)
            await w.pool.delete_many(CHANNEL, list(w.server.messages))

    run(scenario())
    rows = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sum(r["kind"] == "send" for r in rows) == 6 and any(r["kind"] in ("delete", "bulk") for r in rows)
    assert all({"t", "bot", "status", "ms"} <= set(r) for r in rows)


def test_the_report_carries_the_diagnosis():
    async def scenario():
        async with World(helpers=2, reaction_window=0.5) as w:
            return await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)

    report = run(scenario())
    trace = report["trace"]
    assert trace["requests"] > 40 and "reacciones" in trace["phases"]
    # the stricter reaction spacing (500 ms) was learned from the headers of the first reaction: no 429 at all
    assert trace["limited_total"] == 0 and report["reactions"]["failed"] == 0
    assert report["planned"]["react_spacing_ms"] >= 500
    text = "\n".join(benchmark.format_report(report))
    assert "DIAGNÓSTICO" in text and "Discord dice (mensaje)" in text and "Discord dice (reacción)" in text
    assert "Ningún 429" in text and "Carga del bot" in text


# ---- a 429 must not start a chain of 429s --------------------------------------------------------------
def test_push_back_delays_only_the_slots_that_have_not_come_yet():
    sender = multibot.Sender("s", multibot.Endpoints(*([None] * 5)))
    for at in (1.0, 2.0, 3.0, 4.0):
        sender.reserve("react", 9, at)
    moved = sender.push_back("react", 9, now=2.5, earliest=3.6)
    assert round(moved, 3) == 0.6
    assert list(sender._slots[("react", 9)]) == [1.0, 2.0, 3.6, 4.6]    # slots in the past stay as they were
    assert sender.push_back("react", 9, now=2.5, earliest=3.0) == 0.0 and sender.shifted("react", 9) == moved


def test_a_waiting_request_notices_that_its_turn_was_pushed_back():
    async def scenario():
        async with World(helpers=0) as w:
            pool, sender = w.pool, w.pool.primary
            t0 = time.monotonic()
            woke = []

            async def go(name):
                await pool._admit(sender, "react", CHANNEL)
                woke.append((name, time.monotonic() - t0))

            tasks = [asyncio.ensure_future(go(n)) for n in "abc"]     # planned at 0, +0.27, +0.54
            await asyncio.sleep(0.05)
            pool._learn({"kind": "react", "bot": sender.name, "status": 429, "channel": CHANNEL, "reset_after": 0.25})
            await asyncio.gather(*tasks)
            return dict(woke)

    woke = run(scenario())
    assert woke["a"] < 0.1
    assert woke["b"] >= 0.5 and woke["c"] >= woke["b"] + 0.25   # b waits out the retry plus a spacing, c keeps its gap


def test_pushing_back_cuts_the_chain_of_429s_caused_by_discordpys_own_retries(monkeypatch):
    async def trial():
        async with World(helpers=1, latency=0.05, reaction_jitter=0.12) as w:
            messages = [await w.channel.send(f"m{i}") for i in range(6)]
            await asyncio.gather(*(w.pool.add_reaction(CHANNEL, messages[i % 6].id, "⭐") for i in range(24)))
            return (len([r for r in w.server.reactions if r["status"] == 429]),
                    len([r for r in w.server.reactions if r["status"] == 204]))

    with_push = run(trial())
    monkeypatch.setattr(multibot.Sender, "push_back", lambda *args, **kwargs: 0.0)
    without_push = run(trial())
    assert with_push[1] == 24 == without_push[1]                  # every reaction lands either way
    assert with_push[0] < without_push[0] * 0.7, (with_push, without_push)


# ---- slow requests: new connection or not? ---------------------------------------------------------------
def test_each_request_says_whether_it_opened_a_connection():
    async def scenario():
        async with World(helpers=0) as w:
            seq = w.pool.tracer.seq
            await burst(w, 5)                 # five at once: five connections, nothing to reuse yet
            await asyncio.sleep(0.1)
            await burst(w, 5)                 # the same five connections are free again
            return w.pool.tracer.summary(seq)

    summary = run(scenario())
    conns = summary["connections"]
    assert conns["new"] >= 1 and conns["reused"] >= 5 and conns["new"] + conns["reused"] == 10
    assert summary["slowest"] == sorted(summary["slowest"], key=lambda r: r["ms"], reverse=True)
    assert all(r["conn"] in ("new", "reused") for r in summary["slowest"])


def test_the_report_names_a_slow_request_and_its_connection():
    report = {"bots": 2, "profile": "rapida", "senders": [], "bursts": [], "reactions": None, "sustained": None,
              "aborted": "", "errors": [], "planned": {"send_limit": 5, "send_window_ms": 5300, "react_spacing_ms": 300},
              "trace": {"requests": 10, "kinds": {}, "observed": {}, "limited": [], "limited_total": 0, "phases": {},
                        "connections": {"new": 2, "reused": 8, "connect_ms_max": 3012, "new_by_phase": {"ráfaga 2": 2}},
                        "slowest": [{"at_ms": 9000, "phase": "ráfaga 2", "bot": "Bot#1234", "kind": "send", "ms": 3647,
                                     "status": 200, "conn": "new", "connect_ms": 3012}]}}
    text = "\n".join(benchmark.format_report(report))
    assert "2 nuevas (2 en ráfaga 2)" in text and "3647 ms" in text and "3012 ms solo en conectar" in text
