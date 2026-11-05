// Round-trip statistics of the connection. Pure code (no DOM), so it can be tested on its own.
import { median } from "./util.js";

// Of several ping/pong round trips the fastest ones are the most symmetric, so the clock offset (server minus us) is the
// median over the three quickest. The typical delay (median) is what a player really lives with; the minimum is the best case.
export class SyncEstimator {
  constructor(max = 40) { this.max = max; this.samples = []; }

  add(rtt, offset = 0) {
    this.samples.push({ rtt, offset });
    if (this.samples.length > this.max) this.samples.shift();
  }

  get count() { return this.samples.length; }
  get rtts() { return this.samples.map((s) => s.rtt); }
  get min() { return this.count ? Math.min(...this.rtts) : null; }
  get median() { return median(this.rtts); }

  // mean distance from the median: how much the delay moves around
  get jitter() {
    const m = this.median;
    if (m === null) return null;
    return this.rtts.reduce((sum, r) => sum + Math.abs(r - m), 0) / this.count;
  }

  get offset() {
    if (!this.count) return 0;
    const best = [...this.samples].sort((a, b) => a.rtt - b.rtt).slice(0, 3);
    return median(best.map((s) => s.offset));
  }
}

// How good a connection is for reacting to QTEs, from its typical round trip and how many pings were lost.
export function qualityOf(medianRtt, loss = 0) {
  if (medianRtt === null || medianRtt === undefined) return "off";
  if (loss > 0.2 || medianRtt >= 320) return "poor";
  if (loss > 0.05 || medianRtt >= 200) return "fair";
  if (medianRtt >= 90) return "good";
  return "great";
}

// Tap test: where the player's taps landed against the beat (signed errors in ms, positive = late).
// Humans tap a little before a steady beat (~30 ms); anything later than that is the device (screen + touch) being slow.
export const TAP_ANTICIPATION_MS = 30;
export function deviceLag(errors) {
  const clean = errors.filter((e) => Number.isFinite(e));
  if (clean.length < 4) return null;
  // drop the farthest taps (a missed beat is not lag), then take the middle
  const m = median(clean);
  const kept = clean.filter((e) => Math.abs(e - m) <= 140);
  const typical = median(kept.length >= 4 ? kept : clean);
  return Math.max(0, Math.min(150, Math.round(typical + TAP_ANTICIPATION_MS)));
}

// Spread of the taps: how steadily the player taps (informational)
export function tapSpread(errors) {
  const clean = errors.filter((e) => Number.isFinite(e));
  const m = median(clean);
  if (m === null) return null;
  return Math.round(clean.reduce((s, e) => s + Math.abs(e - m), 0) / clean.length);
}
