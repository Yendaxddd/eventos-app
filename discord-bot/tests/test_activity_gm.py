"""The game-master panel: launching QTEs, the boss, the players, the game's numbers and the content files, with the limits the bot's own
commands have, signed in a log, and open only to whoever the bot says is a GM."""
import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity.gm import GmLog, GmPanel  # noqa: E402
from eventos_app.activity.gm.common import number  # noqa: E402
from eventos_app.activity.hub import RpcError  # noqa: E402
from special_objects_manager import SpecialObjectsManager  # noqa: E402
from test_activity_panel import DATA, ME, OTHER, make_app  # noqa: E402

BOSS_DEFAULTS = {"character_name": None, "evade_chance": 0.15, "counter_chance": 0.20, "counter_damage": 15, "counter_gifs": [], "evade_gifs": [],
                 "abilities": {}, "domain": None, "status_inflict": {}}


def run(coro):
    return asyncio.run(coro)


class Rig:
    """A bot with the tables the GM panel touches, and recorders where the real bot would send messages to Discord."""

    def __init__(self, tmp: Path, app=None, guild=None):
        """`app` is a bot that already has the player tables (the socket tests bring the one behind their bridge); `guild` is the
        server it sees (by default, Ana and Mina)."""
        self.tmp = tmp
        self.app = app if app is not None else make_app(tmp / "objects", me=ME, other=OTHER)
        shutil.copytree(DATA / "special_objects" / "templates", self.app.special_objects_manager.templates_path, dirs_exist_ok=True)
        self._keep_manager_files_in_tmp(self.app.special_objects_manager, self.app.special_objects_manager.base_path)
        self.calls, self.sent = [], []
        app = self.app
        app.max_hp = 100
        app.player_hp = {ME: {"current": 60, "max": 100, "alive": True, "revenge_mode": False}, OTHER: {"current": 100, "max": 100, "alive": True, "revenge_mode": False}}
        app.active_boss = None
        app.fight_active = False
        app.fight_start_time = None
        app.enemy_stunned, app.stun_end_time = False, None
        if getattr(app, "active_qtes", None) is None:                 # behind a real bridge the QTE book is already there
            app.active_qtes = {}
        app.batch_mode_active, app.pending_qte_batch, app.regen_checkpoints = False, [], []
        app.regen_amount, app.save_limit, app.save_time_window = 30, 2, 60
        app.qte_players = [NS(id=ME, display_name="Ana", name="ana"), NS(id=OTHER, display_name="Mina", name="mina")]
        app.session_stats = {"qtes_triggered": 3, "black_flashes_today": 1}
        app.current_qte_mode = "standard"
        app.qte_variations = {"standard": {"weight": 60}, "combo": {"weight": 15}, "direction": {"weight": 15}, "fake": {"weight": 10}}
        app.qte_times = {"easy": {"evade_window": 6.0, "parry_window": (4.0, 7.0), "perfect_parry": 5.5}, "medium": {"evade_window": 4.5, "parry_window": (3.0, 5.0), "perfect_parry": 4.0},
                         "hard": {"evade_window": 4.0, "parry_window": (2.5, 4.5), "perfect_parry": 3.5}, "impossible": {"evade_window": 1.5, "parry_window": (0.8, 1.7), "perfect_parry": 1.25}}
        app.qte_timeout_durations = {"easy": 6.75, "medium": 5.0, "hard": 5.75, "impossible": 3.5}
        app.damage_ranges = {"easy": (1, 3), "medium": (1, 5), "hard": (1, 10), "impossible": (15, 15)}
        for attr, value in (("black_flash_base_chance", 0.02), ("black_flash_increment", 0.01), ("black_flash_cap", 0.20), ("bf_timing_window", 0.2), ("bf_chain_timing_window", 0.15),
                            ("charge_per_damage_dealt", 2.0), ("charge_per_damage_taken", 5.0), ("charge_per_counter", 3.0), ("ultimate_cost", 100.0), ("ultimate_base_cooldown", 600),
                            ("ultimate_cooldown_per_damage", 0.5), ("ultimate_max_damage", 500), ("ultimate_self_recharge", False), ("counter_window", 1.5),
                            ("revenge_threshold", 0.20), ("revenge_damage_multiplier", 1.5), ("revenge_bf_bonus", 0.10), ("latency_offset", 0.25)):
            setattr(app, attr, value)
        app.tupperbox_boss_config = json.loads(json.dumps(BOSS_DEFAULTS))
        app.tupperbox_boss_mode = False
        app.boss_defeat_gifs = []
        app.status_effect_types = {"bleed": {}, "burn": {}, "stunned": {}}
        app.player_status_effects = {}
        app.power_cooldowns = {ME: {"power1": time.time() + 100}}
        app.ultimate_fight_cooldowns, app.domain_cooldowns = {ME: {"power2": 50}}, {ME: {"infinite_void": time.time()}}
        app.max_adaptation_warned = {}
        members = {ME: NS(id=ME, display_name="Ana", name="ana"), OTHER: NS(id=OTHER, display_name="Mina", name="mina")}
        app.qte_channel_id, app.resolve_event_guild = 10, (lambda: guild) if guild is not None else (lambda: NS(get_member=members.get))
        bot = getattr(app, "bot", None) or NS()
        channel = (bot.get_channel(10) if hasattr(bot, "get_channel") else None) or NS(id=10)

        async def send(*args, **kwargs):
            self.sent.append(kwargs)
        channel.send = send
        bot.get_channel = lambda cid: channel if cid == 10 else None
        app.bot = bot

        def record(name):
            async def call(*args, **kwargs):
                self.calls.append((name, args, kwargs))
            return call
        for name in ("trigger_single_qte", "trigger_group_qte", "trigger_combo_qte", "trigger_direction_qte", "trigger_fake_qte", "process_batch_qtes", "trigger_checkpoint_heal",
                     "force_sync_commands", "update_hp_bar_display", "trigger_boss_domain", "update_qte_player_cache"):
            setattr(app, name, record(name))
        app.should_update_cache = lambda: False
        app._resume_ultimate_cooldowns = lambda: self.calls.append(("resume", (), {}))
        app._pause_ultimate_cooldowns = lambda: self.calls.append(("pause", (), {}))
        app.reset_faith_system = lambda: self.calls.append(("faith", (), {}))
        app.save_tupperbox_boss_config = lambda: self.calls.append(("save_boss", (), {}))
        app.save_qte_settings = lambda: self.calls.append(("save_qte", (), {}))
        app.save_live_config = lambda: self.calls.append(("save_live", (), {}))

        async def initialize_player_hp(uid):
            app.player_hp[uid] = {"current": app.max_hp, "max": app.max_hp, "alive": True, "revenge_mode": False}
        app.initialize_player_hp = initialize_player_hp

        async def damage_boss(name, damage):
            boss = app.active_boss
            boss["hp_current"] = max(0, boss["hp_current"] - damage)
            self.calls.append(("damage_boss", (name, damage), {}))
            if boss["hp_current"] == 0:
                app.active_boss, app.fight_active = None, False
        app.damage_boss = damage_boss

        async def boss_use_ability(name, targets):
            self.calls.append(("boss_use_ability", (name, list(targets)), {}))
            return {"success": True, "damage": 25, "targets_hit": list(targets), "gif": None}
        app.boss_use_ability = boss_use_ability

        async def award(uid, achievement_id):
            app.player_achievements.setdefault(str(uid), {})[achievement_id] = {"unlocked": True, "date": "2026-02-02 10:00:00"}
            return True
        app.award_achievement = award
        data = tmp / "data"
        (data / "achievements").mkdir(parents=True)
        shutil.copy(DATA / "achievements" / "achievements_config.json", data / "achievements" / "achievements_config.json")
        (data / "skill_trees" / "templates").mkdir(parents=True)
        shutil.copy(DATA / "skill_trees" / "templates" / "skill_tree_template.json", data / "skill_trees" / "templates" / "skill_tree_template.json")
        app.load_achievements_config = lambda: json.loads((data / "achievements" / "achievements_config.json").read_text(encoding="utf-8"))
        app.load_skill_tree_config = lambda: {t["id"]: t for t in (json.loads(f.read_text(encoding="utf-8")) for f in (data / "skill_trees" / "templates").glob("*.json"))}
        self.data = data
        self.gm = GmPanel(app, GmLog(tmp / "gm_log.jsonl"), data, tmp / "gm_values.json")

    @staticmethod
    def _keep_manager_files_in_tmp(manager, base: Path) -> None:
        """The manager saves to `data/special_objects/...` relative to the working directory (the bot runs inside its data folder): a test
        must never write there, because from the repository that is the real data."""
        save_tracking, save_inventory = manager.save_tracking, manager.save_inventory
        manager.save_tracking = lambda filepath=None: save_tracking(str(base / "tracking_data.json"))
        manager.save_inventory = lambda filepath=None: save_inventory(str(base / "player_inventory.json"))


