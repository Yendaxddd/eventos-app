"""The player's dashboards: what the screen is told about stats, achievements, characters, skills, objects and pictures, and the
few things a player may change. The data is the game's own sample data (achievements, skill tree, objects)."""
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

from eventos_app import i18n  # noqa: E402
from eventos_app.activity.hub import RpcError  # noqa: E402
from eventos_app.activity.panel import MAX_CHARACTERS, MAX_COUNTER_IMAGES, PlayerPanel  # noqa: E402
from special_objects_manager import SpecialObjectsManager  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
ME, OTHER = 111, 222


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def make_app(tmp: Path, me: int = ME, other: int = OTHER):
    tree = load("skill_trees/templates/skill_tree_template.json")
    shutil.copytree(DATA / "special_objects" / "approved", tmp / "approved")
    manager = SpecialObjectsManager(str(tmp))
    manager.load_all()
    manager.player_inventory = {me: ["reactive_core"], other: []}
    manager.unique_object_owners = {"reactive_core": me, "mirror_shard": me}      # the shard is owned but not listed: it still shows up
    for key, spins in (("easy", 5), ("medium", 1), ("hard", 0), ("impossible", 3)):
        manager.set_tracking(me, "reactive_core", key, spins)
    manager.set_tracking(me, "mirror_shard", "total", 7)
    registry = {"Kuro": me, "Shiro": me, "Mina": other}
    app = NS(
        player_stats={me: {"total_attempts": 20, "successful": 15, "failed": 5, "evades": 12, "parries": 3, "saves": 2, "adapts": 1,
                           "best_time": 0.8, "avg_time": 2.5, "times": [1.0, 2.0, float("nan"), 3.0], "current_streak": 2, "best_streak": 6,
                           "parry_streak": 3, "best_parry_streak": 4, "evade_streak": 1, "best_evade_streak": 4, "black_flash_chance": 0.02, "black_flashes": 2},
                      other: {"total_attempts": 10, "successful": 9, "evades": 9, "best_time": float("inf"), "black_flashes": 5, "saves": 7, "best_parry_streak": 9},
                      333: {"reflect_active": False}},          # someone who never played: not on any board
        power_charges={me: {"power1": 100.0, "power2": 37.5}}, ultimate_cost=100,
        character_registry=registry, user_characters={me: ["Kuro", "Shiro"], other: ["Mina"]},
        character_powers={"Kuro": {"power1": {"name": "Corte", "description": "Un tajo", "type": "destructive", "cooldown": 60, "effect": "damage:50",
                                              "image_url": None, "trigger_phrase": None}}},
        power_types=["destructive", "support", "defend", "build", "control"],
        achievements_config=load("achievements/achievements_config.json"),
        player_achievements={str(me): {"first_evade": {"unlocked": True, "date": "2026-01-02 03:04:05", "timestamp": 1.0}, "infinity": {"unlocked": True, "date": "2026-01-03"},
                                       "titles": ["Nimble", "∞ Infinity"], "active_title": "Nimble", "domains": ["infinite_void"], "active_domain": "infinite_void"}},
        player_skills={str(me): {"skill_points": 3, "skills": {"combat_1": 1}}},
        skill_tree_config={"example_tree": tree}, special_objects_manager=manager,
        user_counter_gifs={me: ["https://cdn.discordapp.com/a.png"]}, afk_users=set(), domain_cooldowns={me: {"infinite_void": time.time() - 100}},
        saves=0,
    )
    app.get_user_characters = lambda uid: [n for n, o in app.character_registry.items() if o == uid]

    def save_all_data(force=False):
        app.saves += 1 if force else 0
    app.save_all_data = save_all_data
    return app


@pytest.fixture()
def rig():
    with tempfile.TemporaryDirectory() as tmp:
        app = make_app(Path(tmp))
        yield app, PlayerPanel(app)


def strict(data):
    """What the page receives: it must survive a strict JSON round trip (no NaN, no Infinity)."""
    return json.loads(json.dumps(data, allow_nan=False))


