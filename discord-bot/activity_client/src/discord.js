// The Discord side of the Activity: the Embedded App SDK, only when running inside Discord.
import { DiscordSDK } from "@discord/embedded-app-sdk";
import { inDiscord, params } from "./util.js";

export let sdk = null;
import { pip } from "./state.js";

let subscribed = false;
const READY_WAIT_MS = 12000;
const PORTRAIT = 2;                                    // Discord's OrientationLockState: 1 unlocked, 2 portrait, 3 landscape

export class SdkTimeout extends Error {}

export async function initSdk(clientId) {
  if (!sdk) sdk = new DiscordSDK(clientId);            // one SDK for the whole visit: making another on each reconnection breaks it
  let timer;
  const late = new Promise((_, reject) => { timer = setTimeout(() => reject(new SdkTimeout("Discord no respondió al abrir la Actividad.")), READY_WAIT_MS); });
  try {
    await Promise.race([sdk.ready(), late]);
  } finally {
    clearTimeout(timer);
  }
  lockPortrait();
  return sdk;
}

// On a phone the Activity is played upright: the chat, the boss and the QTE buttons are laid out for it.
function lockPortrait() {
  if (params.get("platform") !== "mobile") return;
  sdk.commands.setOrientationLockState({ lock_state: PORTRAIT, picture_in_picture_lock_state: PORTRAIT }).catch(() => { /* an older Discord client */ });
}

// After signing in: keep the buttons working when the Activity is shrunk into a floating window, and follow its size.
export async function afterAuth() {
  if (!sdk || subscribed) return;
  subscribed = true;
  try { await sdk.commands.setConfig({ use_interactive_pip: true }); } catch { /* an older Discord client */ }
  try {
    await sdk.subscribe("ACTIVITY_LAYOUT_MODE_UPDATE", (update) => {
      pip.value = update.layout_mode === 1;          // 0 focused, 1 picture-in-picture, 2 grid
    });
  } catch { /* the layout is only a courtesy */ }
}

// Links must be opened through Discord (a page inside the Activity cannot open tabs by itself).
export function openLink(url) {
  if (inDiscord && sdk) {
    sdk.commands.openExternalLink({ url }).catch(() => {});
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
