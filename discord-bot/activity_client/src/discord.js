// The Discord side of the Activity: the Embedded App SDK, only when running inside Discord.
import { DiscordSDK } from "@discord/embedded-app-sdk";
import { inDiscord } from "./util.js";

export let sdk = null;
import { pip } from "./state.js";

export async function initSdk(clientId) {
  sdk = new DiscordSDK(clientId);
  await sdk.ready();
  return sdk;
}

// After signing in: keep the buttons working when the Activity is shrunk into a floating window, and follow its size.
export async function afterAuth() {
  if (!sdk) return;
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