# ---- profile and leaderboard ---------------------------------------------------------------------------------------------
def test_the_profile_is_plain_numbers_the_page_can_draw(rig):
    app, panel = rig
    p = strict(panel.profile(ME))
    s = p["stats"]
    assert (s["attempts"], s["ok"], s["rate"], s["evades"], s["parries"], s["bf"], s["bfChance"]) == (20, 15, 75.0, 12, 3, 2, 2.0)
    assert s["times"] == [1.0, 2.0, 3.0] and s["best"] == 0.8 and s["multiplier"] == 1.3 and s["bestParryStreak"] == 4
    assert [c["pct"] for c in p["charges"]] == [100.0, 37.5] and p["charges"][0]["ready"] and not p["charges"][1]["ready"]
    assert p["charges"][0]["name"] == "Corte" and p["charges"][0]["character"] == "Kuro" and p["charges"][1]["name"] == "Poder 2"
    assert p["points"] == 3 and p["title"] == "Nimble" and p["domain"] == {"id": "infinite_void", "name": "Infinite Void"}
    assert p["counts"]["achievements"] == [2, 16] and p["counts"]["characters"] == 2 and p["counts"]["skills"] == 1
    assert p["counts"]["objects"] == 2 and p["counts"]["slots"] == [1, 5] and p["active"] is True
    assert p["ranks"]["success_rate"] == 2 and p["ranks"]["black_flashes"] == 2 and p["players"] == 2


def test_a_player_without_stats_gets_an_empty_profile_not_an_error(rig):
    _, panel = rig
    p = strict(panel.profile(999))
    assert p["stats"]["attempts"] == 0 and p["stats"]["best"] is None and p["ranks"] == {} and p["points"] == 0 and p["counts"]["characters"] == 0


def test_the_leaderboard_sorts_each_category_the_way_the_bot_does(rig):
    _, panel = rig
    by_rate = panel.ranking("success_rate")
    assert [(r["id"], r["rank"]) for r in by_rate] == [(OTHER, 1), (ME, 2)] and by_rate[0]["text"] == "90 %"
    assert [r["id"] for r in panel.ranking("black_flashes")] == [OTHER, ME]
    assert [r["id"] for r in panel.ranking("best_time")] == [ME]                       # nobody without a time is ranked
    assert panel.ranking("best_time")[0]["text"] == "0,8 s"
    assert [r["id"] for r in panel.ranking("saves")] == [OTHER, ME] and [r["id"] for r in panel.ranking("total_attempts")] == [ME, OTHER]
    with pytest.raises(RpcError):
        panel.ranking("hacker_score")


def test_taking_part_in_the_qtes_can_be_switched_off_and_on(rig):
    app, panel = rig
    assert panel.set_active(ME, False) == {"active": False} and ME in app.afk_users
    assert panel.profile(ME)["active"] is False
    assert panel.set_active(ME, True) == {"active": True} and ME not in app.afk_users


# ---- achievements ----------------------------------------------------------------------------------------------------------
def test_secret_achievements_tell_nothing_until_they_are_earned(rig):
    app, panel = rig
    out = strict(panel.achievements(ME))
    everything = {i["id"]: i for c in out["categories"] for i in c["items"]}
    assert everything["shrine"]["secret"] and everything["shrine"]["name"] == "???" and not everything["shrine"]["unlocked"]
    blob = json.dumps(everything["shrine"], ensure_ascii=False)
    assert "Shrine" not in blob and "damage" not in blob and "flawless" not in blob and "Untouched" not in blob       # nothing of it leaves the server
    assert out["unlocked"] == 2 and out["total"] == 16
    assert everything["first_evade"]["unlocked"] and everything["first_evade"]["date"] == "2026-01-02 03:04:05"
    assert everything["first_evade"]["name"] == "Pies ligeros" and everything["first_evade"]["description"] == "Esquiva con éxito tu primer QTE"
    assert everything["first_evade"]["reward"] == {"points": 1, "title": "Ágil", "domain": None}
    assert everything["infinity"]["reward"]["domain"] == "Infinite Void"
    # progress toward an achievement that counts something we know
    assert everything["evade_master"]["progress"] == {"have": 12, "need": 100}
    assert everything["first_parry"]["progress"] is None or everything["first_parry"]["progress"]["need"] == 1
    # once earned, a secret shows up
    app.player_achievements[str(ME)]["shrine"] = {"unlocked": True, "date": "2026-02-02"}
    shown = {i["id"]: i for c in panel.achievements(ME)["categories"] for i in c["items"]}["shrine"]
    assert shown["unlocked"] and shown["name"] == "Shrine" and shown["secret"] and shown["reward"]["points"] == 10


