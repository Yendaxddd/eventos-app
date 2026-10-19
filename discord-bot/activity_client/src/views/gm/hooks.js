// What the game-master screens share: data that keeps itself fresh, buttons that know a change is in flight, and forms that
// follow the server until the person starts typing.
import { useEffect, useRef, useState } from "preact/hooks";
import { act, usePanel } from "../../panel/data.js";
import { DraftMemory } from "./draft.js";

// A request that asks again every few seconds while the page is open and visible: the event moves on its own.
export function useLive(op, args, every = 3000) {
  const q = usePanel(op, args);
  const again = useRef(q.refresh);
  again.current = q.refresh;
  useEffect(() => {
    const id = setInterval(() => { if (!document.hidden) again.current(); }, every);
    return () => clearInterval(id);
  }, [every, op]);
  return q;
}

// A change in flight: `busy` is its name, so the buttons that start changes can disable themselves, and a refusal is shown as a toast.
export function useDo() {
  const [busy, setBusy] = useState(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  const run = async (name, op, args, done) => {
    setBusy(name);
    const out = await act(op, args, done);
    if (alive.current) setBusy(null);
    return out;
  };
  return [busy, run];
}

// A form's own copy of what the server has: it follows the server until the person types, and then stays theirs until it is saved.
export function useDraft(server) {
  const [draft, setDraft] = useState(server);
  const mem = useRef(null);
  if (mem.current === null) mem.current = new DraftMemory(server);
  mem.current.render(draft);
  useEffect(() => {
    const next = mem.current.sync(server);
    if (next !== undefined) setDraft(next);
  });
  return {
    draft,
    edit: (patch) => setDraft(mem.current.edit(patch)),
    saved: (sent) => mem.current.saved(sent),
    reset: () => setDraft(mem.current.reset(server)),
  };
}
