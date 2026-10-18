"""Webhook lanes: one webhook per bot in the event channel, used as extra senders for plain messages."""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import discord
from discord.http import MultipartParameters

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app import benchmark, diagnostics, multibot, webhooks  # noqa: E402
from test_multibot import CHANNEL, LIMIT, WINDOW, World, burst, run  # noqa: E402

OTHER = 777


async def with_lanes(helpers: int = 1, channel: int = CHANNEL, **options) -> World:
    world = World(helpers=helpers, **options)
    await world.__aenter__()
    world.server.can_manage_webhooks.update(["tok-primary", *world.helper_tokens])
    await world.pool.ensure_lanes(channel)
    return world


def hooks_in(world: World, channel: int = CHANNEL) -> list[dict]:
    return [h for h in world.server.webhooks.values() if h["channel"] == channel]


# ---- registering: one per bot, found again, per channel ----------------------------------------------------------
def test_every_bot_registers_exactly_one_webhook_and_it_is_found_again():
    async def scenario():
        w = await with_lanes(helpers=2)
        try:
            first = sorted(h["creator"] for h in hooks_in(w))
            lanes = len(w.pool.lanes)
            await w.pool.ensure_lanes(CHANNEL)         # same channel again: nothing new
            await w.pool.ensure_lanes(CHANNEL)
            return first, lanes, len(hooks_in(w)), sorted(l.webhook_id for l in w.pool.lanes), sorted(w.pool.lane_ids)
        finally:
            await w.__aexit__(None, None, None)

    first, lanes, total, lane_ids, ids = run(scenario())
    assert first == [100, 101, 102] and lanes == 3 and total == 3     # a bot never makes a second one
    assert lane_ids == ids and len(ids) == 3                          # what the bot must not take for players


def test_after_a_restart_the_stored_webhook_is_reused(tmp_path):
    async def scenario():
        w = World(helpers=1)
        w.pool.lane_store = webhooks.LaneStore(tmp_path / "lanes.json")
        await w.__aenter__()
        try:
            w.server.can_manage_webhooks.update(["tok-primary", "tok-h0"])
            await w.pool.ensure_lanes(CHANNEL)
            created = len(hooks_in(w))
            fresh = multibot.SenderPool(limit=LIMIT, window=WINDOW)          # a new run of the app
            fresh.lane_store = webhooks.LaneStore(tmp_path / "lanes.json")
            fresh._http, fresh.primary = w.pool._http, w.pool.primary
            fresh.helpers = w.pool.helpers
            await fresh.ensure_lanes(CHANNEL)
            return created, len(hooks_in(w)), len(fresh.lanes)
        finally:
            await w.__aexit__(None, None, None)

    assert run(scenario()) == (2, 2, 2)


def test_without_the_stored_file_a_bot_finds_its_old_webhook_by_name():
    async def scenario():
        w = await with_lanes(helpers=1)
        try:
            w.pool.lane_store = webhooks.LaneStore()          # the file was lost
            await w.pool.ensure_lanes(CHANNEL)
            return len(hooks_in(w)), len(w.pool.lanes)
        finally:
            await w.__aexit__(None, None, None)

    assert run(scenario()) == (2, 2)


def test_changing_the_channel_registers_one_per_bot_there_and_drops_the_old_lanes():
    async def scenario():
        w = await with_lanes(helpers=1)
        try:
            old_ids = set(w.pool.lane_ids)
            await w.pool.ensure_lanes(OTHER)
            moved = (len(hooks_in(w, CHANNEL)), len(hooks_in(w, OTHER)), {l.channel for l in w.pool.lanes},
                     old_ids.isdisjoint(w.pool.lane_ids))
            await w.pool.ensure_lanes(CHANNEL)               # coming back reuses the first ones
            return moved, len(hooks_in(w, CHANNEL)), len(hooks_in(w, OTHER)), set(w.pool.lane_ids) == old_ids
        finally:
            await w.__aexit__(None, None, None)

    moved, here, there, same = run(scenario())
    assert moved == (2, 2, {OTHER}, True) and (here, there) == (2, 2) and same


def test_a_bot_without_permission_has_no_lane_and_says_why_while_the_others_work():
    async def scenario():
        w = World(helpers=2)
        await w.__aenter__()
        try:
            w.server.can_manage_webhooks.update(["tok-primary", "tok-h1"])
            results = await w.pool.ensure_lanes(CHANNEL)
            notes = {b.name: b.lane_note for b in w.pool._bots()}
            return results, notes, len(w.pool.lanes)
        finally:
            await w.__aexit__(None, None, None)

    results, notes, lanes = run(scenario())
    assert lanes == 2 and sorted(r["ok"] for r in results) == [False, True, True]
    assert any("Gestionar webhooks" in n for n in notes.values()) and sum(n.startswith("ok") for n in notes.values()) == 2