@pytest.fixture()
def rig():
    with tempfile.TemporaryDirectory() as tmp:
        yield Rig(Path(tmp))


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


# ---- the numbers a game master types ---------------------------------------------------------------------------------------------
def test_numbers_typed_by_a_game_master_are_forced_into_their_limits():
    assert number("12", "x", 0, 20) == 12.0 and number(5, "x", 1, 9, integer=True) == 5 and number("2,5".replace(",", "."), "x", 0, 10) == 2.5
    for bad in (None, "", "abc", True, float("nan"), float("inf"), [1]):
        with pytest.raises(RpcError, match="número"):
            number(bad, "Daño", 0, 10)
    with pytest.raises(RpcError, match="va de 0 a 10"):
        number(11, "Daño", 0, 10)
    with pytest.raises(RpcError, match="entero"):
        number(2.5, "Vidas", 0, 10, integer=True)


# ---- the event --------------------------------------------------------------------------------------------------------------------
def test_the_state_of_the_event_is_plain_data(rig):
    app = rig.app
    app.active_boss = {"name": "Rey", "hp_current": 70, "hp_max": 100, "gif_url": "https://cdn/x.png", "participants": set()}
    app.fight_active = True
    app.active_qtes = {7: {"mode": "single", "difficulty": "easy", "target": app.qte_players[0]}, 8: {"mode": "group", "difficulty": "hard", "target": None}}
    state = json.loads(json.dumps(rig.gm.state(), allow_nan=False))
    assert state["fight"] and state["boss"] == {"name": "Rey", "hp": 70.0, "max": 100.0, "image": "https://cdn/x.png", "tupper": False}
    assert [(q["id"], q["target"]) for q in state["qtes"]] == [("7", "Ana"), ("8", None)] and state["players"] == {"eligible": 2, "afk": 0, "withHp": 2}
    assert state["qteMode"] == "standard" and state["weights"]["standard"] == 60 and state["batch"] == {"active": False, "pending": []} and state["stunLeft"] == 0


def test_every_kind_of_qte_can_be_launched_and_the_arguments_reach_the_bot(rig):
    async def scenario():
        gm = rig.gm
        await gm.launch("Gus", "single", "hard")
        await gm.launch("Gus", "single", "easy", str(OTHER))
        await gm.launch("Gus", "group", "medium")
        await gm.launch("Gus", "combo", "impossible", str(ME))
        await gm.launch("Gus", "direction", "easy")
        await gm.launch("Gus", "fake", "hard", None)
        await settle()
    run(scenario())
    names = [(n, a[0], k) for n, a, k in rig.calls]
    assert names[0] == ("trigger_single_qte", "hard", {"target_member": None, "is_targeted": False})
    assert names[1][0] == "trigger_single_qte" and names[1][2]["is_targeted"] is True and names[1][2]["target_member"].id == OTHER
    assert names[2] == ("trigger_group_qte", "medium", {})
    combo = next(c for c in rig.calls if c[0] == "trigger_combo_qte")
    assert combo[1][0] == "impossible" and combo[1][1].id == ME and combo[1][2] is True                  # chosen by the GM: targeted
    direction = next(c for c in rig.calls if c[0] == "trigger_direction_qte")
    assert direction[1][1].id in (ME, OTHER) and direction[1][2] is False                                  # random
    assert rig.gm.log.recent(10)[0]["action"].startswith("Lanzó un QTE falso")                          # newest first
    assert any("individual (fácil) a Mina" in e["action"] for e in rig.gm.log.recent(10))


