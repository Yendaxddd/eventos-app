// The mini enemies on the field: what the server says about them (`mobs` frames), the hits flying off them (`mob_hit`), and the
// player's own tap on one (the `mob.attack` request, with its cooldown kept here so the button can show it).
import { signal } from "@preact/signals";
import { rpc } from "./net.js";
import { toast } from "./state.js";

export const mobs = signal({ paused: false, list: [], at: 0 });     // `at`: the local time the countdowns were read
export const mobHits = signal([]);                                  // [{ key, id, amount, by }], each kept for a moment
export const hitReady = signal(0);                                  // performance.now() after which this player may hit again

let hitKey = 0;

export function setMobs(frame, arrival = performance.now()) {
  mobs.value = { paused: !!(frame && frame.paused), list: (frame && frame.list) || [], at: arrival };
}

export function onMobHit(frame) {
  const key = ++hitKey;
  mobHits.value = [...mobHits.value.slice(-11), { key, id: frame.id, amount: frame.amount, by: frame.by || null }];
  setTimeout(() => { mobHits.value = mobHits.value.filter((h) => h.key !== key); }, 1100);
}

// seconds until an enemy's next attack, as of `now` (null when it is paused or the server did not say)
export function nextAttackIn(mob, at, now = performance.now()) {
  if (mob.next === null || mob.next === undefined) return null;
  return Math.max(0, mob.next - (now - at) / 1000);
}

export async function hitMob(id) {
  if (performance.now() < hitReady.value) return null;
  hitReady.value = performance.now() + 2000;                        // the server's cooldown; corrected by its answer
  try {
    const out = await rpc("mob.attack", { id });
    hitReady.value = performance.now() + (out.cooldown || 2) * 1000;
    return out;
  } catch (err) {
    const wait = /Espera ([\d.]+) s/.exec(err.message);
    hitReady.value = wait ? performance.now() + Number(wait[1]) * 1000 : 0;
    if (!wait) toast(err.message, "warn", 2200);
    return null;
  }
}