def test_titles_and_domains_belong_to_who_earned_them(rig):
    app, panel = rig
    out = panel.achievements(ME)
    assert out["activeTitle"] == "Nimble" and [t["id"] for t in out["titles"]] == ["Nimble", "∞ Infinity"] and out["titles"][0]["name"] == "Ágil"
    d = out["domains"][0]
    assert d["id"] == "infinite_void" and d["active"] and d["type"] == "simple" and d["cooldown"] == 300 and 150 < d["left"] <= 200
    assert "Atrapa a los enemigos" in d["description"]

    assert panel.set_title(ME, "∞ Infinity") == {"activeTitle": "∞ Infinity"} and app.player_achievements[str(ME)]["active_title"] == "∞ Infinity"
    assert panel.set_title(ME, None) == {"activeTitle": None} and "active_title" not in app.player_achievements[str(ME)]
    with pytest.raises(RpcError):
        panel.set_title(ME, "The Untouchable")                                         # not earned
    with pytest.raises(RpcError):
        panel.set_title(OTHER, "Nimble")                                               # somebody else's
    with pytest.raises(RpcError):
        panel.set_domain(ME, "malevolent_shrine")
    app.player_achievements[str(ME)]["domains"].append("malevolent_shrine")
    assert panel.set_domain(ME, "malevolent_shrine") == {"activeDomain": "malevolent_shrine"}
    assert app.saves >= 3


# ---- characters and powers --------------------------------------------------------------------------------------------
def test_characters_come_with_their_powers_and_the_names_worth_suggesting(rig):
    _, panel = rig
    out = strict(panel.characters(ME, avatars={"Kuro": "https://cdn/kuro.png"}, seen=["Kuro", "Zed", "Mina", "Nova"]))
    assert [c["name"] for c in out["characters"]] == ["Kuro", "Shiro"] and out["characters"][0]["avatar"] == "https://cdn/kuro.png"
    assert out["characters"][0]["powers"]["power1"]["name"] == "Corte" and out["characters"][0]["powers"]["power2"] is None
    assert out["suggestions"] == ["Zed", "Nova"]                              # registered names are not suggested again
    assert out["types"][0] == "destructive"


def test_registering_a_character_follows_the_register_command(rig):
    app, panel = rig
    assert panel.register_character(ME, "  Zed\n ") == {"name": "Zed"}
    assert app.character_registry["Zed"] == ME and "Zed" in app.user_characters[ME]
    for bad, why in (("", "nombre"), ("   ", "nombre"), ("Mina", "ya está registrado"), ("Zed", "ya está registrado")):
        with pytest.raises(RpcError, match=why):
            panel.register_character(ME, bad)
    assert panel.register_character(ME, "A\x00B\x1fC")["name"] == "A B C"      # control characters never get in
    assert len(panel.register_character(ME, "x" * 500)["name"]) == 80
    for i in range(MAX_CHARACTERS):
        try:
            panel.register_character(ME, f"c{i}")
        except RpcError as exc:
            assert "hasta" in str(exc)
            break
    else:
        pytest.fail("the limit never applied")


def test_only_the_owner_can_unregister(rig):
    app, panel = rig
    with pytest.raises(RpcError):
        panel.unregister_character(ME, "Mina")
    with pytest.raises(RpcError):
        panel.unregister_character(ME, "Nadie")
    assert panel.unregister_character(ME, "Shiro") == {"name": "Shiro"} and "Shiro" not in app.character_registry and "Shiro" not in app.user_characters[ME]


GOOD = {"character": "Shiro", "slot": 2, "name": "Escudo", "description": "Detiene el tiempo", "type": "defend", "cooldown": 120, "effect": "heal:30", "trigger": " Detén el Tiempo ", "image": ""}


