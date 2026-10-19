"""The host's library of pictures and audio, the safe download of a picture from an address somebody typed, and importing characters from
Tupperbox (their names registered, their pictures kept on this PC)."""
import asyncio
import struct
import sys
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventos_app.activity import media  # noqa: E402
from eventos_app.activity.safe_fetch import FetchError, check_url, fetch_bytes, is_public  # noqa: E402
from test_activity_panel import PNG, PanelRig  # noqa: E402
from test_activity_play import run  # noqa: E402

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 64
OGG = b"OggS\x00\x02" + b"\x00" * 64


# ---- the library --------------------------------------------------------------------------------------------------
def test_files_are_named_by_content_checked_by_their_bytes_and_found_only_by_their_exact_name(tmp_path):
    store = media.MediaStore(tmp_path)
    first = store.save(media.IMAGES, PNG)
    again = store.save(media.IMAGES, PNG)
    assert first == again and first.name.endswith(".png") and len(first.name) == 28 and first.path == f"files/images/{first.name}"
    assert store.usage(media.IMAGES) == (1, len(PNG))
    audio = store.save(media.AUDIO, MP3)
    assert audio.content_type == "audio/mpeg" and store.path_of(media.AUDIO, audio.name).read_bytes() == MP3
    for kind, data in ((media.IMAGES, b"<svg onload=alert(1)>"), (media.IMAGES, MP3), (media.AUDIO, PNG), (media.AUDIO, b"")):
        with pytest.raises(media.MediaError):
            store.save(kind, data)
    for name in ("../../etc/passwd", "abc.png", first.name.upper(), first.name + "/x", "..", ""):
        assert store.path_of(media.IMAGES, name) is None, name
    assert store.path_of("secrets", first.name) is None and store.path_of(media.AUDIO, first.name) is None     # a picture is not an audio file
    assert media.split_path(first.path) == (media.IMAGES, first.name) and media.split_path("files/images/../x.png") is None
    assert store.delete(media.IMAGES, first.name) and not store.delete(media.IMAGES, first.name) and store.usage(media.IMAGES) == (0, 0)


def test_the_limits_of_a_file_and_of_the_whole_library_are_kept(tmp_path, monkeypatch):
    store = media.MediaStore(tmp_path)
    monkeypatch.setitem(media.LIMITS, media.IMAGES, 100)
    with pytest.raises(media.MediaError, match="pesa demasiado"):
        store.save(media.IMAGES, PNG + b"\x00" * 100)
    monkeypatch.setitem(media.LIMITS, media.IMAGES, 10_000)
    monkeypatch.setitem(media.TOTAL_LIMITS, media.IMAGES, len(PNG) + 10)
    store.save(media.IMAGES, PNG)
    with pytest.raises(media.MediaError, match="llena"):
        store.save(media.IMAGES, PNG + b"\x01")
    assert media.sniff_audio(OGG)[1] == ".ogg" and media.sniff_audio(b"RIFF\x00\x00\x00\x00WAVEfmt ")[1] == ".wav"
    assert media.sniff_audio(b"\x1a\x45\xdf\xa3....")[1] == ".webm" and media.sniff_audio(b"fLaC\x00\x00")[1] == ".flac"
    assert media.sniff_audio(struct.pack("4B", 0xFF, 0xFB, 0x90, 0x00))[1] == ".mp3" and media.sniff_audio(b"MZ\x90\x00") is None


# ---- the safe download --------------------------------------------------------------------------------------------
def test_only_https_addresses_of_the_public_internet_are_accepted():
    for bad in ("ftp://example.com/a.png", "file:///etc/passwd", "http://127.0.0.1/a.png", "http://localhost/a.png".replace("localhost", "[::ffff:127.0.0.1]"), "https://127.0.0.1/a.png", "https://localhost:8765/a.png".replace("localhost", "10.0.0.5"),
                "https://[::1]/a.png", "https://192.168.1.1/a.png", "https://169.254.169.254/latest/meta-data", "https://user:pass@example.com/a.png", "no es un enlace", ""):
        with pytest.raises(FetchError):
            check_url(bad)
    assert check_url("https://cdn.discordapp.com/attachments/1/2/a.png?ex=1") == "https://cdn.discordapp.com/attachments/1/2/a.png?ex=1"
    assert check_url("http://example.com/old.png") == "http://example.com/old.png"             # the odd old Tupperbox address
    assert is_public("8.8.8.8") and not is_public("127.0.0.1") and not is_public("10.1.2.3") and not is_public("fe80::1%eth0") and not is_public("junk")


