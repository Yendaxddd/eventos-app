// The memory behind a form that follows the server until the person starts typing (see useDraft in hooks.js). Pure, so it is tested
// without a browser. Everything it knows about the typing is updated at the very moment of typing, never at the next render: a copy
// from the server that arrives between a render and its effect must not be able to overwrite what has just been typed.
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export class DraftMemory {
  constructor(server) {
    this.dirty = false;          // the person typed something that is not saved yet
    this.last = server;          // the last copy from the server that has been looked at
    this.now = server;           // what the form holds
  }

  // After a render: what the form shows is the latest known value, unless it is being typed.
  render(shown) {
    if (!this.dirty) this.now = shown;
  }

  // The server's copy may have changed. Returns the value to show now, or undefined to keep what is shown.
  sync(server) {
    if (same(this.last, server)) return undefined;
    this.last = server;
    if (this.dirty) return undefined;
    this.now = server;
    return server;
  }

  edit(patch) {
    this.dirty = true;
    this.now = { ...this.now, ...(typeof patch === "function" ? patch(this.now) : patch) };
    return this.now;
  }

  // After a save of `sent`: the form goes back to following the server, unless something else was typed while the answer was on its
  // way (then it stays theirs). The next sync takes the server's version, which may have tidied what was typed ("150.0" -> 150).
  saved(sent) {
    if (sent !== undefined && !same(this.now, sent)) return false;
    this.dirty = false;
    this.last = undefined;
    return true;
  }

  reset(server) {
    this.dirty = false;
    this.now = server;
    this.last = server;
    return server;
  }
}
