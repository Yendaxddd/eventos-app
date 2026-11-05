"""Puts the translation (translator.py) between the bot and Discord without touching the bot's code.

Every message discord.py sends or edits -- in a channel, through a webhook, as the answer to a command or a button -- is built by
`handle_message_parameters` or `interaction_message_response_params`, so the text is translated there, before anything else sees it:
the content, the embeds, the labels of buttons and menus. Forms (modals) and the descriptions of the slash commands are translated
where they are sent. What players write must stay as they wrote it: `untranslated()` marks those sends."""
from __future__ import annotations

import contextlib
import contextvars
import logging

import discord

from .translator import Translator

log = logging.getLogger("eventos_app.lang")
_off = contextvars.ContextVar("eventos_untranslated", default=False)
_installed: dict = {}


@contextlib.contextmanager
def untranslated():
    """Inside this block nothing is translated (a player's own words sent by the bot or the Activity)."""
    token = _off.set(True)
    try:
        yield
    finally:
        _off.reset(token)


def _embed(tr: Translator, embed):
    if embed is None or embed is discord.utils.MISSING:
        return embed
    try:
        return discord.Embed.from_dict(tr.embed_dict(embed.to_dict()))
    except Exception:  # noqa: BLE001
        return embed


def _view(tr: Translator, view) -> None:
    if view is None or view is discord.utils.MISSING:
        return
    for item in getattr(view, "children", []) or []:
        try:
            if isinstance(getattr(item, "label", None), str):
                item.label = tr.text(item.label)
            if isinstance(getattr(item, "placeholder", None), str):
                item.placeholder = tr.text(item.placeholder)
            for option in getattr(item, "options", None) or []:
                if isinstance(getattr(option, "label", None), str):
                    option.label = tr.text(option.label)[:100]
                if isinstance(getattr(option, "description", None), str):
                    option.description = tr.text(option.description)[:100]
        except Exception:  # noqa: BLE001 - a label we cannot change keeps its English
            continue


def _message_args(tr: Translator, kwargs: dict) -> dict:
    if _off.get():
        return kwargs
    content = kwargs.get("content", discord.utils.MISSING)
    if isinstance(content, str):
        kwargs["content"] = tr.text(content)[:2000]
    if "embed" in kwargs:
        kwargs["embed"] = _embed(tr, kwargs["embed"])
    if kwargs.get("embeds") not in (None, discord.utils.MISSING):
        kwargs["embeds"] = [_embed(tr, e) for e in kwargs["embeds"]]
    if "view" in kwargs:
        _view(tr, kwargs["view"])
    return kwargs


def _modal(tr: Translator, data):
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if isinstance(out.get("title"), str):
        out["title"] = tr.text(out["title"])[:45]
    def walk(components):
        for c in components or []:
            if not isinstance(c, dict):
                continue
            for key, limit in (("label", 45), ("placeholder", 100)):
                if isinstance(c.get(key), str):
                    c[key] = tr.text(c[key])[:limit]
            walk(c.get("components"))
    walk(out.get("components"))
    return out


def _commands(tr: Translator, payload):
    def walk(items):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("description"), str) and item["description"]:
                item["description"] = tr.text(item["description"])[:100]
            for choice in item.get("choices") or []:
                if isinstance(choice, dict) and isinstance(choice.get("name"), str):
                    choice["name"] = tr.text(choice["name"])[:100]
            walk(item.get("options"))
    walk(payload if isinstance(payload, list) else [payload])
    return payload


def install(tr: Translator) -> None:
    """Translate from now on. Calling it again swaps the translator; `uninstall` puts discord.py back as it was."""
    if _installed:
        _installed["tr"] = tr
        return
    _installed["tr"] = tr
    import discord.abc
    import discord.channel
    import discord.http
    import discord.interactions
    import discord.message
    import discord.webhook.async_
    import discord.webhook.sync

    original = discord.http.handle_message_parameters

    def handle_message_parameters(*args, **kwargs):
        if args:
            kwargs.setdefault("content", args[0])
            args = ()
        return original(**_message_args(_installed["tr"], kwargs))

    for module in (discord.abc, discord.channel, discord.http, discord.interactions, discord.message, discord.webhook.async_, discord.webhook.sync):
        if getattr(module, "handle_message_parameters", None) is original:
            _installed.setdefault("modules", []).append((module, "handle_message_parameters", original))
            module.handle_message_parameters = handle_message_parameters

    original_reply = discord.webhook.async_.interaction_message_response_params

    def interaction_message_response_params(**kwargs):
        return original_reply(**_message_args(_installed["tr"], kwargs))

    original_raw = discord.webhook.async_.interaction_response_params

    def interaction_response_params(type, data=None):
        if type == discord.InteractionResponseType.modal.value and not _off.get():
            data = _modal(_installed["tr"], data)
        return original_raw(type, data)

    for module in (discord.webhook.async_, discord.interactions):
        for name, new, old in (("interaction_message_response_params", interaction_message_response_params, original_reply),
                               ("interaction_response_params", interaction_response_params, original_raw)):
            if getattr(module, name, None) is old:
                _installed.setdefault("modules", []).append((module, name, old))
                setattr(module, name, new)

    for name in ("bulk_upsert_global_commands", "bulk_upsert_guild_commands", "upsert_global_command", "upsert_guild_command"):
        old = getattr(discord.http.HTTPClient, name, None)
        if old is None:
            continue

        def make(old):
            def method(self, *args, **kwargs):
                if "payload" in kwargs:
                    kwargs["payload"] = _commands(_installed["tr"], kwargs["payload"])
                elif args:
                    args = (*args[:-1], _commands(_installed["tr"], args[-1]))
                return old(self, *args, **kwargs)
            return method

        _installed.setdefault("methods", []).append((name, old))
        setattr(discord.http.HTTPClient, name, make(old))
    log.info("bot messages are translated to Spanish")


def uninstall() -> None:
    for module, name, old in _installed.get("modules", []):
        setattr(module, name, old)
    import discord.http
    for name, old in _installed.get("methods", []):
        setattr(discord.http.HTTPClient, name, old)
    _installed.clear()
