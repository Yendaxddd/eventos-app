"""Turns the bot's English into Spanish as it is sent, using the catalogue made from its own source (extract.py).

A catalogue entry is a *template*: the English text with `{1}`, `{2}`... where the bot puts values, and its Spanish with the same
slots. A field that is exactly one of the texts is swapped whole; otherwise every template is looked for inside it (a message is
often several of them glued together) and each match is replaced by its Spanish, with the values it carried moved to their place.
A value that is itself a known word (a difficulty, a status) is translated too. What was already translated is never looked at again,
and text the catalogue does not know (what players write, names) is left exactly as it was.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "catalog_es.json"
SLOT = re.compile(r"\{(\d+)\}")
_PROTECT = "%d"
_PROTECTED = re.compile("(\\d+)")
MIN_ANCHOR = 4                       # a template is only looked for inside longer text when it has this many letters in a row

# values the bot drops into its sentences
VOCAB = {
    "easy": "fácil", "medium": "media", "hard": "difícil", "impossible": "imposible",
    "single": "individual", "group": "grupal", "combo": "combo", "direction": "dirección", "fake": "falso",
    "burn": "quemadura", "poison": "veneno", "bleed": "sangrado", "freeze": "congelación", "stun": "aturdimiento", "weaken": "debilidad",
    "slow": "lentitud", "curse": "maldición", "shield": "escudo", "attack": "ataque", "defense": "defensa", "speed": "velocidad",
    "destructive": "destructivo", "support": "apoyo", "defend": "defensa", "build": "construcción", "control": "control",
    "active": "activo", "inactive": "inactivo", "enabled": "activado", "disabled": "desactivado", "on": "activado", "off": "desactivado",
    "yes": "sí", "no": "no", "none": "ninguno", "true": "sí", "false": "no", "unknown": "desconocido",
}


def load_catalog(path: Path = CATALOG) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {e["id"]: e for e in data}


def _parts(template: str) -> list[str | int]:
    """«✅ {1} evaded! ({2}s)» -> ["✅ ", 1, " evaded! (", 2, "s)"], with doubled braces made single."""
    out: list[str | int] = []
    pos = 0
    for m in SLOT.finditer(template):
        out.append(template[pos:m.start()].replace("{{", "{").replace("}}", "}"))
        out.append(int(m.group(1)))
        pos = m.end()
    out.append(template[pos:].replace("{{", "{").replace("}}", "}"))
    return [p for p in out if p != ""]


class Translator:
    def __init__(self, entries, vocab: dict | None = None) -> None:
        self.vocab = {**VOCAB, **(vocab or {})}
        self.exact: dict[str, dict[str, str]] = {"user": {}, "console": {}}
        self.patterns: dict[str, list] = {"user": [], "console": []}
        for e in entries:
            en, es, kind = e.get("en"), e.get("es"), e.get("kind", "user")
            if not en or not es or es == en or kind not in self.exact:
                continue
            if sorted(SLOT.findall(en)) != sorted(SLOT.findall(es)):
                continue                                    # a broken translation is never used
            if not SLOT.search(en):
                plain = en.replace("{{", "{").replace("}}", "}")
                self.exact[kind][plain.strip()] = es.replace("{{", "{").replace("}}", "}").strip()
                if " " not in plain.strip():
                    continue                                # a lone word only ever replaces a whole field
            compiled = self._compile(en)
            if compiled is not None:
                self.patterns[kind].append((compiled[0], compiled[1], compiled[2], es))
        for kind in self.patterns:
            self.patterns[kind].sort(key=lambda p: -p[2])
        self.cached = lru_cache(maxsize=4096)(self._translate)

    @staticmethod
    def _compile(en: str):
        parts = _parts(en)
        literals = [p for p in parts if isinstance(p, str)]
        letters = max((len(m) for lit in literals for m in re.findall(r"[^\W\d_][\w' ]*[^\W\d_]", lit)), default=0)
        if letters < MIN_ANCHOR:
            return None
        regex, groups = [], []
        for i, p in enumerate(parts):
            if isinstance(p, str):
                piece = re.escape(p)
                if i == 0 and p[:1].isalnum():
                    piece = r"(?<!\w)" + piece
                if i == len(parts) - 1 and p[-1:].isalnum():
                    piece += r"(?!\w)"
                regex.append(piece)
            else:
                groups.append(p)
                if i == len(parts) - 1:
                    regex.append(r"([^\n]*)")
                elif i == 0:
                    regex.append(r"([^\n]*?)")
                else:
                    regex.append(r"([\s\S]*?)")
        anchor = max(literals, key=len)
        try:
            return re.compile("".join(regex)), (anchor, groups), sum(len(x) for x in literals)
        except re.error:
            return None

    def _value(self, value: str, kind: str) -> str:
        word = value.strip()
        low = word.lower()
        if low in self.vocab:
            spanish = self.vocab[low]
            spanish = spanish.upper() if word.isupper() and len(word) > 1 else spanish.capitalize() if word[:1].isupper() else spanish
            return value.replace(word, spanish)
        if len(word) > 12 and " " in word:
            return self._translate(value, kind, depth=1)
        return value

    def _translate(self, text: str, kind: str = "user", depth: int = 0) -> str:
        if not text or not isinstance(text, str):
            return text
        stripped = text.strip()
        exact = self.exact.get(kind, {})
        if stripped in exact:
            return text.replace(stripped, exact[stripped], 1)
        saved: list[str] = []
        out = text
        for regex, (anchor, groups), _, es in self.patterns.get(kind, ()):
            if anchor not in out:
                continue

            def swap(m, groups=groups, es=es):
                values = {n: self._value(m.group(i + 1), kind) if depth == 0 else m.group(i + 1) for i, n in enumerate(groups)}
                spanish = SLOT.sub(lambda s: values.get(int(s.group(1)), s.group(0)), es).replace("{{", "{").replace("}}", "}")
                saved.append(spanish)
                return _PROTECT % (len(saved) - 1)

            out = regex.sub(swap, out)
        if not saved:
            return out
        while _PROTECTED.search(out):
            out = _PROTECTED.sub(lambda m: saved[int(m.group(1))], out)
        return out

    def text(self, text, kind: str = "user"):
        if not isinstance(text, str) or not text:
            return text
        try:
            return self.cached(text, kind)
        except Exception:  # noqa: BLE001 - a translation must never stop a message
            return text

    def embed_dict(self, data: dict) -> dict:
        """An embed as discord.py turns it into JSON, with its texts translated."""
        out = dict(data)
        for key in ("title", "description"):
            if key in out:
                out[key] = self.text(out[key])
        for key in ("footer", "author"):
            if isinstance(out.get(key), dict):
                part = dict(out[key])
                for name in ("text", "name"):
                    if name in part:
                        part[name] = self.text(part[name])
                out[key] = part
        if isinstance(out.get("fields"), list):
            out["fields"] = [{**f, "name": self.text(f.get("name")), "value": self.text(f.get("value"))} if isinstance(f, dict) else f for f in out["fields"]]
        return out


def load(path: Path = CATALOG) -> Translator:
    return Translator(load_catalog(path).values())