def test_a_full_channel_is_reported_instead_of_failing():
    async def scenario():
        w = World(helpers=2, max_webhooks=2)
        await w.__aenter__()
        try:
            w.server.can_manage_webhooks.update(["tok-primary", *w.helper_tokens])
            await w.pool.ensure_lanes(CHANNEL)
            return len(hooks_in(w)), len(w.pool.lanes), [b.lane_note for b in w.pool._bots()]
        finally:
            await w.__aexit__(None, None, None)

    total, lanes, notes = run(scenario())
    assert total == 2 and lanes == 2 and any("15 webhooks" in n for n in notes)


def test_webhooks_can_be_turned_off():
    async def scenario():
        w = World(helpers=1)
        w.pool.webhooks_enabled = False
        await w.__aenter__()
        try:
            w.server.can_manage_webhooks.update(["tok-primary", "tok-h0"])
            await w.pool.ensure_lanes(CHANNEL)
            return len(w.server.webhooks), len(w.pool.lanes)
        finally:
            await w.__aexit__(None, None, None)

    assert run(scenario()) == (0, 0)


def test_the_webhook_shows_the_bots_name_without_the_words_discord_refuses():
    assert webhooks.lane_name("Events and fun Bot") == "Events and fun Bot"
    assert "discord" not in webhooks.lane_name("My Discord Clyde Bot").lower()
    assert webhooks.avatar_data(b"\x89PNG....").startswith("data:image/png;base64,") and webhooks.avatar_data(None) is None


# ---- sending through the lanes -------------------------------------------------------------------------------------
def test_a_burst_that_the_bots_cannot_take_overflows_into_the_webhooks_without_waiting():
    async def scenario():
        w = await with_lanes(helpers=1)          # 2 bots x 5 + ONE shared webhook limit of 5 = 15 messages in one turn
        try:
            elapsed = await burst(w, 15)
            by_hooks = sum(1 for m in w.server.messages.values() if m.get("webhook_id"))
            return elapsed, by_hooks, [r for r in w.server.requests if r["status"] == 429], \
                [r for r in w.server.webhook_requests if r["status"] == 429]
        finally:
            await w.__aexit__(None, None, None)

    elapsed, by_hooks, bot_429, hook_429 = run(scenario())
    assert by_hooks == 5 and not bot_429 and not hook_429
    assert elapsed < 0.5 * WINDOW, elapsed       # without lanes 15 messages need 2 windows


def test_bots_are_preferred_and_lanes_only_take_what_the_bots_have_no_room_for():
    async def scenario():
        w = await with_lanes(helpers=1)
        try:
            await burst(w, 8)                       # fits in the two bots
            return sum(1 for m in w.server.messages.values() if m.get("webhook_id"))
        finally:
            await w.__aexit__(None, None, None)

    assert run(scenario()) == 0


def test_the_lane_learns_its_real_limit_from_discords_headers():
    async def scenario():
        w = await with_lanes(helpers=0, webhook_limit=3, webhook_window=0.8)    # stricter than the 5 / 2.5 s assumed
        try:
            await burst(w, 8)                       # 5 by the bot, 3 by the lane
            lane = w.pool.lanes[0]
            return lane.send_limit, round(lane.send_window, 2), len(w.server.messages)
        finally:
            await w.__aexit__(None, None, None)

    limit, window, delivered = run(scenario())
    assert limit == 3 and 0.9 <= window <= 1.1 and delivered == 8     # 0.8 s + 0.2 s margin


def test_a_429_on_a_webhook_moves_what_was_planned_behind_it():
    async def scenario():
        w = await with_lanes(helpers=0, webhook_limit=5, webhook_window=3.0)     # slower than the 2.5 s assumed
        try:
            elapsed = await burst(w, 12)            # 5 bot + 5 lane at once, the last 2 wait for the lane's window
            lane = w.pool.lanes[0]
            return elapsed, len(w.server.messages), lane.send_window
        finally:
            await w.__aexit__(None, None, None)

    elapsed, delivered, window = run(scenario())
    assert delivered == 12 and window >= 3.0       # nothing lost; the lane widened its window after the 429


def test_replies_and_buttons_never_go_through_a_webhook():
    async def scenario():
        w = await with_lanes(helpers=0)
        try:
            reply = MultipartParameters(payload={"content": "re", "message_reference": {"message_id": "1"}},
                                        multipart=None, files=None)
            for _ in range(8):                      # more than the one bot takes in a window: a lane would be next
                await w.primary.http.send_message(CHANNEL, params=reply)
            return len(w.server.webhook_requests), len(w.server.sent_by("tok-primary"))
        finally:
            await w.__aexit__(None, None, None)

    hooks_used, by_bot = run(scenario())
    assert hooks_used == 0 and by_bot == 8


