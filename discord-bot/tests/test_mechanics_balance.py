"""The balance decisions of the mechanics review: REVENGE ends when healed, Black Flash luck builds up only with bad luck, the damage and
time limits per difficulty, and old saved defaults that nobody chose giving way to the new ones (a value a game master chose stays)."""
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def bot_module(tmp_path, monkeypatch):
    from eventos_app import paths
    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module
    files = {}                                                       # the bot's data files, in memory: never the real ones
    monkeypatch.setattr(module, "save_data", lambda name, data: files.__setitem__(name, json.loads(json.dumps(data))))
    monkeypatch.setattr(module, "load_data", lambda name, default: files.get(name, default))
    module._files = files
    return module


def shell(module):
    bot = object.__new__(module.AdvancedQTEBot)
    bot.qte_times = {d: dict(t) for d, t in module.DEFAULT_QTE_TIMES.items()}
    bot.qte_timeout_durations = dict(module.DEFAULT_QTE_TIMEOUTS)
    bot.damage_ranges = dict(module.DEFAULT_DAMAGE_RANGES)
    bot.revenge_threshold, bot.revenge_bf_bonus = 0.20, 0.10
    bot.black_flash_base_chance, bot.black_flash_increment, bot.black_flash_cap = 0.02, 0.01, 0.20
    bot.bf_timing_window, bot.bf_chain_timing_window = 0.2, 0.15
    bot.player_hp, bot.player_stats, bot.player_buffs, bot.player_skills = {}, {}, {}, {}
    bot.skill_tree_config = {}
    bot.session_stats = {"black_flashes_today": 0}
    return bot


def test_harder_qtes_are_shorter_and_each_ends_a_moment_after_its_parry(bot_module):
    times, limits = bot_module.DEFAULT_QTE_TIMES, bot_module.DEFAULT_QTE_TIMEOUTS
    order = ["easy", "medium", "hard", "impossible"]
    assert [limits[d] for d in order] == sorted((limits[d] for d in order), reverse=True)
    for d in order:
        assert limits[d] == pytest.approx(times[d]["parry_window"][1] + 0.75)
    damage = bot_module.DEFAULT_DAMAGE_RANGES
    assert [damage[d][0] for d in order] == sorted(damage[d][0] for d in order) and damage["medium"] == (5, 10)


def test_revenge_ends_when_the_player_is_healed_above_the_threshold(bot_module):
    bot = shell(bot_module)
    bot.player_hp[1] = {"current": 15, "max": 100, "alive": True, "revenge_mode": True}
    assert bot.end_revenge_if_healed(1) is False and bot.player_hp[1]["revenge_mode"] is True        # still low: it stays
    bot.player_hp[1]["current"] = 20
    assert bot.end_revenge_if_healed(1) is False                                                       # right at the threshold
    bot.player_hp[1]["current"] = 45
    assert bot.end_revenge_if_healed(1) is True and bot.player_hp[1]["revenge_mode"] is False
    assert bot.end_revenge_if_healed(99) is False                                                      # nobody there


def test_black_flash_luck_builds_with_bad_luck_and_goes_back_to_the_base_when_it_lands(bot_module, monkeypatch):
    bot = shell(bot_module)
    bot.player_stats[1] = {"black_flash_chance": 0.02}
    center = bot.get_adjusted_parry_center("medium", 1)
    rolls = iter([0.99, 0.99, 0.99, 0.0])
    monkeypatch.setattr(random, "random", lambda: next(rolls))
    assert bot.check_black_flash(1, center + 0.5, "medium") is False                                  # bad timing: no roll, no luck
    assert bot.player_stats[1]["black_flash_chance"] == pytest.approx(0.02)
    for _ in range(3):
        assert bot.check_black_flash(1, center, "medium") is False                                    # good timing, bad luck
    assert bot.player_stats[1]["black_flash_chance"] == pytest.approx(0.05)
    assert bot.check_black_flash(1, center, "medium") is True
    assert bot.player_stats[1]["black_flash_chance"] == pytest.approx(0.02)
    bot.player_stats[1]["black_flash_chance"] = 0.195
    monkeypatch.setattr(random, "random", lambda: 0.99)
    bot.check_black_flash(1, center, "medium")
    assert bot.player_stats[1]["black_flash_chance"] == pytest.approx(0.20)                           # capped


def test_old_saved_damage_that_nobody_chose_gives_way_to_the_new_one(bot_module):
    old = {"easy": [1, 3], "medium": [2, 7], "hard": [1, 10]}
    assert bot_module.chosen_damage_ranges(old, None) == {"medium": (2, 7)}                           # the GM's own value stays
    assert bot_module.chosen_damage_ranges(old, 2) == {"easy": (1, 3), "medium": (2, 7), "hard": (1, 10)}   # chosen after the change
    bot = shell(bot_module)
    bot_module._files["qte_settings"] = {"qte_times": {}, "damage_ranges": old}
    bot.load_qte_settings()
    assert bot.damage_ranges["easy"] == (3, 6) and bot.damage_ranges["medium"] == (2, 7)
    bot.save_qte_settings()
    assert bot_module._files["qte_settings"]["defaults"] == bot_module.DEFAULTS_VERSION


def test_the_panel_does_not_bring_back_old_defaults_it_saved_but_keeps_what_was_chosen(tmp_path):
    from test_activity_gm import Rig
    rig = Rig(tmp_path)
    rig.app.counter_window = 5.0
    rig.app.qte_timeout_durations = {"easy": 7.75, "medium": 5.75, "hard": 5.25, "impossible": 2.45}
    rig.gm.values_file = tmp_path / "gm_values.json"
    rig.gm.values_file.write_text(json.dumps({"counter_window": 1.5, "qte_timeout_durations": {"easy": 6.75, "medium": 6.5}}), encoding="utf-8")
    rig.gm.apply_saved()
    assert rig.app.counter_window == 5.0 and rig.app.qte_timeout_durations["easy"] == 7.75 and rig.app.qte_timeout_durations["medium"] == 6.5
    rig.gm.values_file.write_text(json.dumps({"defaults": 2, "counter_window": 1.5}), encoding="utf-8")         # chosen after the change
    rig.gm.apply_saved()
    assert rig.app.counter_window == 1.5
    rig.gm.persist_all()
    assert json.loads(rig.gm.values_file.read_text(encoding="utf-8"))["defaults"] == 2
