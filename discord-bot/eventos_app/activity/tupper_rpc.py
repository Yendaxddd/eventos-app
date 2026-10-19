"""Importing characters from Tupperbox: `panel.tupper_import`.

A player exports their tuppers in Discord (`tul!export` gives a `tuppers.json`), picks the file in the Activity and chooses which ones to bring.
The page reads the file itself and sends only the names and picture addresses; this registers the names to the player (the same rules as typing
them) and downloads every picture to the host's PC, so a character's picture is there for good (a Discord attachment address expires, and a
picture hosted somewhere else could not be shown inside Discord at all).

Mixed into `ActivityBridge`; it relies on `self.panel`, `self.hub`, `self.characters_of`, `self._characters_payload` and `self._characters_changed`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from .hub import Conn, RpcError
from .media import IMAGES, MediaError, MediaStore
from .panel import MAX_CHARACTERS, _clean_line
from .safe_fetch import FetchError, fetch_bytes

log = logging.getLogger("eventos_app.activity")

MAX_TUPPERS = 40                 # one import
IMPORT_EVERY = 15.0              # seconds between two imports of the same player
PARALLEL_DOWNLOADS = 3


class TupperRpc:
    def _init_tupper(self, files: MediaStore | None, images_file: Path | None) -> None:
        self.files = files
        self.images_file = images_file
        self.char_images: dict[str, str] = {}              # character -> «files/images/<hash>.<ext>»
        self.fetch_allow_private = False                    # only the tests serve pictures from this very machine
        self._imported_at: dict[int, float] = {}
        self._importing: set[int] = set()
        if images_file is not None and images_file.exists():
            try:
                data = json.loads(images_file.read_text(encoding="utf-8"))
                self.char_images = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
            except (OSError, ValueError):
                log.warning("could not read %s", images_file)

    def _save_char_images(self) -> None:
        if self.images_file is None:
            return
        try:
            tmp = self.images_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.char_images, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.images_file)
        except OSError:
            log.warning("could not save %s", self.images_file)

    def char_image(self, name: str) -> str | None:
        """The picture kept on this PC for a character, if there is one (and the file is still there)."""
        path = self.char_images.get(name)
        if not path or self.files is None:
            return None
        parts = path.split("/")
        return path if len(parts) == 3 and self.files.exists(parts[1], parts[2]) else None

    # ---- the request ---------------------------------------------------------------------------------------------
    async def rpc_panel_tupper_import(self, conn: Conn, args: dict):
        if self.files is None:
            raise RpcError("Esta Actividad no puede guardar imágenes en este PC.")
        raw = args.get("tuppers")
        if not isinstance(raw, list) or not raw:
            raise RpcError("No hay personajes que importar.")
        if len(raw) > MAX_TUPPERS:
            raise RpcError(f"Importa hasta {MAX_TUPPERS} personajes cada vez.")
        user = conn.user_id
        now = time.monotonic()
        if user in self._importing:
            raise RpcError("Ya hay una importación en marcha.")
        if now - self._imported_at.get(user, -1e9) < IMPORT_EVERY:
            raise RpcError("Acabas de importar: espera unos segundos.")
        self._importing.add(user)
        try:
            results = await self._import(user, raw)
        finally:
            self._importing.discard(user)
            self._imported_at[user] = time.monotonic()
        names = [r["name"] for r in results if r["status"] in ("new", "mine")]
        log.info("%s importó %d personajes de Tupperbox (%d con imagen)", conn.name, len(names), sum(1 for r in results if r["image"] == "ok"))
        return {"results": results, "characters": await self._characters_changed(conn)}

    async def _import(self, user: int, raw: list) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        todo: list[tuple[dict, str]] = []
        for item in raw:
            entry = item if isinstance(item, dict) else {}
            name = _clean_line(entry.get("name"), 80)
            result = {"name": name or "(sin nombre)", "status": "", "image": "none", "note": ""}
            results.append(result)
            if not name:
                result.update(status="skipped", note="Sin nombre.")
                continue
            if name in seen:
                result.update(status="skipped", note="Repetido en el archivo.")
                continue
            seen.add(name)
            owner = self.app.character_registry.get(name)
            if owner is not None and owner != user:
                result.update(status="taken", note="Ya lo tiene registrado otra persona.")
                continue
            if owner == user:
                result["status"] = "mine"
            else:
                try:
                    self.panel.register_character(user, name)
                    result["status"] = "new"
                except RpcError as exc:
                    result.update(status="skipped", note=str(exc))
                    continue
            avatar = entry.get("avatar")
            if isinstance(avatar, str) and avatar.strip():
                todo.append((result, avatar.strip()))
        gate = asyncio.Semaphore(PARALLEL_DOWNLOADS)

        async def download(result: dict, url: str) -> None:
            async with gate:
                try:
                    data = await fetch_bytes(url, max_bytes=8 * 1024 * 1024, allow_private=self.fetch_allow_private)
                    stored = self.files.save(IMAGES, data)
                except (FetchError, MediaError) as exc:
                    result.update(image="error", note=str(exc))
                    return
                except Exception:  # noqa: BLE001
                    log.exception("could not import a Tupperbox picture")
                    result.update(image="error", note="No se pudo guardar la imagen.")
                    return
                self.char_images[result["name"]] = stored.path
                result["image"] = "ok"

        if todo:
            await asyncio.gather(*(download(r, u) for r, u in todo))
            self._save_char_images()
        return results
