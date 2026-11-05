"""What a power does: the effect language (eventos_app/powers.py), and the real bot applying each part with real numbers."""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app import powers  # noqa: E402
from test_quiet_channel import real_bot  # noqa: E402


def test_the_effect_language_reads_old_and_new_forms_and_refuses_what_does_nothing():
    assert powers.validate("damage:50") == "damage:50"
    assert powers.validate("stun") == "stun:3"
    assert powers.validate("buff:damage_boost:0.2:30") == "buff:damage_boost:20:30"          # a fraction is a percent
    assert powers.validate(" damage_all:80 ; shield_team:30:10 ") == "damage_all:80;shield_team:30:10"
    assert powers.validate("stun:99") == "stun:10" and powers.validate("shield:200:5") == "shield:90:5"     # kept in range
    for bad, why in (("", "Falta"), ("rm -rf /", "no es un efecto"), ("damage", "cantidad"), ("buff:attack:1:2", "damage_boost"),
                     ("damage:1;heal:1;stun;cleanse;charge_team:5", "hasta 4"), ("damage:abc", "número")):
        with pytest.raises(powers.PowerError, match=why):
            powers.validate(bad)
    assert powers.damage_multiplier(1.5, 20, True) == pytest.approx(1.5 * 1.2 * 1.1)
    lines = powers.describe(powers.parse("damage:1000;heal_team:20"), 1.0, 500)
    assert lines[0].startswith("💥 500 damage") and "every player" in lines[1]


class Channel:
    def __init__(self):
        self.embeds = []

    async def send(self, content=None, embed=None, **kwargs):
        self.embeds.append(embed)


def fight(bot):
    bot.fight_active = True
    bot.active_boss = {"name": "Rey", "hp_current": 1000, "hp_max": 1000}
    for uid in (1, 2, 3):
        bot.player_hp[uid] = {"current": 50, "max": 100, "alive": True, "revenge_mode": False}

    async def damage_boss(name, amount):
        bot.active_boss["hp_current"] -= amount
    bot.damage_boss = damage_boss

    async def no_display(*a, **k):
        pass
    bot.update_hp_bar_display = no_display
    events = []
    bot.emit_event = lambda event, /, **data: events.append((event, data))
    return events


def use(bot, effect, user_id=1):
    channel = Channel()
    power = {"name": "Prueba", "description": "…", "type": "destructive", "cooldown": 60, "effect": effect}
    webhook = NS(id=999999)                                   # a Tupperbox message: the author is the webhook, not the player
    asyncio.run(bot.apply_power_effect(webhook, power, channel, "power1", user_id=user_id, character="Kuro"))
    return channel


def test_the_real_bot_applies_damage_with_the_weapon_and_the_boost_and_heals_shields_stuns_and_charges(tmp_path, monkeypatch):
    bot, _, _ = real_bot(tmp_path, monkeypatch)
    events = fight(bot)
    bot.get_weapon_damage_multiplier = lambda uid: 1.5
    bot.apply_buff(1, "damage_boost", 20, 60)
    channel = use(bot, "damage:100")
    assert bot.active_boss["hp_current"] == 1000 - 180                 # 100 × 1.5 (weapon) × 1.2 (boost)
    assert bot.power_cooldowns[1]["power1"] > time.time()            # the cooldown is the player's, not the webhook's
    assert 999999 not in bot.power_cooldowns
    assert ("power_effect", {"user": 1, "character": "Kuro", "name": "Prueba", "damage": 180, "healed": 0}) in events
    assert "180 damage" in channel.embeds[-1].fields[0].value

    use(bot, "heal_team:30;shield_team:40:20")
    assert [bot.player_hp[u]["current"] for u in (1, 2, 3)] == [80, 80, 80]
    assert bot.get_active_buff(2, "shield")["value"] == 40

    async def hurt():
        await bot.damage_player(2, 50)
    asyncio.run(hurt())
    assert bot.player_hp[2]["current"] == 80 - 30                     # 50 damage, 40 % less

    events.clear()
    use(bot, "stun:4;damage_all:10;charge_team:25")
    assert bot.enemy_stunned and bot.stun_end_time >= time.time() + 3.5
    assert ("boss_stunned", {"user": 1, "seconds": 4.0}) in events and any(e == "power_aoe" for e, _ in events)
    assert bot.power_charges[2]["power1"] >= 25 and bot.power_charges.get(1, {}).get("power1", 0) < 25      # the others, not the caster

    bot.player_status_effects[1] = {"burn": {"stacks": 1, "end_time": time.time() + 9}}
    bot.player_status_effects[2] = {"poison": {"stacks": 1, "end_time": time.time() + 9}}
    use(bot, "cleanse")
    assert 1 not in bot.player_status_effects and 2 in bot.player_status_effects


def test_a_power_can_make_the_boss_burn_and_weakness_and_curses_now_count(tmp_path, monkeypatch):
    bot, _, _ = real_bot(tmp_path, monkeypatch)
    fight(bot)
    assert powers.validate("afflict:burn") == "afflict:burn:8"
    use(bot, "afflict:burn:5")
    assert "burn" in bot.boss_status_effects.get("Rey", {})
    hp = bot.active_boss["hp_current"]
    asyncio.run(bot.apply_status_effect(1, "weakened", 30, 1, source="test"))
    use(bot, "damage:100")
    assert hp - bot.active_boss["hp_current"] < 100                 # weakened: the blow is weaker
    bot.power_charges[1] = {"power1": 0, "power2": 0}
    asyncio.run(bot.apply_status_effect(1, "cursed", 30, 2, source="test"))
    bot.add_charge_from_damage_taken(1, 50)
    assert bot.power_charges[1]["power1"] < 50 / 5.0 * bot.charge_per_damage_taken          # cursed: less charge


def test_the_game_masters_support_heals_boosts_shields_and_shortens_cooldowns_in_the_real_bot(tmp_path, monkeypatch):
    from eventos_app.activity.gm import GmPanel
    bot, _, _ = real_bot(tmp_path, monkeypatch)
    fight(bot)
    gm = GmPanel(bot)
    asyncio.run(gm.support("Gus", 1, "Ana", "heal", 25, 0))
    assert bot.player_hp[1]["current"] == 75
    asyncio.run(gm.support("Gus", 1, "Ana", "shield", 50, 20))
    assert bot.get_active_buff(1, "shield")["value"] == 50
    asyncio.run(gm.support("Gus", 1, "Ana", "damage_boost", 30, 0))
    assert bot.get_active_buff(1, "damage_boost")["value"] == 30
    bot.power_cooldowns[1] = {"power1": time.time() + 100}
    asyncio.run(gm.support("Gus", 1, "Ana", "cd_reduce", 60, 0))
    assert bot.power_cooldowns[1]["power1"] < time.time() + 41
    with pytest.raises(Exception, match="no existe"):
        asyncio.run(gm.support("Gus", 1, "Ana", "nuke", 1, 0))
    assert any("Curó a Ana" in e["action"] or "Curó Ana" in e["action"] for e in gm.log.recent())