def test_reactions_never_use_a_webhook_but_work_on_webhook_messages():
    async def scenario():
        w = await with_lanes(helpers=0)
        try:
            messages = await asyncio.gather(*(w.channel.send(f"m{i}") for i in range(8)))
            on_hook = [m for m in messages if w.server.messages[m.id].get("webhook_id")]
            await asyncio.gather(*(m.add_reaction("⭐") for m in on_hook))
            return len(on_hook), len([r for r in w.server.reactions if r["status"] == 204])
        finally:
            await w.__aexit__(None, None, None)

    on_hook, reacted = run(scenario())
    assert on_hook >= 3 and reacted == on_hook


def test_edits_and_deletes_go_to_whoever_wrote_the_message_webhooks_included():
    async def scenario():
        w = await with_lanes(helpers=1)
        try:
            messages = await asyncio.gather(*(w.channel.send(f"m{i}") for i in range(20)))
            await asyncio.gather(*(m.edit(content=f"edited {m.id}") for m in messages))
            ok = all(w.server.messages[m.id]["edited_by"] ==
                     (f"webhook:{w.server.messages[m.id]['webhook_id']}" if w.server.messages[m.id].get("webhook_id")
                      else w.server.messages[m.id]["author_token"]) for m in messages)
            await asyncio.gather(*(m.delete() for m in messages))
            return ok, len(w.server.messages), any(w.server.messages.get(m.id) for m in messages)
        finally:
            await w.__aexit__(None, None, None)

    ok, left, _ = run(scenario())
    assert ok and left == 0


def test_a_webhook_deleted_by_hand_is_dropped_and_the_message_still_arrives():
    async def scenario():
        w = await with_lanes(helpers=0)
        try:
            lane = w.pool.lanes[0]
            del w.server.webhooks[lane.webhook_id]              # someone deleted it in Discord
            w.pool.primary.penalty_until = time.monotonic() + 0.3   # make the lane the first choice
            await burst(w, 7)
            return len(w.server.messages), len(w.pool.lanes), w.pool.primary.lane_note, w.pool.lane_ids
        finally:
            await w.__aexit__(None, None, None)

    delivered, lanes, note, ids = run(scenario())
    assert delivered == 7 and lanes == 0 and not ids and "borrado" in note


def test_removing_a_helper_removes_its_lane():
    async def scenario():
        w = await with_lanes(helpers=1)
        try:
            await w.pool.remove_helper(w.pool.helpers[0])
            return len(w.pool.lanes), len(w.pool.lane_ids)
        finally:
            await w.__aexit__(None, None, None)

    assert run(scenario()) == (1, 1)


