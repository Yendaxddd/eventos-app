// Which messages of the feed share the header of the one before them.
const GROUP_MS = 5 * 60 * 1000;

export function groupedWithPrevious(list, i) {
  const m = list[i], prev = list[i - 1];
  if (!prev || m.reply || prev.author.name !== m.author.name) return false;
  // a webhook is one name that can come from several webhooks (one per bot lane): it is the same speaker when the name and picture match
  if (m.author.webhook || prev.author.webhook) { if (!(m.author.webhook && prev.author.webhook && m.author.avatar === prev.author.avatar)) return false; }
  else if (prev.author.id !== m.author.id) return false;
  return m.ts - prev.ts < GROUP_MS && m.ts >= prev.ts;
}
