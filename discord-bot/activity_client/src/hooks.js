import { useEffect, useState } from "preact/hooks";

// performance.now(), refreshed every `interval` ms while `active` (countdowns redraw from it).
export function useNow(interval = 250, active = true) {
  const [now, setNow] = useState(performance.now());
  useEffect(() => {
    if (!active) return undefined;
    setNow(performance.now());
    const id = setInterval(() => setNow(performance.now()), interval);
    return () => clearInterval(id);
  }, [interval, active]);
  return now;
}

function matches(query) {
  return typeof matchMedia === "function" && matchMedia(query).matches;
}

// wide: players + chat + me · mid: chat + me · narrow: chat only (phones); short: a phone held sideways
export function useLayout() {
  const read = () => ({
    mode: matches("(min-width: 1080px)") ? "wide" : matches("(min-width: 720px)") ? "mid" : "narrow",
    short: matches("(max-height: 520px)"),
  });
  const [layout, setLayout] = useState(read);
  useEffect(() => {
    const queries = ["(min-width: 1080px)", "(min-width: 720px)", "(max-height: 520px)"].map((q) => matchMedia(q));
    const update = () => setLayout((old) => {
      const next = read();
      return old.mode === next.mode && old.short === next.short ? old : next;
    });
    queries.forEach((q) => q.addEventListener("change", update));
    return () => queries.forEach((q) => q.removeEventListener("change", update));
  }, []);
  return layout;
}

export function useEscape(handler) {
  useEffect(() => {
    const on = (e) => { if (e.key === "Escape") handler(e); };
    document.addEventListener("keydown", on);
    return () => document.removeEventListener("keydown", on);
  }, [handler]);
}

// run `fn` when the window changes size (rotating a phone, opening the keyboard...)
export function useResize(fn) {
  useEffect(() => {
    window.addEventListener("resize", fn);
    window.visualViewport && window.visualViewport.addEventListener("resize", fn);
    return () => {
      window.removeEventListener("resize", fn);
      window.visualViewport && window.visualViewport.removeEventListener("resize", fn);
    };
  }, [fn]);
}
