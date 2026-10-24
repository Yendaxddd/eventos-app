import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { groupedWithPrevious } from "../feed-model.js";
import { ArrowDown, MessagesSquare, Paperclip } from "lucide-preact";
import { messages, prefs } from "../state.js";
import { cdn, cx, timeLabel } from "../util.js";
import { Markdown } from "../md.jsx";
import { openLink } from "../discord.js";
import { Avatar } from "./Avatar.jsx";

const VIDEO = /\.(mp4|webm|mov)(\?|$)/i;

// Images and clips; when the player turned media off they load on a tap.
function Media({ src, poster, video, alt = "", class: className }) {
  const [open, setOpen] = useState(prefs.value.showMedia);
  if (!open) {
    return <button class="btn btn-sm" type="button" onClick={() => setOpen(true)}><Paperclip size={14} /> Mostrar imagen</button>;
  }
  if (video) return <video class={className} src={cdn(src)} poster={poster ? cdn(poster) : undefined} muted loop autoplay playsInline preload="metadata" />;
  return <img class={className} src={cdn(src)} alt={alt} loading="lazy" />;
}

function Embed({ e }) {
  const hasVideo = e.video && VIDEO.test(e.video);
  return (
    <div class="embed" style={e.color ? { "--embed-color": e.color } : undefined}>
      {e.author && <div class="e-author">{e.author}</div>}
      {e.thumb && e.image !== e.thumb && !hasVideo && <Media class="e-thumb" src={e.thumb} />}
      {e.title && (
        <div class="e-title">
          {e.url && /^https?:/.test(e.url) ? <a href={e.url} onClick={(ev) => { ev.preventDefault(); openLink(e.url); }}>{e.title}</a> : e.title}
        </div>
      )}
      {e.description && <div class="e-desc"><Markdown text={e.description} /></div>}
      {(e.fields || []).length > 0 && (
        <div class="e-fields">
          {e.fields.map((f, i) => <div key={i}><b>{f.name}</b><Markdown text={f.value} /></div>)}
        </div>
      )}
      {hasVideo ? <Media class="e-media" video src={e.video} poster={e.thumb} /> : (e.image || e.thumb) && !(e.thumb && e.image !== e.thumb && !e.image) ? <Media class="e-media" src={e.image || e.thumb} /> : null}
      {e.footer && <div class="e-footer">{e.footer}</div>}
    </div>
  );
}

function Reactions({ list }) {
  return (
    <div class="reactions">
      {list.map((r, i) => (
        <span class="reaction" key={i}>
          {r.emoji.id
            ? <img alt={r.emoji.name} src={cdn(`https://cdn.discordapp.com/emojis/${r.emoji.id}.${r.emoji.animated ? "gif" : "png"}?size=32`)} />
            : r.emoji.name}
          <b>{r.count}</b>
        </span>
      ))}
    </div>
  );
}

function Message({ m, grouped }) {
  const p = prefs.value;
  const tag = m.author.webhook ? (m.author.ours ? "" : "WEBHOOK") : (m.author.bot ? "BOT" : "");
  const system = m.author.bot || (m.author.webhook && m.author.ours && false);
  return (
    <div class={cx("msg", !p.showAvatars && "no-avatar", !p.showTimestamps && "hide-time", system && "is-system", grouped && "grouped")} data-id={m.id}>
      {grouped ? <span style={{ width: "var(--av, 32px)", flex: "none" }} /> : <Avatar url={m.author.avatar} name={m.author.name} />}
      <div class="msg-body">
        {m.reply && <div class="msg-reply ellipsis">{m.reply.author ? `${m.reply.author}: ` : ""}{m.reply.text}</div>}
        {!grouped && (
          <div class="msg-head">
            <span class="msg-name" style={m.author.color ? { color: m.author.color } : undefined}>{m.author.name}</span>
            {tag && <span class={cx("tag", m.author.webhook && "hook")}>{tag}</span>}
            <span class="msg-time">{timeLabel(m.ts)}</span>
          </div>
        )}
        {m.text && <div class="msg-text"><Markdown text={m.text} />{m.edited && <span class="msg-edited"> (editado)</span>}</div>}
        {(m.attachments || []).map((a, i) => (
          <div class="attach" key={i}>
            {a.image ? <Media src={a.url} alt={a.name} /> : <a href={a.url} onClick={(ev) => { ev.preventDefault(); openLink(a.url); }}><Paperclip size={14} /> {a.name}</a>}
          </div>
        ))}
        {(m.stickers || []).map((s, i) => <Media key={i} class="sticker" src={s.url} alt={s.name} />)}
        {(m.embeds || []).map((e, i) => <Embed key={i} e={e} />)}
        {(m.reactions || []).length > 0 && <Reactions list={m.reactions} />}
      </div>
    </div>
  );
}

export function Feed() {
  const list = messages.value;
  const box = useRef(null);
  const stick = useRef(true);
  const seen = useRef(null);                                    // the id of the newest message already counted
  const [unread, setUnread] = useState(0);

  const toBottom = () => { const el = box.current; if (el) el.scrollTop = el.scrollHeight; };
  const onScroll = () => {
    const el = box.current;
    if (!el) return;                                            // a scroll that arrives after the chat was closed (another tab)
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (stick.current && unread) setUnread(0);
  };
  useLayoutEffect(() => {
    // counted by the newest id, not by length: once the list is at its limit, a new message pushes an old one out and the length stays
    const last = list.length ? list[list.length - 1].id : null;
    let added = 0;
    if (seen.current !== null && last !== seen.current) {
      const at = list.findIndex((m) => m.id === seen.current);
      added = at < 0 ? list.length : list.length - 1 - at;
    }
    seen.current = last;
    if (stick.current) toBottom();
    else if (added > 0) setUnread((n) => n + added);
  }, [list]);

  return (
    <div class="feed-wrap">
      <div class="feed" ref={box} onScroll={onScroll} onLoadCapture={() => { if (stick.current) toBottom(); }} role="log" aria-live="polite" aria-relevant="additions" aria-label="Canal del evento" data-testid="feed">
        {list.length === 0 && (
          <div class="feed-empty"><MessagesSquare size={32} /><strong>Todavía no hay mensajes</strong><span>Lo que pase en el canal del evento aparecerá aquí.</span></div>
        )}
        {list.map((m, i) => <Message key={m.id} m={m} grouped={groupedWithPrevious(list, i)} />)}
      </div>
      {unread > 0 && (
        <button class="jump-new" type="button" onClick={() => { toBottom(); stick.current = true; setUnread(0); }}>
          <ArrowDown size={15} /> {unread === 1 ? "1 mensaje nuevo" : `${unread} mensajes nuevos`}
        </button>
      )}
    </div>
  );
}