def test_a_power_is_checked_like_the_register_power_command(rig):
    app, panel = rig
    assert panel.save_power(ME, False, GOOD) == {"character": "Shiro", "slot": 2}
    saved = app.character_powers["Shiro"]["power2"]
    assert saved == {"name": "Escudo", "description": "Detiene el tiempo", "type": "defend", "cooldown": 120, "effect": "heal:30", "image_url": None, "trigger_phrase": "detén el tiempo",
                     "show": "all"}
    assert panel.save_power(ME, False, {**GOOD, "image": "https://cdn.discordapp.com/p.png"}) and app.character_powers["Shiro"]["power2"]["image_url"].endswith("p.png")
    assert panel.save_power(ME, False, {**GOOD, "effect": "buff:damage_boost:0.2:30"}) and panel.save_power(ME, False, {**GOOD, "effect": "stun"})
    assert app.character_powers["Shiro"]["power2"]["effect"] == "stun:3"
    panel.save_power(ME, False, {**GOOD, "effect": "damage_all:80; shield_team:30:10", "show": "self"})
    assert app.character_powers["Shiro"]["power2"]["effect"] == "damage_all:80;shield_team:30:10" and app.character_powers["Shiro"]["power2"]["show"] == "self"
    with pytest.raises(RpcError, match="damage_boost"):
        panel.save_power(ME, False, {**GOOD, "effect": "buff:attack:0.2:30"})              # a boost that does nothing is refused
    for patch, why in (({"character": "Mina"}, "no es tuyo"), ({"character": "Nadie"}, "registrado"), ({"slot": 3}, "ranura"), ({"name": " "}, "nombre"),
                       ({"description": ""}, "qué hace"), ({"type": "hack"}, "tipo"), ({"cooldown": -1}, "recarga"), ({"cooldown": 10**7}, "recarga"),
                       ({"effect": ""}, "efecto"), ({"effect": "rm -rf /"}, "efecto"), ({"effect": "damage:abc"}, "efecto"),
                       ({"image": "http://insecure/x.png"}, "https"), ({"image": "javascript:alert(1)"}, "https"), ({"image": "https://a b/c"}, "https")):
        with pytest.raises(RpcError, match=why):
            panel.save_power(ME, False, {**GOOD, **patch})
    assert panel.save_power(ME, True, {**GOOD, "character": "Mina"}) == {"character": "Mina", "slot": 2}      # a game master may fix anyone's


def test_a_power_can_be_removed_by_its_owner(rig):
    app, panel = rig
    with pytest.raises(RpcError):
        panel.remove_power(OTHER, False, "Kuro", 1)
    with pytest.raises(RpcError):
        panel.remove_power(ME, False, "Kuro", 2)
    assert panel.remove_power(ME, False, "Kuro", 1) == {"character": "Kuro"} and "Kuro" not in app.character_powers


# ---- skills ---------------------------------------------------------------------------------------------------------------
def skill(out, sid):
    return next(s for t in out["trees"] for b in t["branches"] for s in b["skills"] if s["id"] == sid)


def test_the_skill_tree_says_what_each_skill_does_and_whether_you_can_learn_it(rig):
    _, panel = rig
    out = strict(panel.skills(ME))
    assert out["points"] == 3 and out["learned"] == 1 and out["total"] == 9
    one = skill(out, "combat_1")
    assert one["rank"] == 1 and one["max"] == 3 and one["state"] == "available" and "+0,1 s a la ventana de esquive" in one["description"] and one["name"] == "Reflejos rápidos"
    assert skill(out, "combat_2a")["state"] == "available" and skill(out, "combat_2a")["needs"] == [{"id": "combat_1", "name": "Reflejos rápidos", "met": True}]
    assert skill(out, "defense_2a")["state"] == "locked" and skill(out, "defense_2a")["needs"][0]["met"] is False
    assert skill(out, "defense_1")["state"] == "available" and skill(out, "defense_2b")["state"] == "locked"
    assert out["trees"][0]["name"] == "Árbol de habilidades de ejemplo" and out["trees"][0]["branches"][0]["name"] == "Maestría de combate"


def test_learning_a_skill_follows_the_learn_command(rig):
    app, panel = rig
    assert panel.learn_skill(ME, "combat_1") == {"id": "combat_1", "rank": 2, "points": 2}
    assert panel.learn_skill(ME, "combat_2a") == {"id": "combat_2a", "rank": 1, "points": 0}      # costs 2
    with pytest.raises(RpcError, match="Te faltan puntos"):
        panel.learn_skill(ME, "combat_1")
    app.player_skills[str(ME)]["skill_points"] = 50
    with pytest.raises(RpcError, match="Te falta"):
        panel.learn_skill(ME, "defense_2a")                                                         # needs Iron Will
    with pytest.raises(RpcError, match="no existe"):
        panel.learn_skill(ME, "cheat_99")
    panel.learn_skill(ME, "combat_1")
    with pytest.raises(RpcError, match="máximo"):
        panel.learn_skill(ME, "combat_1")                                                           # max rank 3
    assert app.player_skills[str(ME)]["skills"]["combat_1"] == 3
    with pytest.raises(RpcError):
        panel.learn_skill(OTHER, "combat_2a")                                                       # someone with no skill points at all
    assert app.player_skills[str(OTHER)]["skill_points"] == 0