# ---- diagnostics: the token never leaks --------------------------------------------------------------------------------
def test_webhook_requests_are_traced_by_webhook_and_the_token_is_never_logged(tmp_path, caplog):
    async def scenario():
        world = World(helpers=0, webhook_limit=2, webhook_window=1.0)    # small, so a 429 is logged by discord.py
        world.pool.trace_file = tmp_path / "requests.jsonl"
        await world.__aenter__()
        try:
            world.server.can_manage_webhooks.add("tok-primary")
            await world.pool.ensure_lanes(CHANNEL)
            with caplog.at_level(logging.WARNING, logger="discord.http"):
                lane = world.pool.lanes[0]
                for _ in range(3):                            # the third is a real 429 that discord.py logs
                    await lane.endpoints.send_message(CHANNEL, params=multibot._plain_params("x"))
            token = world.server.webhooks[lane.webhook_id]["token"]
            events = [e for e in world.pool.tracer.events if e["kind"] == "wsend"]
            return events, token
        finally:
            await world.__aexit__(None, None, None)

    events, token = run(scenario())
    assert len(events) >= 3 and all(e["webhook"] for e in events) and any(e["status"] == 429 for e in events)
    assert token not in (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    assert token not in caplog.text and "/webhooks/" in caplog.text and "***" in caplog.text


# ---- the performance test with lanes -----------------------------------------------------------------------------------
def test_the_performance_test_counts_the_webhooks_and_cleans_up_after_them():
    async def scenario():
        w = await with_lanes(helpers=1)
        try:
            report = await benchmark.run(w.pool, CHANNEL, say=lambda _: None, sustained_seconds=0)
            return report, len(w.server.messages)
        finally:
            await w.__aexit__(None, None, None)

    report, left = run(scenario())
    assert (report["bots"], report["lanes"]) == (2, 2)
    assert report["bursts"][0]["size"] == 15 and report["bursts"][0]["max_wait_ms"] < 100     # all in one turn
    assert report["reactions"]["failed"] == 0 and report["capacity"]["3"]["lanes"] == 2
    assert left == 0 and report["cleanup"]["deleted"] == report["cleanup"]["requested"]
    text = "\n".join(benchmark.format_report(report))
    assert "2 bots + 2 webhooks" in text and "(webhook)" in text and "mensaje por webhook" in text
    assert "comparten UN solo límite" in text and "reacciones siguen necesitando un bot" in text


def test_lanes_add_messages_but_not_reactions_to_the_capacity_model():
    from eventos_app import capacity
    bots = capacity.capacity(5, deadline=3.0)
    with_lanes = capacity.capacity(5, lanes=5, deadline=3.0)
    assert with_lanes.messages_in_deadline > bots.messages_in_deadline
    assert with_lanes.reactions_in_deadline == bots.reactions_in_deadline
    assert with_lanes.messages_per_minute > 1.3 * bots.messages_per_minute
    # the webhooks of a channel are ONE bucket: more of them add nothing
    assert capacity.capacity(5, lanes=1, deadline=3.0).messages_per_minute == with_lanes.messages_per_minute


# ---- the app side ----------------------------------------------------------------------------------------------------
def test_the_runner_registers_the_event_channel_webhooks_and_reports_who_could_not():
    from types import SimpleNamespace as NS
    from eventos_app import console_bridge, runner

    lines: list[str] = []
    console_bridge.console.set_sink(lambda segments: lines.append("".join(seg.text for seg in segments)))

    async def scenario():
        w = World(helpers=1)
        await w.__aenter__()
        try:
            w.server.can_manage_webhooks.add("tok-primary")          # the helper bot was never given the permission
            r = runner.BotRunner()
            r._pool, r._app = w.pool, NS(qte_channel_id=CHANNEL)
            first = await r._sync_lanes()
            off = await r._sync_lanes(enabled=False)
            return first, off, len(w.pool.lanes)
        finally:
            await w.__aexit__(None, None, None)
            console_bridge.console.set_sink(None)

    first, off, lanes_after_off = run(scenario())
    text = "\n".join(lines)
    assert first["ok"] and first["lanes"] == 1 and len(first["failed"]) == 1
    assert "1 webhook de envío listo" in text and "Gestionar webhooks" in text
    assert off["disabled"] and lanes_after_off == 0


def test_the_bot_ignores_its_own_webhooks_but_not_tupperbox():
    import advanced_qte_hp_system_debug as bot_module
    source = Path(bot_module.__file__).read_text(encoding="utf-8")
    assert "message.webhook_id not in self.own_webhook_ids" in source
    assert "msg.webhook_id not in self.own_webhook_ids" in source


# ---- all the webhooks of a channel share ONE limit (what a real run showed: 429 with scope "shared") --------------
def test_five_webhooks_are_paced_as_one_shared_limit_so_none_of_them_gets_a_429():
    async def scenario():
        w = await with_lanes(helpers=4)          # 5 bots + 5 webhooks
        try:
            elapsed = await burst(w, 40)         # 25 for the bots, 5 for the shared webhook limit, 10 have to wait
            delivered = len(w.server.messages)
            return elapsed, delivered, [r for r in w.server.webhook_requests if r["status"] == 429], \
                [r for r in w.server.requests if r["status"] == 429], len({l._slots is w.pool._lane_slots for l in w.pool.lanes})
        finally:
            await w.__aexit__(None, None, None)

    elapsed, delivered, hook_429, bot_429, one_ledger = run(scenario())
    assert delivered == 40 and not hook_429 and not bot_429 and one_ledger == 1


def test_a_message_discordpy_gave_up_on_is_sent_again_not_lost():
    async def scenario():
        w = await with_lanes(helpers=0)
        try:
            lane = w.pool.lanes[0]
            calls = []

            async def always_limited(*args, **kwargs):          # discord.py raises this after 5 rate-limited tries
                calls.append(1)
                raise discord.HTTPException(type("R", (), {"status": 429, "reason": "x"})(), "The resource is being rate limited.")

            lane.endpoints = lane.endpoints._replace(send_message=always_limited)
            await burst(w, 12)                       # 5 would go to the bot, 5 to the lane (which fails), 2 wait
            return len(w.server.messages), len(calls), len(w.server.sent_by("tok-primary"))
        finally:
            await w.__aexit__(None, None, None)

    delivered, lane_attempts, by_bot = run(scenario())
    assert delivered == 12 and by_bot == 12 and lane_attempts >= 1       # every message reached Discord, via the bot


def test_webhook_429s_do_not_stop_the_performance_test():
    counter = benchmark._RateLimitCounter()
    for text in ("We are being rate limited. POST https://x/webhooks/1/***/ responded with 429. Retrying in 1.00 seconds.",
                 "We are being rate limited. PUT https://x/channels/1/messages/2/reactions/a/@me responded with 429."):
        counter.emit(logging.LogRecord("discord.http", logging.WARNING, "", 0, text, (), None))
    assert (counter.webhooks, counter.reactions, counter.count) == (1, 1, 0)
