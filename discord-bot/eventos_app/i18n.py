"""Spanish for the texts the game masters wrote (achievements, skills, objects...) and for the effect codes behind them.

The bot's data files are written in English (`"Dodge 5 attacks in a row without getting hit"`, `"damage_reduction:50"`). The
Activity shows them in Spanish: first an exact phrase table, then a few patterns, then the text as it came. Game masters can
add their own translations in `data/i18n_es.json`:

    {"exact": {"Boss Slayer": "Cazajefes"}, "patterns": [["^Kill (\\d+) bosses$", "Derrota a \\1 jefes"]]}

so a name nobody translated can be fixed without touching the game's files. Texts that are not in any table are left alone.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

# ---- the stock content ----------------------------------------------------------------------------------------------
EXACT_ES: dict[str, str] = {
    # achievement categories
    "Combat": "Combate", "Defense": "Defensa", "Mastery": "Maestría", "Special": "Especial", "Domain Expansion": "Expansión de dominio",
    # achievements: names (the ones that read as a phrase) and what they ask for
    "Quick Feet": "Pies ligeros", "Untouchable": "Intocable", "Perfect Defense": "Defensa perfecta", "Black Spark": "Chispa negra",
    "Chain Lightning": "Cadena de rayos", "Counter Strike": "Contragolpe", "Survivor": "Superviviente", "Wrath": "Ira",
    "Boss Slayer": "Cazajefes", "Incriminating Evidence": "Pruebas incriminatorias", "Soul Manipulator": "Manipulador de almas",
    "Cursed Partners": "Compañeros malditos", "Revengeful Curse": "Maldición vengativa", "Restless Gambler": "Apostador inquieto",
    "Dodge 5 attacks in a row without getting hit": "Esquiva 5 ataques seguidos sin que te golpeen",
    "Hit 3 Critical counters in a single bossfight": "Logra 3 contraataques críticos en un mismo combate contra un jefe",
    "Make a parry at less than 15 HP": "Haz un parry con menos de 15 HP",
    "Survive a bossfight without receiving ANY damage at all": "Sobrevive a un combate contra un jefe sin recibir NINGÚN daño",
    "Save someone under 5HP OR save someone from 4 impossible QTEs in a streak":
        "Salva a alguien con menos de 5 HP O salva a alguien de 4 QTE imposibles seguidos",
    "In a single bossfight: Deal the last hit, save 5 people, AND deal minimum 300 damage":
        "En un mismo combate contra un jefe: da el golpe final, salva a 5 personas Y causa al menos 300 de daño",
    "Kill 2 bosses in streak with 2+ black flashes each, then land a 3rd black flash under 50HP":
        "Derrota a 2 jefes seguidos con 2 o más Black Flash en cada uno y después logra un tercer Black Flash con menos de 50 HP",
    "Successfully evade your first QTE": "Esquiva con éxito tu primer QTE",
    "Evade 100 QTEs": "Esquiva 100 QTE",
    "Successfully parry your first QTE": "Haz con éxito tu primer parry",
    "Land your first Black Flash": "Logra tu primer Black Flash",
    "Land a 4-chain Black Flash combo": "Logra una cadena de 4 Black Flash",
    "Land 50 counter attacks": "Acierta 50 contraataques",
    "Win a fight with less than 10 HP": "Gana un combate con menos de 10 HP",
    "Defeat a boss while in REVENGE mode": "Derrota a un jefe estando en modo VENGANZA",
    "Participate in defeating 10 bosses": "Participa en la derrota de 10 jefes",
    # titles that come with them
    "Nimble": "Ágil", "The Untouchable": "El Intocable", "Flash User": "Usuario del Flash", "Chain Master": "Maestro de la cadena",
    "Wrathful": "Iracundo", "High Roller": "Gran apostador", "The Untouched": "El Intacto", "True Love": "Amor verdadero",
    "Professional Lawyer": "Abogado profesional", "Cursed Avenger": "Vengador maldito",
    # domains
    "Traps enemies in infinite information, stunning them completely.": "Atrapa a los enemigos en información infinita y los deja aturdidos por completo.",
    "A domain of chance where fate is determined by the roll of slots.": "Un dominio de azar donde el destino lo decide el giro de las tragaperras.",
    "A domain of reflection where ALL attacks return to the boss.": "Un dominio de reflejo donde TODOS los ataques vuelven contra el jefe.",
    "A domain of relentless destruction with a devastating finisher.": "Un dominio de destrucción implacable con un remate devastador.",
    "A domain of true partnership with 3 special attacks, overspec counters, and Jacob's Ladder finisher.":
        "Un dominio de verdadera alianza con 3 ataques especiales, contraataques «overspec» y el remate Escalera de Jacob.",
    "A courtroom domain where AI judges the battle. Win to gain the Executioner Sword.":
        "Un dominio de tribunal donde una IA juzga el combate. Si ganas, obtienes la Espada del Verdugo.",
    "A domain where all evades become instant perfect counters. Stacks Transfiguration for exponential damage.":
        "Un dominio donde todos los esquives se vuelven contraataques perfectos al instante. Acumula Transfiguración para un daño exponencial.",
    # skill tree
    "Example Skill Tree": "Árbol de habilidades de ejemplo",
    "A template skill tree showing the branching structure": "Un árbol de ejemplo que muestra cómo se ramifican las habilidades",
    "Combat Mastery": "Maestría de combate", "Offensive combat abilities": "Habilidades ofensivas de combate",
    "Defensive Arts": "Artes defensivas", "Survival and protection abilities": "Habilidades de supervivencia y protección",
    "Utility & Support": "Utilidad y apoyo", "Charge, healing, and team abilities": "Habilidades de carga, curación y equipo",
    "Quick Reflexes": "Reflejos rápidos", "Power Strike": "Golpe poderoso", "Perfect Timing": "Tiempo perfecto",
    "Iron Will": "Voluntad de hierro", "Second Wind": "Segundo aliento", "Parry Master": "Maestro del parry",
    "Power Surge": "Oleada de poder", "Rapid Recovery": "Recuperación rápida", "Cooldown Reduction": "Reducción de enfriamiento",
    "+0.1s evade window": "+0,1 s a la ventana de esquive", "+10% counter damage": "+10 % de daño de contraataque",
    "+5% Black Flash chance": "+5 % de probabilidad de Black Flash", "-5% damage taken": "−5 % de daño recibido",
    "Survive fatal blow once per fight at 1 HP": "Sobrevives a un golpe mortal con 1 HP, una vez por combate",
    "+0.2s parry window": "+0,2 s a la ventana de parry", "+1% ultimate charge per action": "+1 % de carga de ultimate por acción",
    "+5 HP regen at checkpoints": "+5 HP de regeneración en los checkpoints", "-10% power cooldowns": "−10 % de enfriamiento de los poderes",
    # special objects (stock)
    "Mirror Shard": "Fragmento de espejo", "Reactive Core": "Núcleo reactivo",
    "A fragment of an ancient mirror that reflects not just images, but techniques. Allows the wielder to study and eventually copy enemy attack patterns.":
        "Un fragmento de un espejo antiguo que no solo refleja imágenes, sino también técnicas. Permite a quien lo porta estudiar y, con el tiempo, copiar los patrones de ataque enemigos.",
    "Legend says this shard was once part of a mirror that showed warriors their perfect selves.":
        "La leyenda dice que este fragmento fue parte de un espejo que mostraba a los guerreros su yo perfecto.",
    "A mysterious artifact that pulses with adaptive energy. When equipped, it allows the wielder to adapt to incoming attacks, building resistance over time.":
        "Un artefacto misterioso que late con energía adaptativa. Equipado, permite a quien lo porta adaptarse a los ataques que recibe y crear resistencia con el tiempo.",
    "Forged in the depths of the Void, this core learns from every strike it absorbs.":
        "Forjado en las profundidades del Vacío, este núcleo aprende de cada golpe que absorbe.",
    "Split Soul Katana": "Katana divisora de almas", "Executioner Sword": "Espada del Verdugo",
    "A cursed blade that splits the soul. Grants 1.5x damage multiplier when equipped.": "Una hoja maldita que parte el alma. Equipada, multiplica el daño por 1,5.",
    "Obtained from winning Deadly Sentencing. Grants 4x damage and special attacks.": "Se obtiene al ganar Deadly Sentencing. Multiplica el daño por 4 y da ataques especiales.",
}

# (pattern, replacement): for texts with numbers in them that are not in the table above
PATTERNS_ES: list[tuple[str, str]] = [
    (r"^Evade (\d+) QTEs?$", r"Esquiva \1 QTE"),
    (r"^Parry (\d+) QTEs?$", r"Haz \1 parry"),
    (r"^Land (\d+) counter ?attacks?$", r"Acierta \1 contraataques"),
    (r"^Land (\d+) Black Flash(?:es)?$", r"Logra \1 Black Flash"),
    (r"^Dodge (\d+) attacks in a row(?: without getting hit)?$", r"Esquiva \1 ataques seguidos"),
    (r"^Participate in defeating (\d+) bosses$", r"Participa en la derrota de \1 jefes"),
    (r"^Make a parry at less than (\d+) ?HP$", r"Haz un parry con menos de \1 HP"),
    (r"^Win a fight with less than (\d+) ?HP$", r"Gana un combate con menos de \1 HP"),
    (r"^\+(\d+(?:\.\d+)?)s evade window$", r"+\1 s a la ventana de esquive"),
    (r"^\+(\d+(?:\.\d+)?)s parry window$", r"+\1 s a la ventana de parry"),
    (r"^\+(\d+)% counter damage$", r"+\1 % de daño de contraataque"),
    (r"^\+(\d+)% Black Flash chance$", r"+\1 % de probabilidad de Black Flash"),
    (r"^-(\d+)% damage taken$", r"−\1 % de daño recibido"),
    (r"^-(\d+)% power cooldowns$", r"−\1 % de enfriamiento de los poderes"),
]

OVERRIDES_CHECK_EVERY = 2.0      # seconds between looks at the overrides file


class Translator:
    """`tr(text)` -> the Spanish text when it is known, else the text itself."""

    def __init__(self, exact: dict[str, str] | None = None, patterns: list[tuple[str, str]] | None = None,
                 overrides: Path | None = None, enabled: bool = True) -> None:
        self.exact = dict(EXACT_ES if exact is None else exact)
        self.patterns = [(re.compile(p, re.I), r) for p, r in (PATTERNS_ES if patterns is None else patterns)]
        self.overrides = overrides
        self.enabled = enabled
        self._extra_exact: dict[str, str] = {}
        self._extra_patterns: list[tuple[re.Pattern, str]] = []
        self._stamp: tuple[float, int] | None = None
        self._checked = 0.0

    # ---- the game masters' own translations -------------------------------------------------------------------------
    def _reload(self) -> None:
        now = time.monotonic()
        if self.overrides is None or now - self._checked < OVERRIDES_CHECK_EVERY:
            return
        self._checked = now
        try:
            stat = self.overrides.stat()
            stamp = (stat.st_mtime, stat.st_size)
        except OSError:
            if self._stamp is not None:
                self._stamp, self._extra_exact, self._extra_patterns = None, {}, []
            return
        if stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            data = json.loads(self.overrides.read_text(encoding="utf-8"))
            exact = {str(k): str(v) for k, v in (data.get("exact") or {}).items()} if isinstance(data, dict) else {}
            patterns = []
            for pair in (data.get("patterns") or []) if isinstance(data, dict) else []:
                try:
                    patterns.append((re.compile(str(pair[0]), re.I), str(pair[1])))
                except (re.error, IndexError, TypeError):
                    log.warning("i18n_es.json: pattern ignored: %r", pair)
            self._extra_exact, self._extra_patterns = exact, patterns
        except (OSError, ValueError):
            log.warning("could not read %s", self.overrides)

    def __call__(self, text):
        if not self.enabled or not isinstance(text, str) or not text.strip():
            return text
        self._reload()
        key = text.strip()
        for table in (self._extra_exact, self.exact):
            found = table.get(key)
            if found is not None:
                return found
        for pattern, replacement in (*self._extra_patterns, *self.patterns):
            if pattern.search(key):
                try:
                    return pattern.sub(replacement, key, count=1)
                except (re.error, IndexError):
                    continue
        return text


_shared = Translator()


def tr(text):
    """The Spanish text when it is known (see Translator), else the text itself."""
    return _shared(text)


def configure(overrides: Path | None = None, enabled: bool = True) -> Translator:
    """Point the shared translator at the game masters' file (the app does this once when it starts)."""
    global _shared
    _shared = Translator(overrides=overrides, enabled=enabled)
    return _shared


