// Reading and changing the player's dashboards over the socket (see net.js `rpc` and the server's panel_rpc.py).
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { rpc } from "../net.js";
import { toast } from "../state.js";
import { cache } from "./cache.js";

// A page's data: what we already know shows immediately, and a fresh copy replaces it as soon as it arrives.
export function usePanel(op, args) {
  const key = op + (args ? JSON.stringify(args) : "");
  const known = cache.get(key);
  const [state, setState] = useState({ data: known === undefined ? null : known, error: null, loading: known === undefined });
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const load = useCallback(async (spinner) => {
    if (spinner) setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await rpc(op, args || {});
      cache.set(key, data);
      if (alive.current) setState({ data, error: null, loading: false });
    } catch (error) {
      if (alive.current) setState((s) => ({ ...s, error: error.message, loading: false }));
    }
  }, [key]);

  useEffect(() => {
    const again = cache.get(key);
    setState({ data: again === undefined ? null : again, error: null, loading: again === undefined });
    load(false);
  }, [key]);

  const replace = useCallback((data) => {
    cache.set(key, data);
    setState({ data, error: null, loading: false });
  }, [key]);

  return { ...state, reload: () => load(true), refresh: () => load(false), replace };
}

// A change: the server's answer, or null after telling the player why it was refused.
export async function act(op, args, done) {
  try {
    const out = await rpc(op, args || {});
    if (done) toast(done, "ok");
    return out;
  } catch (error) {
    toast(error.message, "bad", 4500);
    return null;
  }
}