# ---- inventory ------------------------------------------------------------------------------------------------------------
def test_the_inventory_shows_adaptation_progress_in_spanish(rig):
    _, panel = rig
    out = strict(panel.inventory(ME))
    assert out["slots"] == [1, 5]
    objects = {o["id"]: o for o in out["objects"]}
    assert set(objects) == {"reactive_core", "mirror_shard"}                                         # the unique shard counts although it is not listed
    core = objects["reactive_core"]
    assert core["name"] == "Núcleo reactivo" and core["rarity"] == "legendary" and core["type"] == "adaptation" and core["unique"] and not core["tradeable"]
    assert core["description"].startswith("Un artefacto misterioso") and core["tracking"]["kind"] == "per_difficulty"
    easy = next(r for r in core["tracking"]["rows"] if r["key"] == "easy")
    assert easy["spins"] == 5 and easy["next"] == 7 and easy["max"] == 10
    assert [s["done"] for s in easy["steps"]] == [True, False, False] and easy["steps"][0]["effects"] == ["Reduces el daño un 10 %", "Curas 10 HP"]
    shard = objects["mirror_shard"]
    total = shard["tracking"]["rows"][0]
    assert shard["tracking"]["kind"] == "total" and total["key"] == "total" and total["spins"] == 7 and total["next"] == 10 and total["max"] == 20
    assert "Contraataque garantizado" in total["steps"][1]["effects"]
    assert any("Esquive automático" in e for e in total["steps"][0]["effects"])
    other = panel.inventory(OTHER)
    assert other["objects"] == [] and other["slots"] == [0, 5]
    listed = {o["id"]: o for o in other["catalog"]}                                    # every object of the event, with who has it
    assert listed["mirror_shard"]["taken"] and not listed["mirror_shard"]["mine"] and listed["reactive_core"]["name"] == "Núcleo reactivo"
    assert shard["use"] is None                                                         # a bot without the invocation: no button


def test_the_mirror_shard_is_invoked_from_the_inventory_and_says_why_not_in_spanish(rig):
    app, panel = rig
    calls = []
    app.mirror_invoke_problem = lambda uid: None if calls == [] else "⏱️ The Mirror Shard is recharging: **{}s** left.".format(60)

    async def invoke(uid, name):
        calls.append((uid, name))
        return 15
    app.mirror_invoke = invoke
    shard = next(o for o in panel.inventory(ME)["objects"] if o["id"] == "mirror_shard")
    assert shard["use"] == {"id": "mirror", "label": "Invocar: refleja un QTE contra el jefe", "problem": None}
    out = asyncio.run(panel.use_object(ME, "Ana", "mirror"))
    assert out["damage"] == 15 and calls == [(ME, "Ana")]
    with pytest.raises(RpcError, match="recargando: faltan 60 s"):
        asyncio.run(panel.use_object(ME, "Ana", "mirror"))


# ---- counter images -------------------------------------------------------------------------------------------------------
def test_counter_images_are_a_short_list_of_https_links(rig):
    app, panel = rig
    assert panel.counter_images(ME)["images"] == ["https://cdn.discordapp.com/a.png"]
    out = panel.add_counter_image(ME, "https://cdn.discordapp.com/b.gif")
    assert out["images"][-1].endswith("b.gif") and app.user_counter_gifs[ME] == out["images"]
    for bad in ("", "http://x/y.png", "ftp://x/y", "https://x y/z", "data:image/png;base64,AAAA", "https://" + "a" * MAX_COUNTER_IMAGES * 100):
        with pytest.raises(RpcError):
            panel.add_counter_image(ME, bad)
    assert panel.remove_counter_image(ME, 0)["images"] == ["https://cdn.discordapp.com/b.gif"]
    with pytest.raises(RpcError):
        panel.remove_counter_image(ME, 5)
    assert panel.clear_counter_images(ME)["images"] == [] and ME not in app.user_counter_gifs
    for i in range(MAX_COUNTER_IMAGES):
        panel.add_counter_image(ME, f"https://cdn/x{i}.png")
    with pytest.raises(RpcError, match="hasta"):
        panel.add_counter_image(ME, "https://cdn/one-more.png")
    app.user_counter_gifs[OTHER] = "https://cdn/old-format.png"                                       # the bot once stored a single string
    assert panel.counter_images(OTHER)["images"] == ["https://cdn/old-format.png"]


