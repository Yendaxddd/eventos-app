"""Copies of the event's data (players, achievements, objects, skills, the numbers the game masters set...).

One zip per copy: made by hand, automatically when the bot stops, or as a safety net right before a restore. A copy never holds the
bot's token or the Client Secret (they live in settings.json, which is not part of it) and restoring one never trusts the names inside the
zip: a damaged or malicious file can not write outside the data folder.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

log = logging.getLogger("eventos_app")

DIR_NAME = "backups"
PREFIX = "EventosApp-datos-"
MANIFEST = "manifest.json"
AUTOMATIC = "al-detener"                  # the label of the copies the app makes by itself when the bot stops
SAFETY = "antes-de-restaurar"             # the label of the copy made right before a restore
KEEP_AUTOMATIC = 10
MAX_UNPACKED = 2 * 1024 ** 3
MAX_FILES = 100_000
_STAMP = "%Y%m%d-%H%M%S"
_NAME = re.compile(rf"^{re.escape(PREFIX)}(\d{{8}}-\d{{6}})(?:-([a-z0-9-]+))?(?:_(\d+))?\.zip$")
_SKIP = (".tmp", ".perm_check", ".write_test")


class BackupError(Exception):
    """Something the person can be told in plain words (it is shown as is)."""


@dataclass(frozen=True)
class Backup:
    path: Path
    created: float                         # seconds since 1970, from the name (the file's date changes when it is copied around)
    size: int
    label: str                             # "" (by hand), "al-detener" or "antes-de-restaurar"

    @property
    def title(self) -> str:
        when = datetime.datetime.fromtimestamp(self.created).strftime("%d/%m/%Y %H:%M")
        kind = {"": "Manual", AUTOMATIC: "Automática (al detener el bot)", SAFETY: "Antes de restaurar"}.get(self.label, self.label)
        return f"{when} · {kind}"


def backups_dir(home: Path) -> Path:
    return Path(home) / DIR_NAME


def _clean_label(label: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", label.lower()).strip("-")[:30]


def _files_of(data: Path):
    for path in sorted(data.rglob("*")):
        if path.is_file() and not path.name.endswith(_SKIP):
            yield path


def make_backup(home: Path, *, label: str = "", keep: int = KEEP_AUTOMATIC, now: float | None = None) -> Path:
    """A zip of `<home>/data` in `<home>/backups`. Raises BackupError if there is nothing to copy."""
    home = Path(home)
    data = home / "data"
    if not data.is_dir() or not any(_files_of(data)):
        raise BackupError("Todavía no hay datos del evento que guardar.")
    stamp = time.strftime(_STAMP, time.localtime(now if now is not None else time.time()))
    suffix = f"-{_clean_label(label)}" if _clean_label(label) else ""
    folder = backups_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    target, n = folder / f"{PREFIX}{stamp}{suffix}.zip", 1
    while target.exists():
        n += 1
        target = folder / f"{PREFIX}{stamp}{suffix}_{n}.zip"
    partial = target.with_name(target.name + ".part")
    from . import __version__                                    # light: the package root imports nothing else

    count = 0
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in _files_of(data):
                try:
                    archive.write(path, "data/" + path.relative_to(data).as_posix())
                except FileNotFoundError:                                  # the bot replaced or removed it a moment ago
                    continue
                count += 1
            archive.writestr(MANIFEST, json.dumps({"app": "Eventos App", "version": __version__, "files": count,
                                                   "created": datetime.datetime.now().isoformat(timespec="seconds")}, indent=1))
        partial.replace(target)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise BackupError(f"No se pudo crear la copia: {exc}") from exc
    if _clean_label(label) == AUTOMATIC:
        prune(home, keep)
    return target


def _parse(path: Path) -> Backup | None:
    match = _NAME.match(path.name)
    if match is None or not path.is_file():
        return None
    try:
        created = time.mktime(time.strptime(match.group(1), _STAMP))
        size = path.stat().st_size
    except (ValueError, OverflowError, OSError):
        return None
    return Backup(path, created, size, match.group(2) or "")


def list_backups(home: Path) -> list[Backup]:
    """The copies there are, newest first."""
    folder = backups_dir(home)
    if not folder.is_dir():
        return []
    found = [b for b in (_parse(p) for p in folder.glob(f"{PREFIX}*.zip")) if b is not None]
    return sorted(found, key=lambda b: (b.created, b.path.name), reverse=True)


def prune(home: Path, keep: int = KEEP_AUTOMATIC) -> int:
    """Delete the oldest automatic copies beyond `keep` (copies made by hand or before a restore stay until the person deletes them)."""
    automatic = [b for b in list_backups(home) if b.label == AUTOMATIC]
    removed = 0
    for old in automatic[max(1, keep):]:
        try:
            old.path.unlink()
            removed += 1
        except OSError:
            log.warning("could not delete the old copy %s", old.path)
    return removed


def delete_backup(home: Path, archive: Path) -> None:
    archive = Path(archive)
    if archive.parent.resolve() != backups_dir(home).resolve() or _parse(archive) is None:
        raise BackupError("Esa copia no está en la carpeta de copias.")
    try:
        archive.unlink()
    except OSError as exc:
        raise BackupError(f"No se pudo borrar la copia: {exc}") from exc


def _safe_name(name: str) -> PurePosixPath | None:
    """The relative path inside `data/` that a name of the zip means, or None for anything that is not a plain file of the data folder."""
    if "\\" in name or ":" in name or name.startswith("/"):
        return None
    path = PurePosixPath(name)
    parts = path.parts
    if len(parts) < 2 or parts[0] != "data" or any(p in ("", ".", "..") for p in parts):
        return None
    return PurePosixPath(*parts[1:])


def _check(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    entries, total = [], 0
    infos = archive.infolist()
    if len(infos) > MAX_FILES:
        raise BackupError("La copia tiene demasiados archivos: no parece una copia de Eventos App.")
    for info in infos:
        if info.filename == MANIFEST or info.is_dir():
            continue
        relative = _safe_name(info.filename)
        if relative is None:
            raise BackupError(f"La copia tiene un archivo que no debería estar («{info.filename[:60]}»): no se restaura nada.")
        total += info.file_size
        entries.append((info, relative))
    if total > MAX_UNPACKED:
        raise BackupError("La copia ocupa demasiado al descomprimirse.")
    if not entries:
        raise BackupError("La copia está vacía.")
    return entries


def restore_backup(home: Path, archive: Path) -> Path | None:
    """Put the data of a copy back. The bot must be stopped. Before touching anything a copy of what there is now is made, and a failure
    halfway leaves the data as it was. Returns that safety copy (None if there was nothing to protect)."""
    home, archive = Path(home), Path(archive)
    try:
        with zipfile.ZipFile(archive) as zf:
            entries = _check(zf)
            stamp = time.strftime(_STAMP)
            staging = home / f".restore-{stamp}"
            shutil.rmtree(staging, ignore_errors=True)
            try:
                for info, relative in entries:
                    target = staging / "data" / Path(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as source, open(target, "wb") as out:
                        shutil.copyfileobj(source, out)
                safety = None
                data = home / "data"
                if data.is_dir() and any(_files_of(data)):
                    safety = make_backup(home, label=SAFETY)
                _swap(home, staging / "data", stamp)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
    except zipfile.BadZipFile as exc:
        raise BackupError("Ese archivo no es una copia válida (no se puede abrir como zip).") from exc
    except OSError as exc:
        raise BackupError(f"No se pudo restaurar: {exc}") from exc
    return safety


def _swap(home: Path, new_data: Path, stamp: str) -> None:
    data = home / "data"
    old = home / f".data-replaced-{stamp}"
    try:
        if data.exists():
            data.rename(old)
        try:
            new_data.rename(data)
        except OSError:
            if old.exists() and not data.exists():
                old.rename(data)                                                # put the old data back: nothing was lost
            raise
    except PermissionError as exc:
        raise BackupError("Windows no deja cambiar la carpeta de datos: cierra el Explorador y otros programas que la tengan abierta "
                          "y prueba otra vez.") from exc
    shutil.rmtree(old, ignore_errors=True)


def changed_since_last(home: Path) -> bool:
    """True when the data changed after the newest copy (or there is no copy yet): a copy made now would not be a duplicate."""
    summary = data_summary(home)
    if not summary["files"]:
        return False
    listed = list_backups(home)
    if not listed:
        return True
    try:
        return (summary["newest"] or 0) > listed[0].path.stat().st_mtime                 # the copy's own date is exact; its name only has seconds
    except OSError:
        return True


def data_summary(home: Path) -> dict:
    """What the data folder holds, for the Data page: number of files, size and the date of the latest change."""
    data = Path(home) / "data"
    files = size = 0
    newest = 0.0
    if data.is_dir():
        for path in _files_of(data):
            try:
                stat = path.stat()
            except OSError:
                continue
            files += 1
            size += stat.st_size
            newest = max(newest, stat.st_mtime)
    return {"files": files, "bytes": size, "newest": newest or None}
