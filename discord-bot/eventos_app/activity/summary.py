"""Event summaries: what happened between two moments, written by an AI (any OpenAI-compatible API: OpenAI, OpenRouter, Groq,
LM Studio, Ollama's /v1...), so whoever missed the session can catch up — with the cinematics that played in that stretch linked,
so they can watch them again.

- `AiConfig` keeps the endpoint, the key (never sent to any screen; only whether there is one) and the model.
- `CinemaLog` remembers when each cinematic played (the director calls `played`).
- `SummaryBook` keeps the summaries: drafts the game masters edit, published ones everybody reads in «Resúmenes».

Ops (box «Resúmenes con IA»): `gm.summary`, `gm.ai_get`, `gm.ai_set`, `gm.ai_test`, `gm.summary_make`, `gm.summary_save`,
`gm.summary_delete`, `gm.summary_post`. Everybody: `summary.list`, `summary.cinema` (a cinematic linked to a published summary)."""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

import aiohttp

from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")

MAX_SUMMARIES = 60
CHUNK_CHARS = 24_000            # one request's worth of chat; longer stretches are summarised in parts and then joined
MAX_MESSAGES = 4000
DEFAULT_PROMPT = (
    "Eres el cronista de un evento de rol por Discord (con combates, jefes, QTE y escenas). Escribe en español un resumen para quien "
    "se lo perdió: qué pasó, en orden, quién hizo qué de importante, las decisiones tomadas, cómo acabaron los combates y en qué punto "
    "queda la historia. Usa los nombres de los personajes. Sé vivo pero claro; no inventes nada que no esté en el registro. "
    "Usa títulos cortos con ## y viñetas cuando ayuden. Cuando una cinemática se reprodujo, menciónala por su nombre en el momento en que ocurrió."
)


def _t(raw: Any, limit: int) -> str:
    return str(raw if raw is not None else "").strip()[:limit]


def clean_base_url(raw: Any) -> str:
    url = _t(raw, 300).rstrip("/")
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise RpcError("La dirección de la API debe empezar por http:// o https://")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


class AiConfig:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.base_url = "https://api.openai.com/v1"
        self.api_key = ""
        self.model = "gpt-4o-mini"
        self.temperature = 0.5
        self.prompt = ""
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.base_url = raw.get("base_url") or self.base_url
                self.api_key = raw.get("api_key") or ""
                self.model = raw.get("model") or self.model
                self.temperature = float(raw.get("temperature", self.temperature))
                self.prompt = raw.get("prompt") or ""
            except (OSError, ValueError, TypeError):
                log.warning("could not read %s", path)

    def public(self) -> dict:
        key = self.api_key
        return {"base_url": self.base_url, "model": self.model, "temperature": self.temperature, "prompt": self.prompt,
                "default_prompt": DEFAULT_PROMPT, "has_key": bool(key), "key_hint": f"…{key[-4:]}" if len(key) >= 8 else ("puesta" if key else "")}

    def update(self, args: dict) -> None:
        if "base_url" in args:
            self.base_url = clean_base_url(args.get("base_url")) or "https://api.openai.com/v1"
        if "model" in args:
            self.model = _t(args.get("model"), 120) or self.model
        if "temperature" in args:
            try:
                self.temperature = max(0.0, min(1.5, float(args.get("temperature"))))
            except (TypeError, ValueError):
                pass
        if "prompt" in args:
            self.prompt = _t(args.get("prompt"), 4000)
        if args.get("clear_key"):
            self.api_key = ""
        elif _t(args.get("api_key"), 400):
            self.api_key = _t(args.get("api_key"), 400)
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"base_url": self.base_url, "api_key": self.api_key, "model": self.model,
                                           "temperature": self.temperature, "prompt": self.prompt}), encoding="utf-8")
                tmp.replace(self.path)
            except OSError:
                log.warning("could not save %s", self.path)