# ---- effect codes ----------------------------------------------------------------------------------------------------
DIFFICULTY_ES = {"easy": "fácil", "medium": "media", "hard": "difícil", "impossible": "imposible"}


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _fmt(value: float) -> str:
    """12.0 -> "12", 0.1 -> "0,1" (the decimal comma)."""
    rounded = round(value, 2)
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _pct(value: float) -> str:
    return _fmt(value * 100)


def describe_skill_effect(effect: str) -> str:
    """What a skill does per rank, from its code (`evade_window_bonus:0.1`)."""
    kind, _, raw = str(effect or "").partition(":")
    value = _num(raw)
    if value is None:
        return ""
    per = {
        "evade_window_bonus": lambda v: f"+{_fmt(v)} s a la ventana de esquive por rango",
        "parry_window_bonus": lambda v: f"+{_fmt(v)} s a la ventana de parry por rango",
        "counter_damage_bonus": lambda v: f"+{_pct(v)} % de daño de contraataque por rango",
        "bf_chance_bonus": lambda v: f"+{_pct(v)} % de probabilidad de Black Flash por rango",
        "damage_reduction": lambda v: f"−{_pct(v)} % de daño recibido por rango",
        "death_prevention": lambda v: "Sobrevives a un golpe mortal con 1 HP, una vez por combate",
        "charge_bonus": lambda v: f"+{_pct(v)} % de carga de ultimate en cada acción, por rango",
        "regen_bonus": lambda v: f"+{_fmt(v)} HP de regeneración en los checkpoints por rango",
        "cooldown_reduction": lambda v: f"−{_pct(v)} % de enfriamiento de los poderes por rango",
    }.get(kind)
    return per(value) if per else ""


