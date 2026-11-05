"""Finds the English text the bot shows (in Discord, and in the app's log) so it can be translated.

The bot's source is never changed: its strings are read here (with Python's own parser) and turned into *templates* --
`"✅ {1} evaded! ({2}s)"` for `f"✅ {mention} evaded! ({t:.2f}s)"` -- that the translation layer (translator.py) recognises
in what the bot sends. Run `python -m eventos_app.lang.extract` to list what is new since the catalogue was written.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

BOT_FILE = Path(__file__).resolve().parents[2] / "advanced_qte_hp_system_debug.py"

# calls whose text reaches people in Discord, and calls that write the app's log
SHOWN = {"send", "reply", "edit", "send_message", "Embed", "add_field", "set_footer", "set_author", "edit_message", "webhook_send", "safe_send",
         "feedback", "Choice", "describe", "command", "send_modal", "edit_original_response", "TextInput", "Button", "Select", "SelectOption",
         "Modal", "followup", "insert_field_at", "set_field_at", "Group", "Parameter", "Range"}
CONSOLE = {"print"}
# calls whose string arguments are never text for people
NOT_TEXT = {"get", "getattr", "setattr", "hasattr", "startswith", "endswith", "split", "rsplit", "replace", "strip", "lstrip", "rstrip", "join",
            "open", "exists", "join_path", "loads", "dumps", "load", "dump", "compile", "match", "search", "sub", "findall", "fullmatch", "strptime",
            "strftime", "getenv", "environ", "int", "float", "isinstance", "pop", "setdefault", "index", "count", "find", "encode", "decode", "Path",
            "info", "debug", "warning", "error", "exception", "critical", "log", "format_exc", "add_reaction", "remove_reaction", "fromisoformat",
            "Color", "from_rgb", "from_str", "re_compile", "time", "sleep", "lower", "upper", "title", "capitalize", "partial", "emit_event", "feedback_kind"}
WORD = re.compile(r"[A-Za-z]{2,}")


@dataclass(frozen=True)
class Template:
    id: str
    en: str          # the text with `{1}`, `{2}`... where the bot puts values
    kind: str        # "user" (Discord) or "console" (the app's log)
    slots: int


def template_of(node: ast.AST) -> tuple[str, int] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, 0
    if isinstance(node, ast.JoinedStr):
        parts, n = [], 0
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value).replace("{", "{{").replace("}", "}}"))
            else:
                n += 1
                parts.append("{%d}" % n)
        return "".join(parts), n
    return None


def literal_words(template: str) -> int:
    return len(WORD.findall(re.sub(r"\{\d+\}", " ", template)))


def is_text(template: str, slots: int, direct: bool) -> bool:
    """Is this something a person reads (not a key, an identifier, a URL...)?"""
    bare = re.sub(r"\{\d+\}", "", template).strip()
    if not bare or "://" in template or re.search(r"\.(json|png|gif|jpe?g|webp|txt|py|log|db|mp3|ogg|wav)$", bare, re.I):
        return False
    if re.fullmatch(r"[a-z0-9_]+", bare) or re.fullmatch(r"\*[a-z0-9_]+\*", bare):       # identifiers and the *commands* players type
        return False
    words = literal_words(template)
    if words >= 2:
        return True
    return direct and words == 1 and len(bare) >= 2 and bool(re.search(r"[A-Za-z]{2,}", bare))       # a lone word shown on its own (a field name, a button)


def _make_id(kind: str, en: str) -> str:
    return hashlib.sha1(f"{kind}\x00{en}".encode("utf-8")).hexdigest()[:12]


def extract(path: Path = BOT_FILE) -> list[Template]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def call_name(call: ast.Call) -> str:
        f = call.func
        return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""

    def context(node: ast.AST) -> tuple[str | None, bool]:
        """(kind, direct): which call the string ends up in, if any, and whether it is that call's own argument."""
        child, parent, direct = node, parents.get(node), True
        while parent is not None:
            if isinstance(parent, ast.Call):
                name = call_name(parent)
                if child is parent.func:
                    return None, False
                if name in NOT_TEXT:
                    return None, False
                if name in CONSOLE or (name == "print" and isinstance(parent.func, ast.Attribute)):
                    return "console", direct
                if name in SHOWN:
                    return "user", direct
                direct = False
            elif isinstance(parent, (ast.Compare, ast.Subscript)) or (isinstance(parent, ast.Dict) and child in parent.keys):
                return None, False
            elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                return "loose", False
            elif not isinstance(parent, (ast.BinOp, ast.IfExp, ast.keyword, ast.List, ast.Tuple, ast.Dict, ast.Starred, ast.JoinedStr, ast.FormattedValue)):
                direct = False
            child, parent = parent, parents.get(parent)
        return "loose", False

    found: dict[tuple[str, str], Template] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.JoinedStr)) or (isinstance(node, ast.Constant) and not isinstance(node.value, str)):
            continue
        parent = parents.get(node)
        if isinstance(parent, (ast.JoinedStr, ast.FormattedValue)):
            continue                                       # a piece of an f-string: the whole f-string is the template
        if isinstance(parent, ast.Expr):
            continue                                       # a docstring
        made = template_of(node)
        if made is None:
            continue
        en, slots = made
        kind, direct = context(node)
        if kind is None:
            continue
        if kind == "loose":                                # a string kept in a variable or a table and shown later: only clear sentences
            if literal_words(en) < 3 or not re.search(r"[A-Za-z]{3,}", en):
                continue
            kind = "user"
        if not is_text(en, slots, direct):
            continue
        key = (kind, en)
        if key not in found:
            found[key] = Template(_make_id(kind, en), en, kind, slots)
    return sorted(found.values(), key=lambda t: (t.kind, t.en))


if __name__ == "__main__":
    import json
    import sys

    from .translator import load_catalog
    known = set(load_catalog())
    new = [t for t in extract() if t.id not in known]
    json.dump([t.__dict__ for t in new], sys.stdout, ensure_ascii=False, indent=1)
    print(f"\n{len(new)} new", file=sys.stderr)