async def chat(cfg: AiConfig, messages: list[dict], *, timeout: float = 120.0, session_factory: Callable[[], Any] | None = None) -> str:
    """One chat completion. Raises RpcError with a message fit for the game master."""
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    body = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature}
    make = session_factory or (lambda: aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)))
    try:
        async with make() as session:
            async with session.post(cfg.base_url.rstrip("/") + "/chat/completions", json=body, headers=headers) as resp:
                text = await resp.text()
                if resp.status in (401, 403):
                    raise RpcError("La API rechazó la clave (401/403). Revisa la clave y el modelo.")
                if resp.status == 404:
                    raise RpcError("La API no encontró eso (404): revisa la dirección (suele acabar en /v1) y el nombre del modelo.")
                if resp.status == 429:
                    raise RpcError("La API dice que hay demasiadas peticiones o no queda saldo (429). Prueba en un rato.")
                if resp.status >= 400:
                    raise RpcError(f"La API respondió con un error {resp.status}: {text[:200]}")
                data = json.loads(text)
    except RpcError:
        raise
    except (aiohttp.ClientError, OSError) as exc:
        raise RpcError(f"No se pudo conectar con la API ({type(exc).__name__}). ¿Está bien la dirección?") from exc
    except TimeoutError as exc:
        raise RpcError("La API tardó demasiado en responder.") from exc
    except ValueError as exc:
        raise RpcError("La API respondió algo que no es JSON. ¿Es compatible con OpenAI?") from exc
    try:
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RpcError("La respuesta de la API no trae texto (choices[0].message.content).") from exc


