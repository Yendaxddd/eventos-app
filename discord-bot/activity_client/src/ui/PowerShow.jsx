// A power's picture or GIF filling the screen for a moment when somebody uses it (the power's «who sees it»: everybody or only them).
import { signal } from "@preact/signals";
import { prefs } from "../state.js";
import { cdn, cx } from "../util.js";

const shown = signal(null);          // { key, image, name, character, type }
let key = 0;
const SHOW_MS = 2600;

export function onPowerShow(frame) {
  if (prefs.value.vfx === "off") return;
  const mine = ++key;
  shown.value = { ...frame, key: mine };
  setTimeout(() => { if (shown.value && shown.value.key === mine) shown.value = null; }, SHOW_MS);
}

export function PowerShow() {
  const s = shown.value;
  if (!s) return null;
  const soft = prefs.value.vfx === "soft" || prefs.value.motion === "reduced";
  return (
    <div class={cx("power-show", `pt-${s.type || "destructive"}`, soft && "soft")} key={s.key} aria-hidden="true" data-testid="power-show">
      <img src={cdn(s.image)} alt="" />
      <div class="power-show-name"><small>{s.character}</small><strong>{s.name}</strong></div>
    </div>
  );
}
