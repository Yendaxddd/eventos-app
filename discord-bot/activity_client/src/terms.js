// The words of the game, in Spanish, in one place so the whole interface calls things by the same name.
export const CMD = {
  evade: "Esquivar", parry: "Parry", save: "Rescatar", adapt: "Adaptar", attack: "Contraataque",
  power1: "Poder 1", power2: "Poder 2", domain: "Dominio",
  up: "Arriba", down: "Abajo", left: "Izquierda", right: "Derecha",
};

export const DIFFICULTY = { easy: "Fácil", medium: "Media", hard: "Difícil", impossible: "Imposible" };

export const MODE = {
  single: "Individual", group: "Grupal", combo: "Combo", direction: "Dirección", bf_chain: "Cadena Black Flash", fake: "Falso",
};

export const KEYS = {
  evade: "E", parry: "P", save: "S", adapt: "A", attack: "Q", power1: "1", power2: "2", domain: "3",
  up: "↑", down: "↓", left: "←", right: "→",
};

// What the verdict of a press is called on screen.
export const VERDICT = {
  evade_ok: "¡Esquivado!", parry_ok: "¡Parry!", parry_perfect: "¡Parry perfecto!", bf: "¡BLACK FLASH!",
  save_ok: "¡Rescate!", combo_step: "¡Bien!", combo_done: "¡Combo completo!", direction_ok: "¡Correcto!",
  bad: "Fallaste", late: "Tarde", sent: "Enviado…",
};

export const QUALITY = {
  great: "Excelente", good: "Buena", fair: "Regular", poor: "Mala", off: "Sin conexión",
};
