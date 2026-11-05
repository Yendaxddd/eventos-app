// A small, safe Discord-markdown renderer: everything goes in as text nodes and elements, never as HTML.
import { useState } from "preact/hooks";
import { cdn } from "./util.js";
import { openLink } from "./discord.js";

const TOKEN = new RegExp([
  /(\|\|[^|]+\|\|)/.source,            // 1 spoiler
  /(\*\*\*[^*]+\*\*\*)/.source,        // 2 bold italic
  /(\*\*[^*]+\*\*)/.source,            // 3 bold
  /(__[^_]+__)/.source,                // 4 underline
  /(~~[^~]+~~)/.source,                // 5 strike
  /(`[^`\n]+`)/.source,                // 6 code
  /(\*[^*\n]+\*)/.source,              // 7 italic
  /(\b_[^_\n]+_\b)/.source,            // 8 italic
  /(<a?:\w+:\d+>)/.source,             // 9 custom emoji
  /(<t:\d+(?::[a-zA-Z])?>)/.source,    // 10 timestamp
  /(https?:\/\/[^\s<>()]+)/.source,    // 11 link
].join("|"), "g");

function Spoiler({ children }) {
  const [open, setOpen] = useState(false);
  return <span class={open ? "spoiler open" : "spoiler"} onClick={() => setOpen(!open)}>{children}</span>;
}

function Link({ url }) {
  return <a href={url} onClick={(e) => { e.preventDefault(); openLink(url); }} rel="noopener noreferrer">{url}</a>;
}

function when(token) {
  const [, seconds, style] = token.match(/<t:(\d+)(?::([a-zA-Z]))?>/);
  const date = new Date(Number(seconds) * 1000);
  const text = style === "R" ? date.toLocaleString() : style === "t" ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : style === "d" ? date.toLocaleDateString() : date.toLocaleString();
  return <span class="when">{text}</span>;
}

export function inline(text, key = "") {
  const out = [];
  let last = 0, n = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0], k = `${key}${n++}`;
    if (m[1]) out.push(<Spoiler key={k}>{inline(t.slice(2, -2), k)}</Spoiler>);
    else if (m[2]) out.push(<strong key={k}><em>{inline(t.slice(3, -3), k)}</em></strong>);
    else if (m[3]) out.push(<strong key={k}>{inline(t.slice(2, -2), k)}</strong>);
    else if (m[4]) out.push(<u key={k}>{inline(t.slice(2, -2), k)}</u>);
    else if (m[5]) out.push(<s key={k}>{inline(t.slice(2, -2), k)}</s>);
    else if (m[6]) out.push(<code key={k}>{t.slice(1, -1)}</code>);
    else if (m[7] || m[8]) out.push(<em key={k}>{inline(t.slice(1, -1), k)}</em>);
    else if (m[9]) {
      const id = t.match(/:(\d+)>/)[1], name = t.match(/:(\w+):/)[1];
      out.push(<img key={k} class="emoji" alt={name} src={cdn(`https://cdn.discordapp.com/emojis/${id}.${t.startsWith("<a:") ? "gif" : "png"}?size=48`)} />);
    } else if (m[10]) out.push(<span key={k}>{when(t)}</span>);
    else out.push(<Link key={k} url={t} />);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// Blocks: code fences, headings (# ## ###), sub-text (-#), quotes (>), bullet lists, and plain lines.
export function Markdown({ text }) {
  const lines = String(text || "").split("\n");
  const out = [];
  let i = 0;
  const plainRun = [];
  const flushPlain = () => {
    if (plainRun.length) { out.push(<span key={`p${out.length}`}>{plainRun.splice(0)}</span>); }
  };
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^```(\w+)?\s*$/) || (line.startsWith("```") ? [line] : null);
    if (fence) {
      flushPlain();
      const body = [];
      const firstInline = line.startsWith("```") && line.length > 3 && !fence[1] ? line.slice(3) : null;
      if (firstInline) body.push(firstInline);
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      i++;
      out.push(<pre key={`c${out.length}`}>{body.join("\n").replace(/```$/, "")}</pre>);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushPlain();
      out.push(<div key={`h${out.length}`} class={`md-h${heading[1].length}`}>{inline(heading[2], `h${i}`)}</div>);
      i++; continue;
    }
    if (line.startsWith("-# ")) { flushPlain(); out.push(<div key={`s${out.length}`} class="md-small">{inline(line.slice(3), `s${i}`)}</div>); i++; continue; }
    if (/^>>?>?\s/.test(line)) {
      flushPlain();
      const quote = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      out.push(<blockquote key={`q${out.length}`}>{quote.map((l, n) => <div key={n}>{inline(l, `q${n}`)}</div>)}</blockquote>);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      flushPlain();
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      out.push(<ul key={`u${out.length}`}>{items.map((l, n) => <li key={n}>{inline(l, `u${n}`)}</li>)}</ul>);
      continue;
    }
    plainRun.push(...inline(line, `l${i}`));
    if (i < lines.length - 1 && !/^(#{1,3}\s|-# |>|\s*[-*]\s|```)/.test(lines[i + 1])) plainRun.push("\n");
    i++;
  }
  flushPlain();
  return <>{out}</>;
}