async def picture_server(routes):
    app = web.Application()
    for path, handler in routes.items():
        app.router.add_get(path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{runner.addresses[0][1]}"


def test_the_download_stops_at_the_limit_and_explains_what_went_wrong():
    async def scenario():
        async def ok(request):
            return web.Response(body=PNG, content_type="image/png")

        async def big(request):
            return web.Response(body=b"\x00" * 5000)

        async def missing(request):
            return web.Response(status=404)

        async def slow(request):
            await asyncio.sleep(2)
            return web.Response(body=PNG)

        runner, base = await picture_server({"/ok": ok, "/big": big, "/missing": missing, "/slow": slow})
        try:
            got = await fetch_bytes(base + "/ok", max_bytes=1000, allow_private=True)
            errors = {}
            for name, kwargs in (("big", {"max_bytes": 1000}), ("missing", {"max_bytes": 1000}), ("slow", {"max_bytes": 1000, "timeout": 0.3})):
                try:
                    await fetch_bytes(base + "/" + name, allow_private=True, **kwargs)
                except FetchError as exc:
                    errors[name] = str(exc)
            try:
                await fetch_bytes(base + "/ok", max_bytes=1000)                      # without the test switch this very machine is off limits
            except FetchError as exc:
                errors["private"] = str(exc)
            return got, errors
        finally:
            await runner.cleanup()

    got, errors = run(scenario())
    assert got == PNG
    assert "pesa demasiado" in errors["big"] and "404" in errors["missing"] and "tardó" in errors["slow"] and "pública" in errors["private"]


# ---- Tupperbox -------------------------------------------------------------------------------------------------------
def tupper(name, avatar=None):
    return {"name": name, "avatar": avatar}


def test_importing_registers_the_names_keeps_the_pictures_on_this_pc_and_says_what_happened_to_each(tmp_path):
    async def scenario():
        async def ok(request):
            return web.Response(body=PNG, content_type="image/png")

        async def not_a_picture(request):
            return web.Response(body=b"<html>nope</html>")

        runner, base = await picture_server({"/zed.png": ok, "/kai.png": ok, "/page": not_a_picture})
        try:
            async with PanelRig() as rig:
                store = media.MediaStore(tmp_path / "media")
                rig.bridge.files, rig.bridge.images_file = store, tmp_path / "character_images.json"
                rig.bridge.fetch_allow_private = True
                rig.panel_app.character_registry["Mina"] = 222                     # somebody else's
                ws, _ = await rig.login()
                phone, _ = await rig.login()                                            # the same player on a second screen
                out = await rig.ask(ws, "panel.tupper_import", tuppers=[
                    tupper("Zed", base + "/zed.png"), tupper("Kuro", base + "/kai.png"), tupper("Mina"), tupper("Bad", base + "/page"),
                    tupper("Zed"), tupper(""), tupper("Nopic"), tupper("Offsite", "https://example.invalid/a.png")])
                chars = await frame_of(phone, "chars")
                again = await rig.ask(ws, "panel.tupper_import", tuppers=[tupper("Zed")])
                return rig, store, out, chars, again
        finally:
            await runner.cleanup()

    async def frame_of(ws, kind):
        for _ in range(50):
            got = await asyncio.wait_for(ws.receive_json(), 3)
            if got["t"] == kind:
                return got
        raise AssertionError(f"no {kind} frame")

    rig, store, out, chars, again = run(scenario())
    by_name = {}
    for r in out["data"]["results"]:
        by_name.setdefault(r["name"], r)                                                          # the first of each name
    assert by_name["Zed"]["status"] == "new" and by_name["Zed"]["image"] == "ok"
    assert by_name["Kuro"]["status"] == "mine" and by_name["Kuro"]["image"] == "ok"            # already registered to this player: only the picture
    assert by_name["Mina"]["status"] == "taken" and "otra persona" in by_name["Mina"]["note"]
    assert by_name["Bad"]["status"] == "new" and by_name["Bad"]["image"] == "error" and "imágenes" in by_name["Bad"]["note"]
    assert by_name["Nopic"]["status"] == "new" and by_name["Nopic"]["image"] == "none"
    assert by_name["Offsite"]["image"] == "error"
    assert [r["status"] for r in out["data"]["results"]].count("skipped") == 2                 # the repeated Zed and the one without a name
    assert store.usage(media.IMAGES)[0] == 1                                                    # the same picture is stored once
    assert chars["characters"][-1] != "" and "Zed" in chars["characters"] and chars["charAvatars"]["Zed"].startswith("files/images/")
    assert rig.bridge.char_image("Zed") == rig.bridge.char_avatars(111)["Zed"] and "Nopic" not in rig.bridge.char_avatars(111)
    assert "Zed" in (tmp_path / "character_images.json").read_text(encoding="utf-8")
    assert again["t"] == "rpc_err" and "espera" in again["reason"]                              # one import every few seconds


def test_an_import_is_refused_when_it_is_empty_too_big_or_there_is_nowhere_to_keep_the_pictures(tmp_path):
    async def scenario():
        async with PanelRig() as rig:
            ws, _ = await rig.login()
            nowhere = await rig.ask(ws, "panel.tupper_import", tuppers=[tupper("A")])
            rig.bridge.files = media.MediaStore(tmp_path)
            empty = await rig.ask(ws, "panel.tupper_import", tuppers=[])
            junk = await rig.ask(ws, "panel.tupper_import", tuppers="Zed")
            many = await rig.ask(ws, "panel.tupper_import", tuppers=[tupper(f"N{i}") for i in range(41)])
            return nowhere, empty, junk, many

    nowhere, empty, junk, many = run(scenario())
    assert "no puede guardar" in nowhere["reason"] and empty["t"] == "rpc_err" and junk["t"] == "rpc_err" and "hasta 40" in many["reason"]


def test_the_server_hands_out_the_library_and_nothing_else(tmp_path):
    async def scenario():
        async with PanelRig() as rig:
            store = media.MediaStore(tmp_path / "m")
            stored = store.save(media.IMAGES, PNG)
            sound = store.save(media.AUDIO, MP3)
            rig.server.files = store
            base = f"http://127.0.0.1:{rig.port}"
            out = {}
            for key, url in (("image", f"{base}/{stored.path}"), ("proxied", f"{base}/.proxy/{stored.path}"), ("audio", f"{base}/{sound.path}"),
                             ("traversal", f"{base}/files/images/..%2F..%2Fsettings.json"), ("wrong_kind", f"{base}/files/audio/{stored.name}"),
                             ("unknown", f"{base}/files/images/{'0' * 24}.png")):
                async with rig.http.get(url) as r:
                    out[key] = (r.status, r.headers.get("Content-Type"), r.headers.get("Cache-Control"), r.headers.get("X-Content-Type-Options"))
            async with rig.http.get(f"{base}/{sound.path}", headers={"Range": "bytes=0-3"}) as r:
                out["range"] = (r.status, await r.read())
            return out

    out = run(scenario())
    assert out["image"] == (200, "image/png", "public, max-age=31536000, immutable", "nosniff") and out["proxied"][0] == 200
    assert out["audio"][:2] == (200, "audio/mpeg") and out["range"] == (206, b"ID3\x04")                # a player can seek
    assert out["traversal"][0] == 404 and out["wrong_kind"][0] == 404 and out["unknown"][0] == 404