def test_launching_is_refused_when_it_makes_no_sense(rig):
    async def scenario():
        gm, app = rig.gm, rig.app
        for args, why in ((("single", "godlike"), "dificultad"), (("laser", "easy"), "no existe"), (("single", "easy", "999"), "no está en el servidor"),
                          (("single", "easy", "abc"), "no está en el servidor")):
            with pytest.raises(RpcError, match=why):
                await gm.launch("Gus", *args)
        app.enemy_stunned, app.stun_end_time = True, time.time() + 30
        with pytest.raises(RpcError, match="aturdido"):
            await gm.launch("Gus", "single", "easy")
        app.enemy_stunned = False
        app.qte_players = []
        with pytest.raises(RpcError, match="No hay jugadores"):
            await gm.launch("Gus", "combo", "easy")
        app.bot.get_channel = lambda cid: None
        with pytest.raises(RpcError, match="canal"):
            await gm.launch("Gus", "group", "easy")
    run(scenario())
    assert rig.calls == []                                           # nothing reached the bot


def test_the_batch_queue_follows_the_hotkeys(rig):
    gm, app = rig.gm, rig.app
    with pytest.raises(RpcError, match="empieza"):
        gm.batch("Gus", "add", "easy")
    gm.batch("Gus", "start")
    for d in ("easy", "hard", "impossible"):
        gm.batch("Gus", "add", d)
    assert gm.batch("Gus", "undo") == {"active": True, "pending": ["easy", "hard"]}
    with pytest.raises(RpcError, match="dificultad"):
        gm.batch("Gus", "add", "nope")

    async def scenario():
        gm.batch("Gus", "send")
        await settle()
    run(scenario())
    assert [c[0] for c in rig.calls] == ["process_batch_qtes"]
    gm.batch("Gus", "start")
    assert gm.batch("Gus", "cancel") == {"active": False, "pending": []}
    gm.batch("Gus", "start")
    with pytest.raises(RpcError, match="No hay QTE"):
        gm.batch("Gus", "send")
    for _ in range(30):
        gm.batch("Gus", "add", "easy")
    with pytest.raises(RpcError, match="hasta 30"):
        gm.batch("Gus", "add", "easy")


def test_checkpoint_fight_and_qte_mode(rig):
    async def scenario():
        out = await rig.gm.checkpoint("Gus")
        await settle()
        return out
    assert run(scenario()) == {"name": "Checkpoint 1"} and rig.app.regen_checkpoints == ["Checkpoint 1"]
    assert rig.calls[-1][:2] == ("trigger_checkpoint_heal", ("Checkpoint 1",))
    gm, app = rig.gm, rig.app
    app.player_stats = {ME: {"damage_taken_this_fight": 9, "critical_counters_this_fight": 2}}
    assert gm.fight("Gus", "start")["fight"] is True and app.player_stats[ME] == {"damage_taken_this_fight": 0, "critical_counters_this_fight": 0}
    assert ("resume", (), {}) in rig.calls
    with pytest.raises(RpcError, match="en curso"):
        gm.fight("Gus", "start")
    assert gm.fight("Gus", "end")["fight"] is False and ("pause", (), {}) in rig.calls
    with pytest.raises(RpcError, match="No hay un combate"):
        gm.fight("Gus", "end")
    assert gm.set_qte_mode("Gus", "combo", {"fake": 0, "standard": 50})["qteMode"] == "combo" and app.qte_variations["fake"]["weight"] == 0
    for bad, why in (("chaos", "no existe"), ("random", "mayor que 0")):
        with pytest.raises(RpcError, match=why):
            gm.set_qte_mode("Gus", bad, {k: 0 for k in app.qte_variations} if bad == "random" else None)
    with pytest.raises(RpcError, match="entre|va de"):
        gm.set_qte_mode("Gus", "random", {"combo": 500})
    saved = json.loads((rig.tmp / "gm_values.json").read_text(encoding="utf-8"))
    assert saved["current_qte_mode"] == "combo" and saved["qte_variations"]["fake"] == 0


# ---- the boss ------------------------------------------------------------------------------------------------------------------------
def test_a_boss_is_registered_fought_and_removed(rig):
    async def scenario():
        gm, app = rig.gm, rig.app
        with pytest.raises(RpcError, match="No hay un jefe"):
            await gm.boss_hp("Gus", "damage", 10)
        for args, why in (("", "nombre"), ("Rey", "Vida")):
            with pytest.raises(RpcError, match=why):
                await gm.boss_register("Gus", args, 0 if args else 100)
        with pytest.raises(RpcError, match="https"):
            await gm.boss_register("Gus", "Rey", 100, "http://x/y.png")
        out = await gm.boss_register("Gus", "Rey Sombra", 500, "https://cdn.discordapp.com/boss.png")
        await settle()
        assert out["active"]["name"] == "Rey Sombra" and app.fight_active and app.active_boss["hp_max"] == 500
        assert rig.sent and "BOSS FIGHT STARTED" in rig.sent[0]["embed"].title and ("resume", (), {}) in rig.calls
        await gm.boss_hp("Gus", "damage", 120)
        assert app.active_boss["hp_current"] == 380
        await gm.boss_hp("Gus", "heal", 1000)
        assert app.active_boss["hp_current"] == 500
        await gm.boss_hp("Gus", "set", 250)
        assert app.active_boss["hp_current"] == 250
        with pytest.raises(RpcError, match="máximo"):
            await gm.boss_hp("Gus", "set", 501)
        await gm.boss_hp("Gus", "defeat")
        assert app.active_boss is None and not app.fight_active                        # the bot's own damage routine ended it
        await gm.boss_register("Gus", "Otro", 100)
        gm.boss_remove("Gus")
        assert app.active_boss is None and not app.fight_active and ("pause", (), {}) in rig.calls
        with pytest.raises(RpcError, match="No hay un jefe"):
            gm.boss_remove("Gus")
    run(scenario())


