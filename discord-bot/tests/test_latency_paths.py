"""The bot's hot paths: things that used to add latency (or unfairness) between a QTE and its result."""
import asyncio
import datetime as dt
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eventos_app import paths  # noqa: E402

UTC = dt.timezone.utc


def bot_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module

    bot = object.__new__(module.AdvancedQTEBot)
    bot.latency_offset = 0.25
    bot.character_registry = {}
    bot._tupper_seen, bot._tupper_waiters = {}, {}
    bot.active_qtes = {}
    return bot, module


def at(seconds: float) -> dt.datetime:
    return dt.datetime(2026, 1, 1, tzinfo=UTC) + dt.timedelta(seconds=seconds)


# ---- fair reaction time -----------------------------------------------------------------------
def test_reaction_time_uses_discords_clock_not_ours(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    qte = {"message": NS(created_at=at(10.0)), "start": at(7.0)}  # we started 3 s earlier: sending was slow
    reply = NS(created_at=at(11.2))
    # the player saw the QTE at 10.0 and answered at 11.2: 1.2 s, however long our send/queue took
    assert bot.qte_response_time(reply, qte, now=at(14.0)) == 1.2


def test_reaction_time_falls_back_to_the_old_formula_when_the_qte_message_is_unknown(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    qte = {"start": at(10.0)}
    assert bot.qte_response_time(NS(created_at=at(11.0)), qte, now=at(11.5)) == 1.5 - 0.25


def test_a_reply_cannot_come_before_its_qte(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    qte = {"message": NS(created_at=at(10.0)), "start": at(10.0)}
    assert bot.qte_response_time(NS(created_at=at(9.9)), qte, now=at(10.5)) == 0.0


def test_webhook_send_remembers_the_qte_message(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    sent = NS(id=1, created_at=at(1.0))

    class Channel:
        id = 5

        async def send(self, **kwargs):
            return sent

    bot.qte_channel_id = 5
    bot.bot = NS(get_channel=lambda i: Channel())
    bot._channel_last_send, bot._rate_limit_backoff, bot._min_message_interval = {}, {}, 0.0
    bot.active_qtes = {7: {"mode": "combo"}}

    assert asyncio.run(bot.webhook_send(content="x", qte_id=7)) is sent
    assert bot.active_qtes[7]["message"] is sent


# ---- reactions to player replies ----------------------------------------------------------------
def test_players_without_characters_get_their_reaction_without_waiting(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    original = NS(created_at=at(0))
    started = time.monotonic()
    assert asyncio.run(bot.find_tupper_message(None, 42, original)) is original
    assert time.monotonic() - started < 0.05  # used to sleep 0.15 s and ask Discord for the history


def test_tupperbox_replies_are_picked_up_by_event_not_by_polling(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    bot.character_registry = {"Sukuna": 42}
    original = NS(created_at=at(0))
    webhook = NS(created_at=at(0.3), author=NS(display_name="Sukuna"))

    async def scenario():
        waiting = asyncio.create_task(bot.find_tupper_message(None, 42, original))
        await asyncio.sleep(0.05)
        bot._note_webhook_message(webhook)  # on_message sees Tupperbox's webhook message arrive
        return await asyncio.wait_for(waiting, 1)

    started = time.monotonic()
    assert asyncio.run(scenario()) is webhook
    assert time.monotonic() - started < 0.3


def test_a_tupper_message_that_arrived_first_is_used_right_away(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    bot.character_registry = {"Sukuna": 42}
    webhook = NS(created_at=at(0.2), author=NS(display_name="Sukuna"))
    bot._note_webhook_message(webhook)
    assert asyncio.run(bot.find_tupper_message(None, 42, NS(created_at=at(0)))) is webhook


def test_no_tupper_message_means_the_original_after_a_short_wait(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    bot.character_registry = {"Sukuna": 42}
    original = NS(created_at=at(0))
    started = time.monotonic()
    assert asyncio.run(bot.find_tupper_message(None, 42, original, timeout=0.1)) is original
    assert 0.09 < time.monotonic() - started < 0.4
    assert bot._tupper_waiters.get(42) == []  # no waiter left behind


def test_webhook_messages_of_unregistered_characters_are_ignored(tmp_path, monkeypatch):
    bot, _ = bot_shell(tmp_path, monkeypatch)
    bot._note_webhook_message(NS(created_at=at(0), author=NS(display_name="Stranger")))
    assert bot._tupper_seen == {}


# ---- HP bars -----------------------------------------------------------------------------------
def test_hp_bars_are_edited_concurrently_without_fetching_or_sleeping(tmp_path, monkeypatch):
    bot, module = bot_shell(tmp_path, monkeypatch)
    edits = []

    class FakePartialMessage:
        def __init__(self, channel, id):
            self.id = id

        async def edit(self, **kwargs):
            await asyncio.sleep(0.05)  # one round trip
            edits.append(self.id)

    class Thread:
        async def fetch_message(self, *a):
            raise AssertionError("fetching the message first doubles the requests")

    monkeypatch.setattr(module.discord, "PartialMessage", FakePartialMessage)
    bot._hp_update_interval = 0.0
    bot.hp_bar_messages = {f"p{i}": 1000 + i for i in range(10)}
    bot._pending_hp_updates = {f"p{i}": (Thread(), f"embed{i}") for i in range(10)}

    started = time.monotonic()
    asyncio.run(bot._flush_hp_updates())
    elapsed = time.monotonic() - started
    assert sorted(edits) == [1000 + i for i in range(10)]
    assert elapsed < 0.3  # in parallel: ~1 round trip (before: 10 x (fetch + edit + 0.3 s sleep) = 4 s+)


def test_a_deleted_hp_bar_message_is_sent_again(tmp_path, monkeypatch):
    bot, module = bot_shell(tmp_path, monkeypatch)
    import discord

    class Gone:
        def __init__(self, channel, id):
            pass

        async def edit(self, **kwargs):
            raise discord.NotFound(NS(status=404, reason="Not Found"), "Unknown Message")

    monkeypatch.setattr(module.discord, "PartialMessage", Gone)
    sent = []

    async def safe_send(thread, embed=None, **kw):
        sent.append(embed)
        return NS(id=555)

    bot.safe_send = safe_send
    bot._hp_update_interval = 0.0
    bot.hp_bar_messages = {"p": 1}
    bot._pending_hp_updates = {"p": (object(), "embed")}
    asyncio.run(bot._flush_hp_updates())
    assert sent == ["embed"] and bot.hp_bar_messages["p"] == 555


# ---- saving ---------------------------------------------------------------------------------------
def test_saving_is_done_by_a_writer_thread_and_is_atomic(tmp_path, monkeypatch):
    _, module = bot_shell(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data")
    module.save_data("player_stats", {"1": {"hp": 10}})
    module.save_data("player_stats", {"1": {"hp": 20}})  # a second save of the same file queues behind the first
    module.flush_saves()
    target = tmp_path / "data" / "player_stats.json"
    assert '"hp": 20' in target.read_text(encoding="utf-8")
    assert list((tmp_path / "data").glob("*.tmp")) == []  # temp files never linger
    assert module.load_data("player_stats", {}) == {1: {"hp": 20}}  # ids come back as ints, as before


def test_loading_right_after_saving_sees_the_new_data(tmp_path, monkeypatch):
    _, module = bot_shell(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data2")
    module.save_data("channel_config", {"qte_channel_id": 99})
    assert module.load_data("channel_config", None) == {"qte_channel_id": 99}  # load flushes pending writes


def test_saving_does_not_block_the_caller(tmp_path, monkeypatch):
    _, module = bot_shell(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path / "data3")
    real_replace = module.os.replace

    def slow_replace(a, b):
        time.sleep(0.2)  # an antivirus holding the file
        return real_replace(a, b)

    monkeypatch.setattr(module.os, "replace", slow_replace)
    started = time.monotonic()
    module.save_data("x", {"a": 1})
    assert time.monotonic() - started < 0.1  # the event loop doesn't wait for the disk
    module.flush_saves()
    assert (tmp_path / "data3" / "x.json").exists()
