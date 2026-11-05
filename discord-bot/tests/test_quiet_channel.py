"""The channel stays quiet for who plays from the Activity: no reactions, no message for each answer; the player is told on their screen.
Whoever plays from the chat keeps the messages. The real bot's routing, and the real bridge delivering the notices."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app import paths  # noqa: E402
from eventos_app.activity.qte import ActivityInput  # noqa: E402
from test_activity_play import Rig, frame, run  # noqa: E402


class Notifier:
    """What the bridge offers the bot: who is inside the Activity and a way to tell them something."""

    def __init__(self, inside=()):
        self.inside, self.told = set(inside), []

    def has_player(self, user_id):
        return user_id in self.inside

    def notify(self, who, kind, data):
        self.told.append((who, kind, data))


def real_bot(tmp_path, monkeypatch, mode=None):
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.setenv("EVENTOS_RESET_ON_START", "0")
    monkeypatch.setenv("EVENTOS_HOTKEYS", "0")
    if mode is None:
        monkeypatch.delenv("EVENTOS_FEEDBACK", raising=False)
    else:
        monkeypatch.setenv("EVENTOS_FEEDBACK", mode)
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module

    bot = module.AdvancedQTEBot()
    sent = []

    async def webhook_send(content=None, embed=None, file=None, qte_id=None):
        sent.append((content, embed))
        return "the message"

    bot.webhook_send = webhook_send
    return bot, sent, module


def test_in_auto_mode_who_is_in_the_activity_hears_it_there_and_the_others_in_the_channel(tmp_path, monkeypatch):
    bot, sent, module = real_bot(tmp_path, monkeypatch)
    assert bot.feedback_mode == "auto" and bot.activity_notify is None
    asyncio.run(bot.feedback(1, "evade_slow", "❌ slow", ms=900))
    assert sent == [("❌ slow", None)]                                           # no Activity running: the channel, as always
    bot.activity_notify = Notifier(inside={1})
    sent.clear()

    async def scenario():
        first = await bot.feedback(1, "evade_slow", "❌ <@1> slow", ms=900)         # inside the Activity
        second = await bot.feedback(2, "evade_slow", "❌ <@2> slow", ms=700)        # playing from the chat
        return first, second

    first, second = asyncio.run(scenario())
    assert first is None and second == "the message"
    assert sent == [("❌ <@2> slow", None)]
    assert bot.activity_notify.told == [(1, "evade_slow", {"ms": 900})]


def test_a_message_to_several_players_stays_in_the_channel_unless_all_of_them_are_in_the_activity(tmp_path, monkeypatch):
    bot, sent, _ = real_bot(tmp_path, monkeypatch)
    bot.activity_notify = Notifier(inside={1, 2})
    asyncio.run(bot.feedback(None, "group_done", "📊 2/3", users=[1, 2], ok=2, total=3))
    assert sent == [] and bot.activity_notify.told == [([1, 2], "group_done", {"ok": 2, "total": 3})]
    asyncio.run(bot.feedback(None, "group_done", "📊 2/3", users=[1, 2, 3], ok=2, total=3))
    assert sent == [("📊 2/3", None)]                                           # player 3 is in the chat: they need it


def test_the_modes_chat_and_quiet_force_the_channel_on_or_off(tmp_path, monkeypatch):
    bot, sent, _ = real_bot(tmp_path, monkeypatch, mode="chat")
    bot.activity_notify = Notifier(inside={1})
    asyncio.run(bot.feedback(1, "timeout", "💥 late"))
    assert sent == [("💥 late", None)] and bot.activity_notify.told == []        # "chat": always the channel
    bot, sent, _ = real_bot(tmp_path, monkeypatch, mode="quiet")
    asyncio.run(bot.feedback(1, "timeout", "💥 late"))
    assert sent == [("💥 late", None)]                                           # "quiet" but no Activity running: the channel is all there is
    sent.clear()
    bot.activity_notify = Notifier(inside=())
    asyncio.run(bot.feedback(5, "timeout", "💥 late"))
    assert sent == [] and bot.activity_notify.told == [(5, "timeout", {})]       # "quiet": the channel never hears it
    bot, _, _ = real_bot(tmp_path, monkeypatch, mode="nonsense")
    assert bot.feedback_mode == "auto"


def test_no_reaction_goes_on_any_message_for_who_plays_from_the_activity_but_the_verdict_is_kept(tmp_path, monkeypatch):
    bot, _, _ = real_bot(tmp_path, monkeypatch)
    bot.activity_notify = Notifier(inside={1})
    reacted = []

    class Posted:
        async def add_reaction(self, emoji):
            reacted.append(emoji)

    async def scenario():
        press = ActivityInput(NS(id=1), NS(guild=None), "*evade*", user_id=1)
        press.mirror_to = Posted()
        await bot.add_reaction_to_response(None, 1, press, "✅")
        return press

    press = asyncio.run(scenario())
    assert reacted == [] and press.reactions == ["✅"]                           # the screen still learns it went well
    assert bot.cue_quiet(None) is False                                          # auto mode with nothing known: the cue is left alone
    bot.active_qtes[5] = {"mode": "single", "target": NS(id=1), "participants": {}}
    assert bot.cue_quiet(5) is True                                              # a QTE for somebody inside: no star on its message
    bot.active_qtes[6] = {"mode": "single", "target": NS(id=2), "participants": {}}
    assert bot.cue_quiet(6) is False                                             # for somebody in the chat: the star stays


def test_the_bridge_tells_only_the_player_it_is_about_and_never_the_hosts_own_window():
    async def scenario():
        async with Rig() as rig:
            ana, _ = await rig.login(111)
            assert rig.app.activity_notify is rig.bridge                          # the bot talks to the Activity through the bridge
            assert rig.bridge.has_player(111) and not rig.bridge.has_player(222)
            rig.bridge.notify(111, "timeout", {})
            got = await frame(ana, "notice")
            rig.bridge.notify([222], "timeout", {})                               # nobody inside with that id: nothing is sent, nothing breaks
            rig.bridge.notify(111, "black_flash", {"damage": 25})
            second = await frame(ana, "notice")
            rig.bridge.stop()
            return got, second, rig.app.activity_notify

    got, second, after = run(scenario())
    assert got == {"t": "notice", "kind": "timeout", "data": {}}
    assert second["kind"] == "black_flash" and second["data"] == {"damage": 25}
    assert after is None


def test_a_press_in_quiet_mode_does_not_put_the_reaction_on_the_qte_message():
    async def scenario():
        async with Rig() as rig:
            rig.app.feedback_quiet = lambda user_id: True
            mirrored = []
            qte_message = NS(add_reaction=lambda e: mirrored.append(e) or asyncio.sleep(0))
            ws, _ = await rig.login()
            rig.start_qte()
            rig.app.active_qtes[7]["message"] = qte_message
            q = (await frame(ws, "qte"))["q"]
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "press", "id": q["id"], "command": "evade", "dt": 200})
            result = await frame(ws, "qte_result")
            return result, mirrored

    result, mirrored = run(scenario())
    assert result["ok"] is True and mirrored == []


def test_what_happens_to_a_player_is_told_to_the_activity_as_a_sound_event(tmp_path, monkeypatch):
    bot, sent, module = real_bot(tmp_path, monkeypatch)
    heard = []
    bot.activity_notify = NS(on_event=lambda event, data: heard.append((event, data.get("user"))), has_player=lambda uid: False, notify=lambda *a: None)

    async def scenario():
        for kind in ("evade_ok", "evade_slow", "timeout", "parry_mistimed", "save_ok", "combo_step", "combo_failed", "black_flash", "parry_cooldown"):
            await bot.feedback(7, kind, "x")

    asyncio.run(scenario())
    assert heard == [("evade_ok", 7), ("qte_fail", 7), ("qte_fail", 7), ("qte_fail", 7), ("rescue_ok", 7), ("combo_step", 7), ("qte_fail", 7),
                     ("black_flash", 7)]                                              # a parry on cooldown is not a sound of its own