def test_the_tupperbox_boss_is_configured_and_uses_abilities_gifs_and_a_domain(rig):
    async def scenario():
        gm, app = rig.gm, rig.app
        with pytest.raises(RpcError, match="personaje de Tupperbox"):
            await gm.boss_spawn("Gus")
        gm.boss_config("Gus", {"character": "  Lyra ", "hp": 800, "evade": 10, "counter": 25, "counterDamage": 40})
        cfg = app.tupperbox_boss_config
        assert (cfg["character_name"], cfg["boss_hp"], cfg["evade_chance"], cfg["counter_chance"], cfg["counter_damage"]) == ("Lyra", 800, 0.1, 0.25, 40) and ("save_boss", (), {}) in rig.calls
        for patch, why in (({"hp": 0}, "Vida"), ({"evade": 101}, "esquivar"), ({"counterDamage": "x"}, "Daño")):
            with pytest.raises(RpcError, match=why):
                gm.boss_config("Gus", {"character": "Lyra", "hp": 800, "evade": 10, "counter": 25, "counterDamage": 40, **patch})
        out = await gm.boss_spawn("Gus")
        await settle()
        assert out["active"]["tupper"] and app.tupperbox_boss_mode and app.active_boss["name"] == "Lyra" and "BOSS APPEARS" in rig.sent[-1]["embed"].title

        gm.ability_save("Gus", {"name": "Tajo", "damage": 30, "gif": "https://cdn/a.gif", "statusType": "bleed", "statusChance": 50, "statusDuration": 20})
        assert cfg["abilities"]["Tajo"] == {"damage": 30, "gif": "https://cdn/a.gif"} and cfg["status_inflict"]["Tajo"] == {"status": "bleed", "chance": 50, "duration": 20}
        for patch, why in (({"name": " "}, "nombre"), ({"damage": 99999}, "Daño"), ({"statusType": "wet"}, "estado"), ({"gif": "ftp://x"}, "https")):
            with pytest.raises(RpcError, match=why):
                gm.ability_save("Gus", {"name": "Otra", "damage": 5, **patch})
        gm.ability_save("Gus", {"name": "Tajo", "damage": 35})
        assert "Tajo" not in cfg["status_inflict"] and cfg["abilities"]["Tajo"]["damage"] == 35                  # no status: the old one goes
        used = await gm.ability_use("Gus", "Tajo")
        await settle()
        assert used == {"damage": 25, "hit": 2} and rig.sent[-1]["embed"].title.endswith("Tajo**!")
        with pytest.raises(RpcError, match="no existe"):
            await gm.ability_use("Gus", "Nada")
        data = gm.boss()
        assert data["config"]["abilities"][0]["name"] == "Tajo" and "bleed" in data["statusTypes"]

        gm.gif_add("Gus", "evade", "https://cdn/e1.gif")
        gm.gif_add("Gus", "counter", "https://cdn/c1.gif")
        gm.gif_add("Gus", "defeat", "https://cdn/d1.gif")
        with pytest.raises(RpcError, match="ya está"):
            gm.gif_add("Gus", "evade", "https://cdn/e1.gif")
        with pytest.raises(RpcError, match="no existe"):
            gm.gif_add("Gus", "party", "https://cdn/p.gif")
        assert cfg["evade_gifs"] == ["https://cdn/e1.gif"] and app.boss_defeat_gifs == ["https://cdn/d1.gif"]
        gm.gif_remove("Gus", "evade", 0)
        with pytest.raises(RpcError, match="ya no está"):
            gm.gif_remove("Gus", "evade", 0)

        with pytest.raises(RpcError, match="no tiene dominio"):
            await gm.domain_expand("Gus")
        gm.domain_save("Gus", {"name": "Santuario", "type": "DPS", "duration": 30, "effect": 10, "gif": ""})
        assert cfg["domain"] == {"name": "Santuario", "type": "dps", "duration": 30, "effect_value": 10, "gif": None}
        with pytest.raises(RpcError, match="tipo de dominio"):
            gm.domain_save("Gus", {"name": "X", "type": "magic", "duration": 5, "effect": 1})
        await gm.domain_expand("Gus")
        await settle()
        assert rig.calls[-1][0] == "trigger_boss_domain" and rig.calls[-1][1][1]["name"] == "Santuario"
        gm.domain_clear("Gus")
        assert cfg["domain"] is None
        gm.ability_remove("Gus", "Tajo")
        assert cfg["abilities"] == {}
        gm.boss_mode("Gus", False)
        assert app.tupperbox_boss_mode is False
    run(scenario())


# ---- the players ------------------------------------------------------------------------------------------------------------------------
def test_the_players_list_and_one_players_whole_picture(rig):
    gm = rig.gm
    rows = gm.rows({ME: ("Ana", None)}, {ME})
    by_id = {r["id"]: r for r in rows}
    assert str(ME) in by_id and str(OTHER) in by_id and by_id[str(ME)]["name"] == "Ana" and by_id[str(ME)]["online"] and not by_id[str(OTHER)]["online"]
    assert by_id[str(OTHER)]["name"].startswith("Jugador …") and by_id[str(ME)]["hp"] == {"current": 60, "max": 100, "alive": True, "revenge": False}
    assert by_id[str(ME)]["charges"] == [100.0, 37.5] and by_id[str(ME)]["points"] == 3 and by_id[str(ME)]["characters"] == 2
    json.dumps(rows, allow_nan=False)
    detail = json.loads(json.dumps(gm.player(ME, ("Ana", None)), allow_nan=False))
    assert detail["profile"]["stats"]["attempts"] == 20 and [o["id"] for o in detail["inventory"]["objects"]] == ["reactive_core", "mirror_shard"]
    assert {a["id"] for a in detail["achievements"]} == {"first_evade", "infinity"} and detail["skills"] == {"combat_1": 1}
    assert any(o["id"] == "mirror_shard" and o["unique"] and o["owner"] == str(ME) for o in detail["catalog"]["objects"]) and len(detail["catalog"]["achievements"]) == 16
    hidden = next(a for a in detail["catalog"]["achievements"] if a["id"] == "shrine")
    assert hidden["hidden"] is True                                  # the GM sees secrets: the players' panel does not