def _diff(name: str) -> str:
    return DIFFICULTY_ES.get(name, name)


_SUB_EFFECTS = {"heal": "curas {n} HP", "heal_percent": "curas el {n} % de tu vida", "charge_ultimate": "+{n} % de carga de ultimate",
                "damage_boss": "{n} de daño directo al jefe", "boss_damage_percent": "daño al jefe del {n} % de su vida", "stun_enemy": "aturdes al enemigo {n} s",
                "cooldown_reduce": "reduces {n} s el enfriamiento", "damage_boost": "+{n} % de daño", "bf_chance": "+{n} % de probabilidad de Black Flash"}


def describe_object_effect(effect: str) -> str:
    """One effect of a special object, in plain Spanish (`on_hard_evade:heal:15` -> "Al esquivar en difícil: curas 15 HP")."""
    text = str(effect or "").strip()
    simple = {
        "guaranteed_counter": "Contraataque garantizado", "guaranteed_hit": "Golpe garantizado", "black_flash": "Black Flash garantizado",
        "copy_attack": "Copias el ataque del enemigo", "counter_for_enemy": "Contraatacas en lugar del enemigo",
        "remove_timing_requirement": "Sin requisito de tiempo", "charge_ultimate_full": "Ultimate cargada al máximo",
    }
    if text in simple:
        return simple[text]
    m = re.fullmatch(r"damage_reduction(?:\.(\w+))?:([+-]?)(\d+)", text)
    if m:
        where = f" en {_diff(m.group(1))}" if m.group(1) else ""
        if m.group(2):
            return f"{'+' if m.group(2) == '+' else '−'}{m.group(3)} % de reducción de daño{where}"
        return f"Reduces el daño un {m.group(3)} %{where}"
    m = re.fullmatch(r"(heal|heal_percent|charge_ultimate|damage_boss|boss_damage_percent|stun_enemy|cooldown_reduce):(\d+(?:\.\d+)?)", text)
    if m:
        sentence = _SUB_EFFECTS[m.group(1)].format(n=_fmt(float(m.group(2))))
        return sentence[0].upper() + sentence[1:]
    m = re.fullmatch(r"(damage_boost|bf_chance):([+-]?)(\d+)", text)
    if m:
        number = ("−" if m.group(2) == "-" else "+") + m.group(3)
        return f"{number} % de daño" if m.group(1) == "damage_boost" else f"{number} % de probabilidad de Black Flash"
    m = re.fullmatch(r"invoke_qte:(\w+)", text)
    if m:
        return f"Invocas un QTE de dificultad {_diff(m.group(1))}"
    m = re.fullmatch(r"auto_evade:(\w+)", text)
    if m:
        return f"Esquive automático en dificultad {_diff(m.group(1))}"
    m = re.fullmatch(r"(on_evade|on_hard_evade):(\w+):(\d+)", text)
    if m:
        when = "Al esquivar" if m.group(1) == "on_evade" else "Al esquivar en difícil"
        template = _SUB_EFFECTS.get(m.group(2))
        what = template.format(n=m.group(3)) if template else f"{m.group(2).replace('_', ' ')} {m.group(3)}"
        return f"{when}: {what}"
    m = re.fullmatch(r"on_boss_stunned:(\w+)(?::(\d+))?", text)
    if m:
        template = _SUB_EFFECTS.get(m.group(1))
        what = ("Black Flash" if m.group(1) == "black_flash" else template.format(n=m.group(2)) if template and m.group(2)
                else m.group(1).replace("_", " ") + (f" {m.group(2)}" if m.group(2) else ""))
        return f"Con el jefe aturdido: {what}"
    return text.replace("_", " ")
