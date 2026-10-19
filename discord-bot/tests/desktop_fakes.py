"""A made-up bot and Activity to put behind the desktop window, so its pages can be shown and tested as if an event were going on."""
from types import SimpleNamespace as NS

from eventos_app.runner import State


def fake_bot(**extra):
    """The tables of a bot in the middle of an event: a fight with a boss, a QTE running, three people with health."""
    members = {1: NS(display_name="Ana", name="ana"), 2: NS(display_name="Mina", name="mina"), 4: NS(display_name="Luis", name="luis")}
    channel = NS(name="qte-evento", guild=NS(name="Mi servidor"))
    app = NS(fight_active=True, active_boss={"name": "Rey de las Maldiciones", "hp_current": 640, "hp_max": 1000, "participants": set()},
             active_qtes={7: {"mode": "single", "difficulty": "hard", "target": members[1]}},
             player_hp={1: {"current": 80, "max": 100, "alive": True, "revenge_mode": False}, 2: {"current": 10, "max": 100, "alive": True, "revenge_mode": True},
                        3: {"current": 0, "max": 100, "alive": False, "revenge_mode": False}, 4: {"current": 55, "max": 100, "alive": True, "revenge_mode": False}},
             afk_users={4}, qte_players=list(members.values()), regen_checkpoints=["c1"], regen_amount=30, session_stats={"qtes_triggered": 14, "black_flashes_today": 3},
             current_qte_mode="standard", qte_variations={"standard": {"weight": 60}}, batch_mode_active=False, pending_qte_batch=[],
             resolve_event_guild=lambda: NS(get_member=members.get), power_charges={1: {"power1": 100.0, "power2": 40.0}},
             qte_channel_id=55, bot=NS(is_ready=lambda: True, guilds=[NS(name="Mi servidor")], user="EventBot#1234", get_channel=lambda cid: channel),
             quick_actions={}, keybinds={"single_easy": "f9", "single_medium": "f10", "single_hard": "f11", "single_impossible": "f12"})
    for key, value in extra.items():
        setattr(app, key, value)
    return app


def fake_activity(users=None, **extra):
    users = users if users is not None else [
        {"id": "1", "name": "Ana", "avatar": "", "dev": False, "hidden": False, "rtt_ms": 42.0, "seconds": 1800},
        {"id": "2", "name": "Mina", "avatar": "", "dev": False, "hidden": False, "rtt_ms": 135.0, "seconds": 600},
        {"id": "4", "name": "Luis", "avatar": "", "dev": False, "hidden": False, "rtt_ms": 410.0, "seconds": 75},
        {"id": "-1", "name": "Anfitrión (prueba local)", "avatar": "", "dev": True, "hidden": True, "rtt_ms": 2.0, "seconds": 3000}]
    values = dict(server=NS(port=8765, client_id=42), tunnel=NS(state="up", detail="", url="https://equipo.tail1234.ts.net", fixed=True),
                  hub=NS(stats=lambda: users, conns={}), auth=NS(client_secret="secret"), bridge=NS())
    values.update(extra)
    return NS(**values)


def connect(window, *, activity: bool = True, **bot_extra) -> None:
    """Make the window's runner look connected to a bot with an event going on (and the Activity open, if asked)."""
    runner = window.runner
    runner._app = fake_bot(**bot_extra)
    runner._state = State.CONNECTED
    runner._activity = fake_activity() if activity else None
    window.settings.discord_token = window.settings.discord_token or "x" * 24
    window.settings.activity_enabled = activity