def test_health_charges_cooldowns_points_and_afk(rig):
    async def scenario():
        gm, app = rig.gm, rig.app
        await gm.set_hp("Gus", ME, "Ana", current=80)
        assert app.player_hp[ME]["current"] == 80
        await gm.set_hp("Gus", ME, "Ana", maximum=150)
        assert app.player_hp[ME] == {"current": 80, "max": 150, "alive": True, "revenge_mode": False}
        with pytest.raises(RpcError, match="Vida"):
            await gm.set_hp("Gus", ME, "Ana", current=150, maximum=120)                       # more than the new maximum
        assert app.player_hp[ME]["max"] == 150                                                  # and the refusal changed nothing
        await gm.set_hp("Gus", ME, "Ana", current=100, maximum=120)
        assert (app.player_hp[ME]["current"], app.player_hp[ME]["max"]) == (100, 120)
        for kw, why in (({"current": 0}, "Vida"), ({"current": 500}, "Vida"), ({"maximum": 0}, "máxima"), ({}, "Indica")):
            with pytest.raises(RpcError, match=why):
                await gm.set_hp("Gus", ME, "Ana", **kw)
        await gm.set_hp("Gus", 777, "Nuevo", current=10)                                   # nobody had HP for them yet: it starts as the bot starts it
        assert app.player_hp[777]["current"] == 10 and app.player_hp[777]["max"] == 100
        app.player_hp[ME]["alive"] = False
        await gm.set_hp("Gus", ME, "Ana", current=30)
        assert app.player_hp[ME]["alive"] is True                                          # healing a fallen player brings them back
        assert await gm.reset_hp("Gus", ME, "Ana") == 1 and app.player_hp[ME]["current"] == 100
        with pytest.raises(RpcError, match="todavía no tiene vida"):
            await gm.reset_hp("Gus", 555, "Nadie")
        assert await gm.reset_hp("Gus", None) == 3 and ("faith", (), {}) in rig.calls
    run(scenario())
    gm, app = rig.gm, rig.app
    gm.set_charges("Gus", ME, "Ana", 10, "55,5".replace(",", "."))
    assert app.power_charges[ME] == {"power1": 10.0, "power2": 55.5}
    with pytest.raises(RpcError, match="Carga del poder 1"):
        gm.set_charges("Gus", ME, "Ana", 101, 0)
    gm.reset_cooldowns("Gus", ME, "Ana")
    assert ME not in app.power_cooldowns and ME not in app.ultimate_fight_cooldowns and ME not in app.domain_cooldowns
    gm.give_points("Gus", ME, "Ana", 5)
    assert app.player_skills[str(ME)]["skill_points"] == 8
    gm.give_points("Gus", ME, "Ana", -8)
    assert app.player_skills[str(ME)]["skill_points"] == 0
    for amount, why in ((-1, "No tiene tantos"), (0, "Indica"), (10**6, "Puntos")):
        with pytest.raises(RpcError, match=why):
            gm.give_points("Gus", ME, "Ana", amount)
    gm.set_afk("Gus", ME, "Ana", True)
    assert ME in app.afk_users
    gm.set_afk("Gus", ME, "Ana", False)
    assert ME not in app.afk_users
    app.player_skills[str(ME)] = {"skill_points": 1, "skills": {"combat_1": 2, "combat_2a": 1}}
    assert gm.reset_skills("Gus", ME, "Ana") == 1 * 2 + 2 * 1 and app.player_skills[str(ME)] == {"skills": {}, "skill_points": 5}
    with pytest.raises(RpcError, match="No tiene habilidades"):
        gm.reset_skills("Gus", ME, "Ana")


def test_achievements_are_granted_once_and_removed_with_their_title_and_domain(rig):
    async def scenario():
        gm, app = rig.gm, rig.app
        with pytest.raises(RpcError, match="no existe"):
            await gm.grant_achievement("Gus", ME, "Ana", "ghost")
        with pytest.raises(RpcError, match="Ya tiene"):
            await gm.grant_achievement("Gus", ME, "Ana", "first_evade")
        await gm.grant_achievement("Gus", ME, "Ana", "first_parry")
        assert "first_parry" in app.player_achievements[str(ME)]
        gm.remove_achievement("Gus", ME, "Ana", "infinity")
        mine = app.player_achievements[str(ME)]
        assert "infinity" not in mine and "∞ Infinity" not in mine["titles"] and "infinite_void" not in mine["domains"] and "active_domain" not in mine
        assert mine["active_title"] == "Nimble"
        with pytest.raises(RpcError, match="No tiene ese logro"):
            gm.remove_achievement("Gus", ME, "Ana", "infinity")
    run(scenario())