# ---- Spanish for the game masters' texts ---------------------------------------------------------------------------------------
def test_the_game_masters_can_add_their_own_translations_and_it_is_picked_up_live(tmp_path):
    path = tmp_path / "i18n_es.json"
    tr = i18n.Translator(overrides=path)
    assert tr("Boss Slayer") == "Cazajefes" and tr("Something new") == "Something new"
    path.write_text(json.dumps({"exact": {"Something new": "Algo nuevo", "Boss Slayer": "Matajefes"}, "patterns": [["^Kill (\\d+) bosses$", "Derrota a \\1 jefes"], ["(", "broken"]]}), encoding="utf-8")
    tr._checked = 0
    assert tr("Something new") == "Algo nuevo" and tr("Boss Slayer") == "Matajefes" and tr("Kill 4 bosses") == "Derrota a 4 jefes"
    path.write_text("{ this is not json", encoding="utf-8")
    tr._checked = 0
    assert tr("Boss Slayer") == "Matajefes"                      # a typo while editing keeps the last good translations
    path.unlink()
    tr._checked = 0
    assert tr("Boss Slayer") == "Cazajefes"                      # no file at all: the built-in texts
    assert i18n.Translator(enabled=False)("Boss Slayer") == "Boss Slayer" and i18n.Translator()(None) is None and i18n.Translator()("  ") == "  "


def test_effect_codes_are_described_in_spanish():
    d = i18n.describe_object_effect
    assert d("on_hard_evade:heal:15") == "Al esquivar en difícil: curas 15 HP" and d("auto_evade:easy") == "Esquive automático en dificultad fácil"
    assert d("damage_reduction.easy:100") == "Reduces el daño un 100 % en fácil" and d("damage_reduction.medium:+50") == "+50 % de reducción de daño en media"
    assert d("on_boss_stunned:black_flash") == "Con el jefe aturdido: Black Flash" and d("stun_enemy:2.5") == "Aturdes al enemigo 2,5 s"
    assert d("something_odd:3") == "something odd:3"                    # unknown codes are shown, not hidden
    assert i18n.describe_skill_effect("cooldown_reduction:0.10") == "−10 % de enfriamiento de los poderes por rango" and i18n.describe_skill_effect("nope") == ""


# ---- over the wire: client -> server -> bridge -> panel ------------------------------------------------------------------------
import asyncio  # noqa: E402

from test_activity_play import Rig, frame, run  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


class PanelRig(Rig):
    """The play rig with the panel's tables in the bot, a few more people to see on the board, and a channel that can store pictures.
    `me` is the player whose data it is (a test window on this PC has a negative id made from its name)."""

    def __init__(self, me: int = ME, **kwargs):
        super().__init__(**kwargs)
        self.me = me

    async def __aenter__(self):
        await super().__aenter__()
        self._tmp = tempfile.TemporaryDirectory()
        panel_app = self.panel_app = make_app(Path(self._tmp.name), me=self.me)
        for key, value in vars(panel_app).items():
            setattr(self.app, key, value)
        self.app.bot.fetch_user = self._fetch_user
        stored = self.stored = []

        async def send(content=None, **kwargs):
            stored.append((content, kwargs["file"].filename))
            return NS(attachments=[NS(url=f"https://cdn.discordapp.com/attachments/10/{len(stored)}/{kwargs['file'].filename}")])
        self.channel.send = send

        async def history(**kwargs):                        # an empty channel
            return
            yield                                           # noqa: B901 - makes this an async generator
        self.channel.history = history
        return self

    async def _fetch_user(self, uid):
        names = {OTHER: "Mina", self.me: "Ana"}
        if uid not in names:
            raise LookupError(uid)
        return NS(display_name=names[uid], name=names[uid].lower(), display_avatar=NS(url=f"https://cdn.discordapp.com/avatars/{uid}/a.png"))

    async def __aexit__(self, *exc):
        await super().__aexit__(*exc)
        self._tmp.cleanup()

    async def ask(self, ws, op, **args):
        self.calls_made = getattr(self, "calls_made", 0) + 1
        call = f"r{self.calls_made}"                                          # the server keeps at most 32 characters of an id
        await ws.send_json({"t": "rpc", "id": call, "op": op, "args": args})
        while True:
            got = await asyncio.wait_for(ws.receive_json(), 3)
            if got.get("id") == call and got["t"] in ("rpc_ok", "rpc_err"):
                return got


