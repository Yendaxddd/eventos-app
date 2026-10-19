// The arithmetic of the latency test, apart from the page so it can be tested on its own.
import { median } from "./util.js";

// Each tap answers at most one flash, and each flash takes the closest tap that is still free. The first `skip` flashes are practice and do
// not count. Returns the signed errors in ms (positive = the tap came after the flash), one per flash that was answered.
export function matchTaps(flashes, taps, { skip = 0, window = 450 } = {}) {
  const free = taps.map((t, i) => ({ t, i })).filter((x) => Number.isFinite(x.t));
  const errors = [];
  flashes.forEach((flash, k) => {
    if (k < skip) return;
    let best = -1;
    for (let j = 0; j < free.length; j++) {
      const e = free[j].t - flash;
      if (Math.abs(e) < window && (best < 0 || Math.abs(e) < Math.abs(free[best].t - flash))) best = j;
    }
    if (best >= 0) { errors.push(Math.round(free[best].t - flash)); free.splice(best, 1); }
  });
  return errors;
}

// The result of the ping step. `rtts[i]` is undefined (not answered yet), null (lost) or the round trip in ms; anything slower than
// `lostAfter` counts as lost, as the page says.
export function summarizeNet(rtts, lostAfter = Infinity) {
  const all = rtts.map((r) => (typeof r === "number" && Number.isFinite(r) && r <= lostAfter ? r : null));
  const ok = all.filter((r) => r !== null);
  const sorted = [...ok].sort((a, b) => a - b);
  const med = median(ok);
  return {
    samples: all, median: med, min: sorted[0] ?? null, p90: sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.9))] : null,
    jitter: med === null ? null : ok.reduce((s, r) => s + Math.abs(r - med), 0) / ok.length,
    loss: all.length ? (all.length - ok.length) / all.length : 1,
  };
}

// Taps that are all over the place say nothing about the device: the test must be repeated, not saved.
export const UNSTEADY_MS = 150;
export const MIN_TAPS = 4;