def test_objects_are_given_taken_and_their_spins_edited(rig):
    gm, app = rig.gm, rig.app
    with pytest.raises(RpcError, match="único ya lo tiene"):
        gm.give_object("Gus", OTHER, "Mina", "reactive_core")
    with pytest.raises(RpcError, match="no existe"):
        gm.give_object("Gus", OTHER, "Mina", "ghost")
    with pytest.raises(RpcError, match="No tiene ese objeto"):
        gm.take_object("Gus", OTHER, "Mina", "reactive_core")
    gm.take_object("Gus", ME, "Ana", "reactive_core")
    gm.give_object("Gus", OTHER, "Mina", "reactive_core")
    assert "reactive_core" in app.special_objects_manager.player_inventory[OTHER]
    gm.set_spins("Gus", ME, "Ana", "mirror_shard", {"total": 12})
    assert app.special_objects_manager.get_tracking(ME, "mirror_shard", "total") == 12
    with pytest.raises(RpcError, match="no existe en este objeto"):
        gm.set_spins("Gus", ME, "Ana", "mirror_shard", {"easy": 1})
    with pytest.raises(RpcError, match="Vueltas"):
        gm.set_spins("Gus", ME, "Ana", "mirror_shard", {"total": -1})
    gm.set_spins("Gus", OTHER, "Mina", "reactive_core", {"easy": 3, "impossible": 9})
    assert app.special_objects_manager.get_tracking(OTHER, "reactive_core", "impossible") == 9
    gm.reset_spins("Gus", OTHER, "Mina", "reactive_core")
    assert all(app.special_objects_manager.get_tracking(OTHER, "reactive_core", k) == 0 for k in ("easy", "medium", "hard", "impossible"))
    with pytest.raises(RpcError, match="No tiene ese objeto"):
        gm.set_spins("Gus", OTHER, "Mina", "mirror_shard", {"total": 1})
    gm.set_slots("Gus", ME, "Ana", 9)
    assert app.special_objects_manager.get_player_max_slots(ME) == 9
    with pytest.raises(RpcError, match="Espacios"):
        gm.set_slots("Gus", ME, "Ana", 0)


# ---- values ----------------------------------------------------------------------------------------------------------------------------
def test_the_games_numbers_are_listed_with_their_limits_and_changed_like_the_commands_do(rig):
    async def scenario():
        gm, app = rig.gm, rig.app
        values = gm.values()
        flat = {i["key"]: i for g in values["groups"] for i in g["items"]}
        assert flat["max_hp"]["value"] == 100 and flat["black_flash_base_chance"]["value"] == 2 and flat["revenge_threshold"]["value"] == 20
        assert flat["ultimate_self_recharge"]["value"] is False and flat["counter_window"]["min"] == 0.5 and flat["counter_window"]["max"] == 5
        assert values["qte"]["medium"] == {"evade": 4.5, "parryStart": 3.0, "parryEnd": 5.0, "perfect": 4.0, "timeout": 5.0, "damageMin": 1, "damageMax": 5}
        json.dumps(values, allow_nan=False)

        await gm.set_value("Gus", "black_flash_base_chance", 5)
        assert app.black_flash_base_chance == 0.05                                                           # a percentage in, a fraction in the bot
        await gm.set_value("Gus", "counter_window", "2.5")
        assert app.counter_window == 2.5
        await gm.set_value("Gus", "ultimate_self_recharge", True)
        assert app.ultimate_self_recharge is True
        await gm.set_value("Gus", "revenge_damage_multiplier", 2)
        assert ("save_live", (), {}) in rig.calls                                                            # the bot keeps those in its own file
        for key, value, why in (("black_flash_base_chance", 101, "va de 0 a 100"), ("counter_window", 0.1, "Ventana de contraataque"), ("max_hp", 0, "Vida máxima"),
                                ("ultimate_self_recharge", "yes", "sí o no"), ("nonsense", 1, "no existe"), ("save_limit", 2.5, "entero")):
            with pytest.raises(RpcError, match=why):
                await gm.set_value("Gus", key, value)

        app.player_hp = {ME: {"current": 50, "max": 100, "alive": True, "revenge_mode": False}, OTHER: {"current": 100, "max": 100, "alive": True, "revenge_mode": False}}
        await gm.set_value("Gus", "max_hp", 200)
        assert app.max_hp == 200 and app.player_hp[ME] == {"current": 100, "max": 200, "alive": True, "revenge_mode": False} and app.player_hp[OTHER]["current"] == 200
        assert [c for c in rig.calls if c[0] == "update_hp_bar_display"]
    run(scenario())


def test_the_timings_of_each_difficulty_are_checked_together(rig):
    gm, app = rig.gm, rig.app
    good = {"evade": 5, "parryStart": 3, "parryEnd": 6, "perfect": 4.5, "timeout": 7, "damageMin": 2, "damageMax": 8}
    gm.set_qte("Gus", "medium", good)
    assert app.qte_times["medium"] == {"evade_window": 5.0, "parry_window": (3.0, 6.0), "perfect_parry": 4.5} and app.damage_ranges["medium"] == (2, 8)
    assert app.qte_timeout_durations["medium"] == 7.0 and ("save_qte", (), {}) in rig.calls
    for patch, why in (({"parryStart": 6}, "empezar antes"), ({"perfect": 9}, "dentro de la ventana"), ({"timeout": 5}, "tiempo límite"), ({"damageMin": 9}, "mínimo"),
                       ({"evade": 0}, "esquive"), ({"damageMax": "x"}, "máximo")):
        with pytest.raises(RpcError, match=why):
            gm.set_qte("Gus", "hard", {**good, **patch})
    with pytest.raises(RpcError, match="dificultad"):
        gm.set_qte("Gus", "godlike", good)
    assert app.qte_times["hard"]["evade_window"] == 4.0                                              # a refused change changes nothing


