// Saves what is being edited by itself, a moment after the person stops changing it. Pure (no DOM): the clock and the saving are handed in.
//
//   status: "saved" (what is on screen is what the server has) | "pending" (a change waits for its moment) | "saving" | "error" (the last try failed;
//   it tries again at the next change, or with `flush`) | "invalid" (the change cannot be saved yet: `check` said why).
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export class Autosaver {
  // save(value) -> Promise (rejects or returns false when it did not work); check(value) -> "" or the reason it cannot be saved yet.
  constructor(save, { delay = 700, check = () => "", onStatus = () => {}, setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (id) => clearTimeout(id) } = {}) {
    Object.assign(this, { save, delay, check, onStatus, setTimer, clearTimer });
    this.saved = undefined;       // the last value the server is known to have
    this.latest = undefined;      // what is on screen
    this.timer = 0;
    this.busy = false;
    this.status = "saved";
    this.reason = "";
  }

  _set(status, reason = "") {
    if (status !== this.status || reason !== this.reason) { this.status = status; this.reason = reason; this.onStatus(status, reason); }
  }

  // What the server has (a new thing was opened, or the server's copy came back after a save): the baseline, with nothing pending.
  baseline(value) {
    this.clearTimer(this.timer); this.timer = 0;
    this.saved = value; this.latest = value;
    this._set("saved");
  }

  // The person changed something.
  update(value) {
    this.latest = value;
    if (this.saved === undefined) { this.saved = value; return; }
    if (same(value, this.saved)) { this.clearTimer(this.timer); this.timer = 0; if (!this.busy) this._set("saved"); return; }
    const problem = this.check(value);
    this.clearTimer(this.timer); this.timer = 0;
    if (problem) { this._set("invalid", problem); return; }
    this._set(this.busy ? "saving" : "pending");
    this.timer = this.setTimer(() => { this.timer = 0; this.flush(); }, this.delay);
  }

  // Save now (before leaving, or after a failure).
  async flush() {
    this.clearTimer(this.timer); this.timer = 0;
    if (this.busy || this.saved === undefined || same(this.latest, this.saved)) return;
    if (this.check(this.latest)) return;
    const sending = this.latest;
    this.busy = true;
    this._set("saving");
    let ok = false;
    try { ok = (await this.save(sending)) !== false; } catch { ok = false; }
    this.busy = false;
    if (ok) this.saved = sending;
    if (!same(this.latest, this.saved)) {            // it changed while it was being saved
      if (ok) { const problem = this.check(this.latest); if (problem) this._set("invalid", problem); else { this._set("pending"); this.timer = this.setTimer(() => { this.timer = 0; this.flush(); }, this.delay); } }
      else this._set("error");
    } else this._set(ok ? "saved" : "error");
  }

  dispose() { this.clearTimer(this.timer); this.timer = 0; }
}
