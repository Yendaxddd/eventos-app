"""The game-master panel is written against the bot's own attributes and methods, and the tests of it use a made-up bot. This keeps the made-up
bot honest: every attribute the panel touches exists in the real bot's source, and every method it calls is called the way the real one is
declared. If the bot is renamed or reshaped, this fails here instead of in the middle of an event."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BOT = ROOT / "advanced_qte_hp_system_debug.py"
GM_FILES = sorted((ROOT / "eventos_app" / "activity" / "gm").glob("*.py")) + [ROOT / "eventos_app" / "activity" / "gm_rpc.py", ROOT / "eventos_app" / "activity" / "panel.py"]

# what the panel launches by building the method's name (`trigger_{mode}_qte`): the shapes it calls them with
DYNAMIC_CALLS = {"trigger_single_qte": (1, {"target_member", "is_targeted"}), "trigger_group_qte": (1, set()),
                 "trigger_combo_qte": (3, set()), "trigger_direction_qte": (3, set()), "trigger_fake_qte": (3, set())}


def bot_source() -> str:
    return BOT.read_text(encoding="utf-8")


def is_app(node: ast.AST) -> bool:
    """`app` or `self.app`."""
    return (isinstance(node, ast.Name) and node.id == "app") or (isinstance(node, ast.Attribute) and node.attr == "app" and isinstance(node.value, ast.Name) and node.value.id == "self")


def names_used() -> tuple[dict[str, set[str]], dict[str, set[str]], list[tuple[str, ast.Call, str]]]:
    """(attributes read or written directly, attributes asked for with getattr, calls of the form app.method(...)), over the panel's files."""
    direct: dict[str, set[str]] = {}
    asked: dict[str, set[str]] = {}
    calls: list[tuple[str, ast.Call, str]] = []
    for path in GM_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and is_app(node.value):
                direct.setdefault(node.attr, set()).add(path.name)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr", "hasattr") and node.args and is_app(node.args[0]) \
                        and len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    asked.setdefault(node.args[1].value, set()).add(path.name)
                if isinstance(node.func, ast.Attribute) and is_app(node.func.value):
                    calls.append((node.func.attr, node, path.name))
    return direct, asked, calls


def defined_in_bot(name: str, source: str) -> bool:
    escaped = re.escape(name)
    return bool(re.search(rf"self\.{escaped}\s*(?::[^=\n]+)?=(?!=)", source) or re.search(rf"def {escaped}\(", source) or re.search(rf"^\s+{escaped}\s*(?::[^=\n]+)?=", source, re.M))


def bot_methods() -> dict[str, ast.AST]:
    tree = ast.parse(bot_source())
    found: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("__"):
                    found.setdefault(item.name, item)
    return found


def problem_with(function: ast.AST, positional: int, keywords: set[str]) -> str | None:
    """Why a call with this shape would fail against this declaration, or None."""
    args = function.args
    params = [a.arg for a in args.posonlyargs + args.args]
    if params and params[0] == "self":
        params = params[1:]
    if positional > len(params) and not args.vararg:
        return f"{positional} positional arguments for {len(params)} parameters"
    bound = set(params[:positional])
    kwonly = {a.arg for a in args.kwonlyargs}
    for keyword in keywords:
        if keyword in bound:
            return f"{keyword} is given twice"
        if keyword not in params and keyword not in kwonly and not args.kwarg:
            return f"unknown keyword {keyword}"
    required = params[: len(params) - len(args.defaults)]
    missing = [p for p in required if p not in bound and p not in keywords]
    required_kwonly = [a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None]
    missing += [p for p in required_kwonly if p not in keywords]
    return f"missing {missing}" if missing else None


def test_every_attribute_the_panel_touches_exists_in_the_real_bot():
    direct, asked, _ = names_used()
    source = bot_source()
    assert len(direct) > 40 and len(asked) > 20                                    # the scan found the panel's code
    missing = {name: sorted(files) for name, files in {**asked, **direct}.items() if not defined_in_bot(name, source)}
    assert missing == {}


def test_every_method_the_panel_calls_is_called_the_way_the_real_one_is_declared():
    _, _, calls = names_used()
    methods = bot_methods()
    checked, wrong = 0, []
    for name, call, where in calls:
        if name not in methods:
            continue                                                                # an attribute that is called (a callback the bot stores), not a method
        if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
            continue
        checked += 1
        reason = problem_with(methods[name], len(call.args), {k.arg for k in call.keywords})
        if reason:
            wrong.append(f"{where}: app.{name}(...) -> {reason}")
    assert checked >= 15 and wrong == []


def test_the_qtes_the_panel_launches_by_name_are_declared_the_way_it_calls_them():
    methods = bot_methods()
    for name, (positional, keywords) in DYNAMIC_CALLS.items():
        assert name in methods, name
        assert problem_with(methods[name], positional, keywords) is None, name


# ---- the one thing the panel added to the bot -------------------------------------------------------------------------------------------
def test_the_live_config_the_panel_saves_is_what_the_bot_loads_back_after_a_restart(tmp_path, monkeypatch):
    import asyncio
    import json

    from eventos_app import paths
    from eventos_app.activity.gm import GmLog, GmPanel
    from eventos_app.activity.gm.values import SPECS

    monkeypatch.setenv("EVENTOS_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_home_cache", None)
    import advanced_qte_hp_system_debug as module

    files = {}                                                                          # the bot's data files, in memory: never touch the real ones
    monkeypatch.setattr(module, "save_data", lambda name, data: files.__setitem__(name, json.loads(json.dumps(data))))
    monkeypatch.setattr(module, "load_data", lambda name, default: files.get(name, default))

    def shell():
        bot = object.__new__(module.AdvancedQTEBot)
        for spec in SPECS:                                                                # every number the panel lists exists, at a harmless value
            setattr(bot, spec.key, False if spec.kind == "bool" else spec.lo)
        bot.qte_times = {"easy": {"evade_window": 6.0, "parry_window": (4.0, 7.0), "perfect_parry": 5.5}}
        bot.qte_timeout_durations = {"easy": 6.75}
        bot.qte_timings = {"easy": {"evade_window": 6.0, "parry_start": 4.0, "parry_end": 7.0}}
        bot.damage_ranges = {"easy": (1, 3)}
        bot.revenge_threshold, bot.revenge_damage_multiplier, bot.revenge_bf_bonus = 0.20, 1.5, 0.10
        bot.bf_timing_window, bot.ultimate_base_cooldown = 0.2, 600
        bot.charge_per_damage_dealt, bot.ultimate_max_damage = 2.0, 500
        return bot

    first = shell()
    gm = GmPanel(first, GmLog(None), None, None)
    for key, value in (("revenge_threshold", 35), ("revenge_damage_multiplier", 2.5), ("bf_timing_window", 0.4), ("ultimate_base_cooldown", 900), ("ultimate_max_damage", 750)):
        asyncio.run(gm.set_value("Gus", key, value))
    assert files["live_config"]["revenge_threshold"] == 0.35 and files["live_config"]["ultimate_max_damage"] == 750
    second = shell()                                                                    # the bot starts again with its own defaults...
    second._load_live_config()                                                          # ...and reads what the panel saved
    assert (second.revenge_threshold, second.revenge_damage_multiplier, second.bf_timing_window, second.ultimate_base_cooldown, second.ultimate_max_damage) \
        == (0.35, 2.5, 0.4, 900, 750)