def test_saved_values_come_back_after_a_restart_and_bad_ones_are_ignored(rig):
    async def scenario():
        await rig.gm.set_value("Gus", "charge_per_counter", 7)
        await rig.gm.set_value("Gus", "black_flash_cap", 35)
        rig.gm.set_qte_mode("Gus", "direction", {"fake": 5})
        rig.gm.set_qte("Gus", "easy", {"evade": 7, "parryStart": 4, "parryEnd": 7, "perfect": 5.5, "timeout": 9, "damageMin": 1, "damageMax": 3})
    run(scenario())
    fresh = Rig(rig.tmp / "again")
    fresh.gm.values_file = rig.tmp / "gm_values.json"
    applied = fresh.gm.apply_saved()
    assert applied > 5
    assert fresh.app.charge_per_counter == 7 and abs(fresh.app.black_flash_cap - 0.35) < 1e-9 and fresh.app.current_qte_mode == "direction"
    assert fresh.app.qte_variations["fake"]["weight"] == 5 and fresh.app.qte_timeout_durations["easy"] == 9.0
    (rig.tmp / "gm_values.json").write_text(json.dumps({"max_hp": -5, "counter_window": "x", "current_qte_mode": "chaos", "qte_variations": {"combo": 900}, "ghost": 1}), encoding="utf-8")
    other = Rig(rig.tmp / "third")
    other.gm.values_file = rig.tmp / "gm_values.json"
    assert other.gm.apply_saved() == 0 and other.app.max_hp == 100 and other.app.counter_window == 1.5            # nothing out of limits gets in
    (rig.tmp / "gm_values.json").write_text("{ not json", encoding="utf-8")
    assert other.gm.apply_saved() == 0


# ---- content --------------------------------------------------------------------------------------------------------------------------------
def test_achievements_are_created_changed_and_deleted_from_a_form(rig):
    gm, app = rig.gm, rig.app
    listed = gm.achievements()
    assert len(listed["achievements"]) == 16 and {c["id"] for c in listed["categories"]} >= {"combat", "defense"} and any(d["id"] == "infinite_void" for d in listed["domains"])
    new = {"id": "first_blood", "name": "Primera sangre", "description": "Haz el primer golpe", "category": "combat", "icon": "🩸", "trigger": "evade_count:3",
           "reward": {"points": 2, "title": "Novato", "domain": None}, "hidden": False, "announce": True, "message": ""}
    out = gm.achievement_save("Gus", new)
    assert any(a["id"] == "first_blood" and a["reward"]["points"] == 2 for a in out["achievements"]) and "first_blood" in app.achievements_config["achievements"]
    on_disk = json.loads((rig.data / "achievements" / "achievements_config.json").read_text(encoding="utf-8"))
    assert on_disk["achievements"]["first_blood"]["reward"] == {"skill_points": 2, "title": "Novato"} and on_disk["achievements"]["infinity"]["name"] == "Infinity"     # the rest is untouched
    assert list((rig.data / "backups").glob("*-achievements_config.*.json"))                                  # the old file was kept
    gm.achievement_save("Gus", {**new, "name": "Primera sangre!", "reward": {"points": 0, "title": "", "domain": "infinite_void"}, "message": "¡{player}!"})
    changed = next(a for a in app.achievements_config["achievements"]["first_blood"].items() if a[0] == "announcement_message")
    assert changed[1] == "¡{player}!" and app.achievements_config["achievements"]["first_blood"]["reward"] == {"domain": "infinite_void"}
    for patch, why in (({"id": "A"}, "identificador"), ({"name": ""}, "nombre"), ({"category": "nope"}, "categoría"), ({"trigger": "mucho"}, "disparador"),
                       ({"reward": {"points": 5000}}, "0 a 999"), ({"reward": {"domain": "nope"}}, "dominio")):
        with pytest.raises(RpcError, match=why):
            gm.achievement_save("Gus", {**new, **patch})
    gm.achievement_delete("Gus", "first_blood")
    assert "first_blood" not in app.achievements_config["achievements"]
    with pytest.raises(RpcError, match="ya no existe"):
        gm.achievement_delete("Gus", "first_blood")


def test_content_files_are_checked_backed_up_and_loaded_into_the_running_bot(rig):
    gm, app = rig.gm, rig.app
    keys = [f["key"] for f in gm.files()]
    assert "achievements" in keys and "tree:skill_tree_template" in keys and "object:reactive_core" in keys and "i18n" in keys
    assert any(t["key"] == "template:template_adaptation" for t in gm.templates())

    tree = json.loads(gm.file_get("tree:skill_tree_template")["text"])
    tree["branches"]["combat"]["skills"][0]["name"] = "Reflejos de gato"
    out = gm.file_save("Gus", "tree:skill_tree_template", json.dumps(tree))
    assert out["ok"] and app.skill_tree_config["example_tree"]["branches"]["combat"]["skills"][0]["name"] == "Reflejos de gato"
    assert len(gm.backups("tree:skill_tree_template")) == 1
    restored = gm.file_restore("Gus", "tree:skill_tree_template", gm.backups("tree:skill_tree_template")[0]["name"])
    assert restored["ok"] and app.skill_tree_config["example_tree"]["branches"]["combat"]["skills"][0]["name"] == "Quick Reflexes"
    broken = json.loads(json.dumps(tree))
    broken["branches"]["combat"]["skills"][1]["prerequisites"] = ["combat_9"]
    broken["branches"]["combat"]["skills"][2]["id"] = "combat_1"
    with pytest.raises(RpcError, match="repetida"):
        gm.file_save("Gus", "tree:skill_tree_template", json.dumps(broken))
    broken["branches"]["combat"]["skills"][2]["id"] = "combat_2b"
    with pytest.raises(RpcError, match="combat_9"):
        gm.file_save("Gus", "tree:skill_tree_template", json.dumps(broken))
    with pytest.raises(RpcError, match="JSON no es válido"):
        gm.file_save("Gus", "tree:skill_tree_template", "{ nope")

    shard = gm.file_get("object:mirror_shard")["text"]
    edited = json.loads(shard)
    edited["description"] = "Un espejo roto."
    gm.file_save("Gus", "object:mirror_shard", json.dumps(edited))
    assert app.special_objects_manager.objects["mirror_shard"]["description"] == "Un espejo roto." and "reactive_core" in app.special_objects_manager.objects
    edited["type"] = "banana"
    with pytest.raises(RpcError, match="no es válido"):
        gm.file_save("Gus", "object:mirror_shard", json.dumps(edited))
    edited.update({"type": "adaptation", "id": "other_name"})
    with pytest.raises(RpcError, match="igual al nombre del archivo"):
        gm.file_save("Gus", "object:mirror_shard", json.dumps(edited))

    gm.file_save("Gus", "i18n", json.dumps({"exact": {"A": "B"}, "patterns": [["^x$", "y"]]}))
    for bad, why in (({"exact": {"A": 1}}, "exact"), ({"patterns": [["(", "x"]]}, "no es válida"), ({"patterns": [["a"]]}, "patterns"), ([], "objeto")):
        with pytest.raises(RpcError, match=why):
            gm.file_save("Gus", "i18n", json.dumps(bad))
    with pytest.raises(RpcError, match="no se pueden cambiar"):
        gm.file_save("Gus", "template:template_adaptation", "{}")
    for key in ("../../etc/passwd", "object:../x", "tree:", "weird"):
        with pytest.raises(RpcError, match="no existe"):
            gm.file_get(key)
    assert gm.achievements()["achievements"]
    ach = json.loads(gm.file_get("achievements")["text"])
    ach["achievements"]["infinity"]["reward"]["domain"] = "ghost_domain"
    with pytest.raises(RpcError, match="ghost_domain"):
        gm.file_save("Gus", "achievements", json.dumps(ach))


