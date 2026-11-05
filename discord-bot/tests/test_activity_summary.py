import asyncio
import json

import pytest
from aiohttp import web

from eventos_app.activity.hub import RpcError
from eventos_app.activity.staff import OP_PERMS
from eventos_app.activity.summary import AiConfig, CinemaLog, SummaryBook, chat, chunks, cinema_script, clean_base_url, transcript


class FakeApi:
    """A tiny OpenAI-compatible server: answers what it was asked, or 401 for the key «bad»."""

    def __init__(self) -> None:
        self.seen = []

    async def __aenter__(self):
        async def completions(request):
            body = await request.json()
            self.seen.append({"auth": request.headers.get("Authorization"), "body": body})
            if request.headers.get("Authorization") == "Bearer bad":
                return web.Response(status=401, text="nope")
            return web.json_response({"choices": [{"message": {"content": f"eco: {body['messages'][-1]['content'][:20]}"}}]})

        app = web.Application()
        app.router.add_post("/v1/chat/completions", completions)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/v1"
        return self

    async def __aexit__(self, *exc):
        await self.runner.cleanup()


def test_chat_talks_to_an_openai_compatible_api(tmp_path):
    async def go():
        async with FakeApi() as api:
            cfg = AiConfig(tmp_path / "ai.json")
            cfg.update({"base_url": api.url + "/chat/completions", "api_key": "sk-test-1234", "model": "m1"})
            assert cfg.base_url == api.url                              # the /chat/completions tail is taken off
            assert await chat(cfg, [{"role": "user", "content": "hola mundo"}]) == "eco: hola mundo"
            assert api.seen[0]["auth"] == "Bearer sk-test-1234" and api.seen[0]["body"]["model"] == "m1"
            cfg.update({"api_key": "bad"})
            with pytest.raises(RpcError, match="clave"):
                await chat(cfg, [{"role": "user", "content": "x"}])
            cfg.update({"base_url": "http://127.0.0.1:9/v1"})           # nothing listens there
            with pytest.raises(RpcError, match="conectar"):
                await chat(cfg, [{"role": "user", "content": "x"}], timeout=5)
    asyncio.run(go())


def test_the_key_never_leaves_and_survives_a_restart(tmp_path):
    cfg = AiConfig(tmp_path / "ai.json")
    cfg.update({"api_key": "sk-secret-abcd", "model": "gpt-x"})
    pub = cfg.public()
    assert "sk-secret" not in json.dumps(pub) and pub["has_key"] and pub["key_hint"] == "…abcd"
    again = AiConfig(tmp_path / "ai.json")
    assert again.api_key == "sk-secret-abcd" and again.model == "gpt-x"
    again.update({"model": "otro"})                                  # no key in the request: the old one stays
    assert again.api_key == "sk-secret-abcd"
    again.update({"clear_key": True})
    assert AiConfig(tmp_path / "ai.json").api_key == ""
    with pytest.raises(RpcError):
        clean_base_url("ftp://x")


def test_transcript_cinemas_and_chunks(tmp_path):
    frames = [{"ts": 0, "author": {"name": "Kuro"}, "text": "No retrocedo.", "embeds": []},
              {"ts": 60_000, "author": {"name": "Bot"}, "text": "", "embeds": [{"title": "BLACK FLASH", "description": "Ana 25"}]},
              {"ts": 120_000, "author": {"name": "Vacío"}, "text": "  ", "embeds": []}]
    lines = transcript(frames).splitlines()
    assert lines == ["[01/01 00:00] Kuro: No retrocedo.", "[01/01 00:01] Bot: BLACK FLASH Ana 25"]
    assert len(chunks("a\n" * 30_000, 1000)) > 1
    script = cinema_script({"steps": [{"type": "title", "text": "Fin", "subtitle": "cap. 3"}, {"type": "text", "speaker": "Rey", "text": "Nadie"}, {"type": "audio"}]})
    assert script == "[Título] Fin — cap. 3\nRey: Nadie"
    log = CinemaLog(tmp_path / "c.json")
    log.played({"id": "c1", "name": "Llegada"}, at_ms=5_000)
    log.played({"id": "c2", "name": "Fin"}, at_ms=50_000)
    assert [x["id"] for x in CinemaLog(tmp_path / "c.json").between(0, 10_000)] == ["c1"]


def test_summary_book_edits_and_publishing(tmp_path):
    book = SummaryBook(tmp_path / "s.json")
    book.add({"id": "s1", "title": "Cap 1", "text": "x", "cinemas": [{"id": "c1", "name": "A", "at": 1}, {"id": "c2", "name": "B", "at": 2}], "published": False})
    book.edit("s1", {"text": "nuevo", "cinemas": ["c2"]})
    assert book.get("s1")["text"] == "nuevo" and [c["id"] for c in book.get("s1")["cinemas"]] == ["c2"]
    assert book.published() == []
    book.get("s1")["published"] = True
    book.save()
    assert [s["id"] for s in SummaryBook(tmp_path / "s.json").published()] == ["s1"]
    book.delete("s1")
    with pytest.raises(RpcError):
        book.get("s1")


def test_summary_ops_need_the_summary_box():
    for op in ("gm.summary", "gm.summary_make", "gm.summary_save", "gm.summary_delete", "gm.summary_post", "gm.ai_get", "gm.ai_set", "gm.ai_test"):
        assert OP_PERMS[op] == "summary"