class CinemaLog:
    """When each cinematic played (for linking it to the summaries of that stretch)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.items: list[dict] = []
        if path is not None and path.exists():
            try:
                self.items = [x for x in json.loads(path.read_text(encoding="utf-8")) if isinstance(x, dict)]
            except (OSError, ValueError):
                log.warning("could not read %s", path)

    def played(self, cinema: dict, at_ms: float | None = None) -> None:
        self.items.append({"at": int(at_ms if at_ms is not None else time.time() * 1000), "id": cinema.get("id"), "name": _t(cinema.get("name"), 80)})
        del self.items[:-500]
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
            except OSError:
                log.warning("could not save %s", self.path)

    def between(self, a: int, b: int) -> list[dict]:
        return [x for x in self.items if a <= x["at"] <= b]


def cinema_script(cinema: dict) -> str:
    """The words of a cinematic (titles, dialogue, channel messages), to give the AI what it showed."""
    lines = []
    for s in cinema.get("steps") or []:
        if s.get("type") == "title":
            lines.append(f"[Título] {s.get('text', '')}" + (f" — {s['subtitle']}" if s.get("subtitle") else ""))
        elif s.get("type") == "text":
            lines.append(f"{s.get('speaker') or 'Narrador'}: {s.get('text', '')}")
        elif s.get("type") == "post":
            lines.append(f"[Mensaje] {s.get('text', '')}")
    return "\n".join(lines)[:3000]


def transcript(frames: list[dict]) -> str:
    """Chat frames (the Activity's own message format) as plain lines: «[20:14] Kuro: text»."""
    out = []
    for f in frames:
        when = datetime.fromtimestamp(f.get("ts", 0) / 1000, tz=timezone.utc).strftime("%d/%m %H:%M")
        who = (f.get("author") or {}).get("name") or "?"
        parts = [f.get("text") or ""]
        for e in f.get("embeds") or []:
            parts.append(" ".join(x for x in (e.get("title"), e.get("description")) if x))
        text = " ".join(p.strip() for p in parts if p and p.strip())
        if text:
            out.append(f"[{when}] {who}: {text}")
    return "\n".join(out)


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    lines, out, cur = text.split("\n"), [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > size and cur:
            out.append(cur)
            cur = ""
        cur += line[:size] + "\n"
    if cur.strip():
        out.append(cur)
    return out


class SummaryBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.items: list[dict] = []
        if path is not None and path.exists():
            try:
                self.items = [x for x in json.loads(path.read_text(encoding="utf-8")) if isinstance(x, dict) and x.get("id")]
            except (OSError, ValueError):
                log.warning("could not read %s", path)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    def get(self, sid: Any) -> dict:
        for s in self.items:
            if s["id"] == sid:
                return s
        raise RpcError("Ese resumen ya no existe.")

    def add(self, entry: dict) -> dict:
        self.items.insert(0, entry)
        del self.items[MAX_SUMMARIES:]
        self.save()
        return entry

    def edit(self, sid: Any, args: dict) -> dict:
        s = self.get(sid)
        if "title" in args:
            s["title"] = _t(args.get("title"), 100) or s["title"]
        if "text" in args:
            s["text"] = _t(args.get("text"), 20_000)
        if "cinemas" in args and isinstance(args["cinemas"], list):
            keep = {str(c) for c in args["cinemas"]}
            s["cinemas"] = [c for c in s["cinemas"] if str(c["id"]) in keep]
        s["updated"] = int(time.time() * 1000)
        self.save()
        return s

    def delete(self, sid: Any) -> None:
        self.get(sid)
        self.items = [s for s in self.items if s["id"] != sid]
        self.save()

    def published(self) -> list[dict]:
        return [s for s in self.items if s.get("published")]


class SummaryRpc:
    """Mixed into ActivityBridge; relies on `self.ai` (AiConfig), `self.cine_log` (CinemaLog), `self.summaries` (SummaryBook),
    `self.cinema` (the director, with `.book`), `self.hub`, `self.channel()`, `self._frame`, `self._gm`, `self.gm.log`."""

    ai_chat = staticmethod(chat)          # tests swap this

    async def _frames_between(self, a: int, b: int) -> list[dict]:
        channel = self.channel()
        frames: list[dict] = []
        if channel is not None and hasattr(channel, "history"):
            try:
                after = datetime.fromtimestamp(a / 1000, tz=timezone.utc)
                before = datetime.fromtimestamp(b / 1000, tz=timezone.utc)
                from .panel_rpc import is_storage_message
                async for m in channel.history(limit=MAX_MESSAGES, after=after, before=before, oldest_first=True):
                    if not is_storage_message(m):
                        frames.append(self._frame(m))
            except Exception:  # noqa: BLE001 - fall back to what the Activity remembers
                log.exception("could not read the channel's history for a summary")
                frames = []
        if not frames:
            frames = [f for f in list(getattr(self.hub, "backlog", []) or []) if a <= f.get("ts", 0) <= b]
        return frames

    async def _summary_state(self) -> dict:
        return {"ai": self.ai.public(), "summaries": self.summaries.items, "cinemaLog": self.cine_log.items[-60:][::-1]}

    async def rpc_gm_summary(self, conn: Conn, args: dict):
        await self._gm(conn)
        return await self._summary_state()

    async def rpc_gm_ai_get(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.ai.public()

    async def rpc_gm_ai_set(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        self.ai.update(args)
        self.gm.log.add(actor, f"Cambió la API de IA de los resúmenes ({self.ai.model})")
        return await self._summary_state()

    async def rpc_gm_ai_test(self, conn: Conn, args: dict):
        await self._gm(conn)
        started = time.monotonic()
        reply = await self.ai_chat(self.ai, [{"role": "user", "content": "Responde solo con la palabra: listo"}], timeout=30)
        return {"ok": True, "reply": reply[:80], "ms": int((time.monotonic() - started) * 1000)}

    async def rpc_gm_summary_make(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        try:
            a, b = int(args.get("from")), int(args.get("to"))
        except (TypeError, ValueError) as exc:
            raise RpcError("Elige desde cuándo y hasta cuándo.") from exc
        if b <= a:
            raise RpcError("El final tiene que ir después del principio.")
        frames = await self._frames_between(a, b)
        played = self.cine_log.between(a, b)
        if not frames and not played:
            raise RpcError("No hay mensajes en ese tramo.")
        style = _t(args.get("style"), 600)
        system = (self.ai.prompt or DEFAULT_PROMPT) + (f"\nIndicaciones del GM para este resumen: {style}" if style else "")
        cine_lines = []
        for p in played:
            when = datetime.fromtimestamp(p["at"] / 1000, tz=timezone.utc).strftime("%d/%m %H:%M")
            cinema = self.cinema.book.get(p["id"]) if p.get("id") else None
            script = cinema_script(cinema) if cinema else ""
            cine_lines.append(f"[{when}] CINEMÁTICA «{p['name']}»" + (f":\n{script}" if script else ""))
        text = transcript(frames)
        parts = chunks(text) or [""]
        notes = []
        if len(parts) > 1:                       # long stretch: summarise each part, then write the summary from the notes
            for i, part in enumerate(parts, 1):
                notes.append(await self.ai_chat(self.ai, [
                    {"role": "system", "content": "Resume en viñetas, en español, todo lo importante de este trozo del registro de un evento de rol. Conserva nombres y orden."},
                    {"role": "user", "content": f"Parte {i} de {len(parts)}:\n{part}"}]))
            body = "Notas de cada parte del registro:\n\n" + "\n\n".join(notes)
        else:
            body = f"Registro del chat (hora UTC):\n{parts[0]}"
        if cine_lines:
            body += "\n\nCinemáticas reproducidas en este tramo (hora UTC):\n" + "\n\n".join(cine_lines)
        result = await self.ai_chat(self.ai, [{"role": "system", "content": system}, {"role": "user", "content": body}])
        if not result:
            raise RpcError("La IA no devolvió texto.")
        title = _t(args.get("title"), 100) or f"Resumen del {datetime.fromtimestamp(a / 1000).strftime('%d/%m %H:%M')}"
        seen, cinemas = set(), []
        for p in played:
            if p.get("id") and p["id"] not in seen:
                seen.add(p["id"])
                cinemas.append({"id": p["id"], "name": p["name"], "at": p["at"]})
        entry = self.summaries.add({"id": uuid.uuid4().hex[:10], "title": title, "from": a, "to": b, "text": result, "cinemas": cinemas,
                                    "messages": len(frames), "published": False, "by": conn.name, "model": self.ai.model,
                                    "created": int(time.time() * 1000), "updated": int(time.time() * 1000)})
        self.gm.log.add(actor, f"Generó el resumen «{title}» ({len(frames)} mensajes, {len(cinemas)} cinemáticas)")
        return {**await self._summary_state(), "made": entry["id"]}

    async def rpc_gm_summary_save(self, conn: Conn, args: dict):
        await self._gm(conn)
        s = self.summaries.edit(args.get("id"), args)
        if s.get("published"):
            await self.hub.broadcast({"t": "summaries"})
        return await self._summary_state()

    async def rpc_gm_summary_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        s = self.summaries.get(args.get("id"))
        self.summaries.delete(s["id"])
        if s.get("published"):
            await self.hub.broadcast({"t": "summaries"})
        self.gm.log.add(actor, f"Borró el resumen «{s['title']}»")
        return await self._summary_state()

    async def rpc_gm_summary_post(self, conn: Conn, args: dict):
        """Publish (or take back) a summary in the Activity's «Resúmenes»; `channel: true` also writes it in the event channel."""
        actor = await self._gm(conn)
        s = self.summaries.get(args.get("id"))
        s["published"] = bool(args.get("on", True))
        self.summaries.save()
        await self.hub.broadcast({"t": "summaries", "new": s["id"] if s["published"] else None, "title": s["title"]})
        if s["published"] and args.get("channel"):
            await self._post_summary_in_channel(s)
        self.gm.log.add(actor, f"{'Publicó' if s['published'] else 'Retiró'} el resumen «{s['title']}»" + (" (y en el canal)" if args.get("channel") else ""))
        return await self._summary_state()

    async def _post_summary_in_channel(self, s: dict) -> None:
        channel = self.channel()
        if channel is None:
            raise RpcError("No encuentro el canal del evento.")
        text = f"## 📜 {s['title']}\n{s['text']}"
        if s.get("cinemas"):
            text += "\n\n🎬 Cinemáticas: " + ", ".join(f"«{c['name']}»" for c in s["cinemas"]) + " (puedes verlas de nuevo en la Actividad, en Resúmenes)"
        try:
            while text:                                           # Discord's limit is 2000 characters per message
                cut = text[:1900]
                if len(text) > 1900 and "\n" in cut:
                    cut = cut[: cut.rfind("\n")]
                await channel.send(cut)
                text = text[len(cut):].lstrip("\n")
        except Exception as exc:  # noqa: BLE001
            raise RpcError("No pude escribir en el canal (¿permisos del bot?).") from exc

    async def rpc_summary_list(self, conn: Conn, args: dict):
        return {"summaries": [{k: s[k] for k in ("id", "title", "from", "to", "text", "cinemas", "updated")} for s in self.summaries.published()]}

    async def rpc_summary_cinema(self, conn: Conn, args: dict):
        """A cinematic that played in a published summary's stretch, to watch it again alone (never one that has not been shown)."""
        cid = str(args.get("id") or "")
        if not any(str(c["id"]) == cid for s in self.summaries.published() for c in s.get("cinemas") or []):
            raise RpcError("Esa cinemática no está en ningún resumen publicado.")
        cinema = self.cinema.book.get(cid)
        if cinema is None:
            raise RpcError("Esa cinemática ya no existe.")
        return {"cinema": cinema}
