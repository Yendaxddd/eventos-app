"""The files the Activity keeps on the host's PC: pictures (the avatars of imported Tupperbox characters, backgrounds) and audio (music, sound
effects, voices).

A file is named by what is in it (a hash), so the same file is stored once and its address never changes; it is checked by its first
bytes, never by its name; and the Activity's own server hands it out at `/files/<kind>/<name>`. Being served from the host it needs no URL
Mappings in the Developer Portal and, unlike a Discord attachment, its address never expires.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("eventos_app.activity")

IMAGES, AUDIO = "images", "audio"
KINDS = (IMAGES, AUDIO)
LIMITS = {IMAGES: 8 * 1024 * 1024, AUDIO: 25 * 1024 * 1024}          # the biggest single file of each kind
TOTAL_LIMITS = {IMAGES: 400 * 1024 * 1024, AUDIO: 1024 * 1024 * 1024}   # everything of each kind
NAME = re.compile(r"^[0-9a-f]{24}\.(png|jpg|gif|webp|mp3|ogg|wav|m4a|webm|flac|aac)$")

_IMAGE_SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "image/png", ".png"), (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
                     (b"GIF87a", "image/gif", ".gif"), (b"GIF89a", "image/gif", ".gif"))
CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
                 ".wav": "audio/wav", ".m4a": "audio/mp4", ".webm": "audio/webm", ".flac": "audio/flac", ".aac": "audio/aac"}


class MediaError(Exception):
    """A reason that can be told to the person in plain words."""


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """(content type, extension) of a PNG, JPEG, GIF or WebP by its first bytes, whatever it is called; None for anything else."""
    for magic, kind, ext in _IMAGE_SIGNATURES:
        if data.startswith(magic):
            return kind, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def sniff_audio(data: bytes) -> tuple[str, str] | None:
    """(content type, extension) of an MP3, OGG, WAV, M4A, WebM, FLAC or AAC file by its first bytes; None for anything else."""
    head = data[:16]
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:         # ADTS: the frame header of raw AAC (its "layer" bits are 00)
        return "audio/aac", ".aac"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and (head[1] >> 3) & 3 != 1 and (head[1] >> 1) & 3 != 0):
        return "audio/mpeg", ".mp3"                                            # an ID3 tag, or an MPEG audio frame header
    if head.startswith(b"OggS"):
        return "audio/ogg", ".ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav", ".wav"
    if head[4:8] == b"ftyp":
        return "audio/mp4", ".m4a"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm", ".webm"
    if head.startswith(b"fLaC"):
        return "audio/flac", ".flac"
    return None


@dataclass(frozen=True)
class StoredFile:
    kind: str
    name: str            # «<hash>.<ext>»
    content_type: str
    size: int

    @property
    def path(self) -> str:
        """Where a client asks for it, relative to the Activity's address."""
        return f"files/{self.kind}/{self.name}"


class MediaStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    def _dir(self, kind: str) -> Path:
        if kind not in KINDS:
            raise MediaError("Tipo de archivo desconocido.")
        return self.root / kind

    @staticmethod
    def name_for(kind: str, data: bytes) -> str:
        """The name `save` would give these bytes ("" when they are not a file of that kind)."""
        sniffed = sniff_image(data) if kind == IMAGES else sniff_audio(data)
        return hashlib.sha256(data).hexdigest()[:24] + sniffed[1] if sniffed else ""

    def save(self, kind: str, data: bytes) -> StoredFile:
        """Keep a file. Raises MediaError (with the reason, in Spanish) for an empty, too big, wrong-kind or too-many files."""
        if not data:
            raise MediaError("El archivo está vacío.")
        if len(data) > LIMITS[kind]:
            raise MediaError(f"El archivo pesa demasiado: el máximo es {LIMITS[kind] // (1024 * 1024)} MB.")
        sniffed = sniff_image(data) if kind == IMAGES else sniff_audio(data)
        if sniffed is None:
            raise MediaError("Solo se aceptan imágenes PNG, JPG, GIF o WebP." if kind == IMAGES
                             else "Solo se aceptan audios MP3, OGG, WAV, M4A, WebM, FLAC o AAC.")
        content_type, ext = sniffed
        name = hashlib.sha256(data).hexdigest()[:24] + ext
        folder = self._dir(kind)
        target = folder / name
        with self._lock:
            if target.is_file():
                return StoredFile(kind, name, content_type, target.stat().st_size)
            if self.usage(kind)[1] + len(data) > TOTAL_LIMITS[kind]:
                raise MediaError("La biblioteca está llena: borra archivos que ya no uses.")
            try:
                folder.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(name + ".part")
                partial.write_bytes(data)
                os.replace(partial, target)
            except OSError as exc:
                raise MediaError(f"No se pudo guardar el archivo: {exc}") from exc
        return StoredFile(kind, name, content_type, len(data))

    def path_of(self, kind: str, name: str) -> Path | None:
        """The file on disk, or None for a name that is not exactly one of ours (nothing outside the folder can be asked for)."""
        if kind not in KINDS or not NAME.match(str(name or "")):
            return None
        path = self._dir(kind) / name
        return path if path.is_file() else None

    def exists(self, kind: str, name: str) -> bool:
        return self.path_of(kind, name) is not None

    def delete(self, kind: str, name: str) -> bool:
        path = self.path_of(kind, name)
        if path is None:
            return False
        try:
            path.unlink()
        except OSError:
            return False
        return True

    def usage(self, kind: str) -> tuple[int, int]:
        """(files, bytes) of a kind."""
        folder = self._dir(kind)
        if not folder.is_dir():
            return 0, 0
        sizes = [f.stat().st_size for f in folder.iterdir() if f.is_file() and not f.name.endswith(".part")]
        return len(sizes), sum(sizes)


def split_path(path: str) -> tuple[str, str] | None:
    """«files/images/abc.png» -> ("images", "abc.png"); None for anything else."""
    match = re.fullmatch(r"files/(images|audio)/([0-9a-f]{24}\.[a-z0-9]{2,4})", str(path or ""))
    return (match.group(1), match.group(2)) if match else None
