import { useEffect, useRef, useState } from "preact/hooks";
import { Check, ChevronDown, SendHorizontal } from "lucide-preact";
import { activeAs, canWrite, characters, charAvatars, lastSaid, sayRefused, toast, you, view } from "../state.js";
import { send } from "../net.js";
import { store } from "../util.js";
import { Avatar } from "./Avatar.jsx";

const MAX = 2000;

function AsPicker() {
  const [open, setOpen] = useState(false);
  const names = characters.value;
  const who = you.value;
  const current = activeAs.value;
  const shownName = current === "me" ? (who ? who.name : "Yo") : current;
  const shownAvatar = current === "me" ? (who && who.avatar) : charAvatars.value[current];

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!e.target.closest || !e.target.closest(".as-picker")) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  if (!names.length) return null;
  const choose = (value) => { activeAs.value = value; store.set("eventos.as", value); setOpen(false); };
  return (
    <div class="as-picker">
      <button type="button" class="as-btn" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open} title="Escribir como…" data-testid="as-picker">
        <Avatar url={shownAvatar} name={shownName} size="sm" />
        <span class="ellipsis">{shownName}</span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div class="as-menu" role="listbox">
          <button type="button" role="option" aria-checked={current === "me"} onClick={() => choose("me")}>
            <Avatar url={who && who.avatar} name={who ? who.name : "Yo"} size="sm" />
            <span class="grow ellipsis">{who ? who.name : "Yo"}</span>
            {current === "me" && <Check size={15} />}
          </button>
          {names.map((n) => (
            <button type="button" role="option" key={n} aria-checked={current === n} onClick={() => choose(n)}>
              <Avatar url={charAvatars.value[n]} name={n} size="sm" />
              <span class="grow ellipsis">{n}</span>
              {current === n && <Check size={15} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Composer() {
  const [text, setText] = useState("");
  useEffect(() => sayRefused.subscribe((n) => { if (n && lastSaid.value) { setText((now) => now || lastSaid.value); lastSaid.value = ""; } }), []);
  const box = useRef(null);
  const enabled = canWrite.value && !!you.value;

  const grow = () => {
    const el = box.current;
    if (!el) return;
    el.style.height = "42px";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };
  useEffect(grow, [text]);

  const submit = (event) => {
    event && event.preventDefault();
    const value = text.trim();
    if (!value || !enabled) return;
    if (!send({ t: "say", text: value.slice(0, MAX), as: activeAs.value })) {        // no connection: what was written stays in the box
      toast("Sin conexión: tu mensaje sigue aquí, envíalo cuando vuelva.", "warn", 3000);
      return;
    }
    lastSaid.value = value;                                      // if the server refuses it, it comes back to the box (net.js)
    setText("");
    if (box.current) box.current.focus();                       // keep the keyboard up on a phone
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) submit(e);
  };

  return (
    <form class="composer" onSubmit={submit} autocomplete="off" data-testid="composer">
      <AsPicker />
      <textarea
        ref={box} class="input" rows={1} maxLength={MAX} value={text} disabled={!enabled}
        placeholder={enabled ? "Escribe en el canal…" : "Solo lectura: usa el chat de Discord"}
        enterKeyHint="send" onInput={(e) => setText(e.currentTarget.value)} onKeyDown={onKey} aria-label="Mensaje"
      />
      <button class="send-btn" type="submit" disabled={!enabled || !text.trim()} aria-label="Enviar"><SendHorizontal size={20} /></button>
    </form>
  );
}

export const composerVisible = () => view.value === "event";