def test_copies_made_within_one_second_keep_their_order_and_only_the_last_twenty_stay(rig):
    gm = rig.gm
    for i in range(24):                                                                    # far faster than one per second
        gm.file_save("Gus", "i18n", json.dumps({"exact": {"a": str(i)}}))
    names = [b["name"] for b in gm.backups("i18n")]
    assert len(names) == 20 and names == sorted(names, reverse=True)                      # newest first, the oldest ones were dropped
    assert json.loads((rig.data / "backups" / names[0]).read_text(encoding="utf-8"))["exact"]["a"] == "22"       # the version just before the last save
    assert json.loads((rig.data / "backups" / names[-1]).read_text(encoding="utf-8"))["exact"]["a"] == "3"


def test_new_trees_and_objects_never_overwrite_and_can_be_deleted_with_a_copy_kept(rig):
    gm, app = rig.gm, rig.app
    template = gm.file_get("template:template_adaptation")["text"]
    obj = json.loads(template)
    obj.update({"id": "moon_charm", "name": "Amuleto lunar"})
    gm.file_create("Gus", "object", "moon_charm", json.dumps(obj))
    assert "moon_charm" in app.special_objects_manager.objects
    with pytest.raises(RpcError, match="Ya existe"):
        gm.file_create("Gus", "object", "moon_charm", json.dumps(obj))
    with pytest.raises(RpcError, match="nombre debe"):
        gm.file_create("Gus", "object", "Mal Nombre!", json.dumps(obj))
    with pytest.raises(RpcError, match="no se puede"):
        gm.file_create("Gus", "pending", "moon", json.dumps(obj))
    gm.file_delete("Gus", "object:moon_charm")
    assert "moon_charm" not in app.special_objects_manager.objects and any((rig.data / "backups").glob("*-moon_charm.*.json"))
    with pytest.raises(RpcError, match="ya no existe"):
        gm.file_delete("Gus", "object:moon_charm")
    with pytest.raises(RpcError, match="no se puede borrar"):
        gm.file_delete("Gus", "achievements")


def test_pending_objects_are_approved_or_rejected(rig):
    gm, app = rig.gm, rig.app
    manager = app.special_objects_manager
    good = json.loads(gm.file_get("template:template_passive")["text"])
    good.update({"id": "cursed_ring", "name": "Anillo maldito"})
    (manager.pending_path / "cursed_ring.json").write_text(json.dumps(good), encoding="utf-8")
    (manager.pending_path / "broken.json").write_text(json.dumps({"id": "broken", "name": "X", "type": "banana"}), encoding="utf-8")
    listed = gm.objects()
    pending = {p["file"]: p for p in listed["pending"]}
    assert pending["cursed_ring.json"]["ok"] and not pending["broken.json"]["ok"] and pending["broken.json"]["errors"]
    assert {o["id"] for o in listed["approved"]} == {"reactive_core", "mirror_shard"}
    gm.object_approve("Gus", "cursed_ring.json")
    assert "cursed_ring" in manager.objects
    with pytest.raises(RpcError, match="No se pudo aprobar"):
        gm.object_approve("Gus", "broken.json")
    for sneaky in ("../approved/mirror_shard.json", "..\\approved\\mirror_shard.json", "/etc/passwd.json", "a/b.json", "x"):                  # never out of the pending folder
        with pytest.raises(RpcError, match="No se pudo rechazar"):
            gm.object_reject("Gus", sneaky)
    assert (manager.approved_path / "mirror_shard.json").exists() and "mirror_shard" in manager.objects
    gm.object_reject("Gus", "broken.json", "No encaja")
    assert not (manager.pending_path / "broken.json").exists()
    with pytest.raises(RpcError, match="No se pudo rechazar"):
        gm.object_reject("Gus", "broken.json")
    assert gm.object_reload("Gus")["loaded"] == 3


# ---- the log -----------------------------------------------------------------------------------------------------------------------------------
def test_every_change_is_signed_and_the_log_survives_a_restart(rig):
    rig.gm.set_afk("Gus", ME, "Ana", True)
    rig.gm.give_points("Marta", ME, "Ana", 2)
    recent = rig.gm.log.recent(5)
    assert [(e["who"], e["action"]) for e in recent] == [("Marta", "Dio 2 puntos de habilidad a Ana (ahora 5)"), ("Gus", "Ana queda fuera de los QTE")]
    again = GmLog(rig.tmp / "gm_log.jsonl")
    assert [e["who"] for e in again.recent(5)] == ["Marta", "Gus"]
    (rig.tmp / "gm_log.jsonl").write_text('{"ts": 1, "who": "A", "action": "hola"}\nbasura\n[1]\n', encoding="utf-8")
    assert [e["action"] for e in GmLog(rig.tmp / "gm_log.jsonl").recent(5)] == ["hola"]               # damaged lines are skipped
    small = GmLog(None, keep=3)
    for i in range(6):
        small.add("x", str(i))
    assert [e["action"] for e in small.recent(10)] == ["5", "4", "3"]