def test_the_dashboards_answer_over_the_socket_for_the_player_who_asks():
    async def scenario():
        async with PanelRig() as rig:
            ws, welcome = await rig.login()
            out = {}
            for op in ("panel.profile", "panel.achievements", "panel.skills", "panel.inventory", "panel.images", "panel.characters"):
                out[op] = await rig.ask(ws, op)
            out["board"] = await rig.ask(ws, "panel.board", category="success_rate")
            out["board_bf"] = await rig.ask(ws, "panel.board", category="black_flashes")
            out["bad_board"] = await rig.ask(ws, "panel.board", category="hacker")
            out["ids_are_ignored"] = await rig.ask(ws, "panel.profile", uid=222, user_id=222)      # the page cannot ask as somebody else
            out["unknown"] = await rig.ask(ws, "panel.delete_everything")
            return out

    out = run(scenario())
    assert all(v["t"] == "rpc_ok" for k, v in out.items() if k not in ("bad_board", "unknown"))
    assert out["panel.profile"]["data"]["stats"]["attempts"] == 20 and out["ids_are_ignored"]["data"]["stats"]["attempts"] == 20
    assert out["panel.achievements"]["data"]["unlocked"] == 2 and out["panel.skills"]["data"]["points"] == 3
    assert [o["id"] for o in out["panel.inventory"]["data"]["objects"]] == ["reactive_core", "mirror_shard"]
    assert [c["name"] for c in out["panel.characters"]["data"]["characters"]] == ["Kuro", "Shiro"]
    board = out["board"]["data"]
    assert [(r["rank"], r["name"], r["me"]) for r in board["rows"]] == [(1, "Mina", False), (2, "Ana", True)] and board["rows"][0]["avatar"].endswith("222/a.png")
    assert board["me"] is None and board["total"] == 2
    assert out["bad_board"]["t"] == "rpc_err" and "no existe" in out["bad_board"]["reason"]
    assert out["unknown"]["t"] == "rpc_err" and "no existe" in out["unknown"]["reason"]


def test_changes_from_the_dashboards_are_checked_saved_and_announced_to_every_screen_of_the_player():
    async def scenario():
        async with PanelRig() as rig:
            ws, _ = await rig.login()
            second, _ = await rig.login()                                   # the same player on their phone
            await asyncio.sleep(0.05)
            learned = await rig.ask(ws, "panel.learn", id="combat_2a")
            refused = await rig.ask(ws, "panel.learn", id="defense_2a")
            registered = await rig.ask(ws, "panel.register", name="Zed")
            phone = await frame(second, "chars")
            dup = await rig.ask(ws, "panel.register", name="Mina")
            power = await rig.ask(ws, "panel.power", character="Zed", slot=1, name="Rayo", description="Un rayo", type="destructive", cooldown=30, effect="damage:40")
            bad_power = await rig.ask(ws, "panel.power", character="Mina", slot=1, name="Rayo", description="Un rayo", type="destructive", cooldown=30, effect="damage:40")
            title = await rig.ask(ws, "panel.title", title="∞ Infinity")
            domain = await rig.ask(ws, "panel.domain", id="nope")
            image = await rig.ask(ws, "panel.image_add", url="https://cdn.discordapp.com/new.png")
            gone = await rig.ask(ws, "panel.unregister", name="Zed")
            return rig.panel_app, learned, refused, registered, phone, dup, power, bad_power, title, domain, image, gone

    app, learned, refused, registered, phone, dup, power, bad_power, title, domain, image, gone = run(scenario())
    assert learned["data"]["rank"] == 1 and learned["data"]["points"] == 1 and learned["data"]["skills"]["points"] == 1
    assert refused["t"] == "rpc_err" and "Te falta" in refused["reason"]
    assert [c["name"] for c in registered["data"]["characters"]] == ["Kuro", "Shiro", "Zed"]
    assert phone == {"t": "chars", "characters": ["Kuro", "Shiro", "Zed"], "charAvatars": {}}
    assert dup["t"] == "rpc_err" and "ya está registrado" in dup["reason"]
    assert power["t"] == "rpc_ok" and app.character_powers["Zed"]["power1"]["effect"] == "damage:40"
    assert bad_power["t"] == "rpc_err" and "no es tuyo" in bad_power["reason"]
    assert title["data"] == {"activeTitle": "∞ Infinity"} and domain["t"] == "rpc_err"
    assert image["data"]["images"][-1].endswith("new.png") and "Zed" not in app.character_registry and gone["t"] == "rpc_ok"
    assert app.saves >= 5


