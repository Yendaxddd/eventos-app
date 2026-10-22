// Floating numbers: every change of HP, whatever caused it (a QTE, a power, poison, a checkpoint, a game master), worked out by
// comparing one look at the game with the next, so the numbers always match the bars.
import { signal } from "@preact/signals";

export const pops = signal([]);          // [{ key, target: "boss" | player id, amount (negative: damage) }]
let key = 0;

// The changes between two states of the game: [{ target, amount }]. Pure (tested without a browser).
export function hpChanges(before, after) {
  if (!before || !after) return [];
  const out = [];
  if (before.boss && after.boss && before.boss.name === after.boss.name && after.boss.hp !== before.boss.hp) {
    out.push({ target: "boss", amount: Math.round(after.boss.hp - before.boss.hp) });
  }
  const old = new Map((before.players || []).map((p) => [p.id, p.hp]));
  for (const p of after.players || []) {
    if (old.has(p.id) && old.get(p.id) !== p.hp) out.push({ target: p.id, amount: Math.round(p.hp - old.get(p.id)) });
  }
  return out.filter((c) => c.amount !== 0);
}

export function addPops(changes) {
  if (!changes.length) return;
  const fresh = changes.map((c) => ({ ...c, key: ++key }));
  pops.value = [...pops.value.slice(-20), ...fresh];
  setTimeout(() => { const gone = new Set(fresh.map((f) => f.key)); pops.value = pops.value.filter((p) => !gone.has(p.key)); }, 1400);
}

// the numbers floating over one thing (the boss, a player)
export const popsFor = (target) => pops.value.filter((p) => p.target === target);
