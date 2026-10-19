import { render } from "preact";
import { effect } from "@preact/signals";
import "./css/main.css";
import { App } from "./ui/App.jsx";
import { boot } from "./net.js";
import { installKeys } from "./keys.js";
import { prefs, qtes, you, messages, link, comp, me, game, conn, view, tutorial, characters, perms, go } from "./state.js";
import { applyPrefs } from "./prefs.js";
import { setPrefs } from "./settings-actions.js";
import { cine } from "./cine.js";
import { vfxLog } from "./vfx.js";

effect(() => applyPrefs(prefs.value));      // the player's settings are applied to the page whenever they change
installKeys();

// handy for tests and for looking around from the browser console
window.__eventos = {
  get qtes() { return qtes.value; }, get you() { return you.value; }, get messages() { return messages.value; },
  get link() { return link.value; }, get comp() { return comp.value; }, get me() { return me.value; }, get game() { return game.value; },
  get conn() { return conn.value; }, get view() { return view.value; }, get prefs() { return prefs.value; }, get tutorial() { return tutorial.value; },
  get characters() { return characters.value; }, get perms() { return perms.value; }, go, setPrefs, get cine() { return cine.value; }, vfxLog,
};

render(<App />, document.getElementById("root"));
boot();