def test_a_game_master_may_fix_the_power_of_any_character_but_a_player_may_not():
    async def scenario():
        async with PanelRig() as rig:
            ws, _ = await rig.login()
            player = await rig.ask(ws, "panel.power", character="Mina", slot=2, name="X", description="y", type="defend", cooldown=1, effect="stun")
            rig.app.is_admin = lambda member: True
            gm = await rig.ask(ws, "panel.power", character="Mina", slot=2, name="X", description="y", type="defend", cooldown=1, effect="stun")
            return player, gm

    player, gm = run(scenario())
    assert player["t"] == "rpc_err" and gm["t"] == "rpc_ok"


def post(rig, body, headers=None):
    return rig.http.post(f"http://127.0.0.1:{rig.port}/api/upload", data=body, headers={"X-Dev": "Ana", **(headers or {})})


def test_a_picture_from_the_device_is_checked_and_kept_on_discord_without_cluttering_the_mirror():
    async def scenario():
        async with PanelRig() as rig:
            ok = await post(rig, PNG, {"X-Filename": "mi%20foto%20genial.png"})
            ok_body = await ok.json()
            fake = await post(rig, b"<svg onload=alert(1)></svg>")
            gif = await post(rig, b"GIF89a" + b"\x00" * 20)
            huge = await post(rig, PNG + b"\x00" * (9 * 1024 * 1024 + 10))
            nobody = await rig.http.post(f"http://127.0.0.1:{rig.port}/api/upload", data=PNG)
            tunnel = await rig.http.post(f"http://127.0.0.1:{rig.port}/api/upload", data=PNG, headers={"X-Dev": "Ana", "X-Forwarded-For": "1.2.3.4"})
            limited = []
            for _ in range(8):
                limited.append((await post(rig, PNG)).status)
            hidden = rig.bridge._mine(NS(channel=NS(id=10), content="📁 (Image storage - ignore)"))
            hidden_here = rig.bridge._mine(NS(channel=NS(id=10), content="📁 (Almacén de imágenes de la Actividad: ignorar)"))
            normal = rig.bridge._mine(NS(channel=NS(id=10), content="hola"))
            return rig.stored, ok.status, ok_body, fake.status, await fake.json(), gif.status, huge.status, nobody.status, tunnel.status, limited, hidden, hidden_here, normal

    stored, ok_status, ok_body, fake_status, fake_body, gif_status, huge_status, nobody, tunnel, limited, hidden, hidden_here, normal = run(scenario())
    assert ok_status == 200 and ok_body["url"].startswith("https://cdn.discordapp.com/attachments/") and stored[0][1] == "mi_foto_genial.png"
    assert "Almacén de imágenes" in stored[0][0]
    assert fake_status == 400 and "PNG, JPG, GIF o WebP" in fake_body["error"] and gif_status == 200
    assert huge_status == 413 and nobody == 401 and tunnel == 401
    assert limited.count(200) <= 4 and 400 in limited                              # at most 6 a minute for one person
    assert hidden is False and hidden_here is False and normal is True


def test_the_sniffing_of_pictures_trusts_bytes_not_names():
    from eventos_app.activity.panel_rpc import sniff_image
    assert sniff_image(PNG) == ("image/png", ".png") and sniff_image(b"\xff\xd8\xff\xe0abc")[0] == "image/jpeg"
    assert sniff_image(b"GIF87a....")[0] == "image/gif" and sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ")[0] == "image/webp"
    for bad in (b"", b"<svg/>", b"MZ\x90\x00", b"RIFF\x00\x00\x00\x00WAVEfmt ", b"%PDF-1.7"):
        assert sniff_image(bad) is None
