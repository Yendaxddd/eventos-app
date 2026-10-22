"""The bot speaks Spanish: its catalogue covers what it says, the translator turns its English into Spanish without touching what
players write, and the layer does it to everything discord.py sends (messages, embeds, buttons, forms, command descriptions) and to the log."""
import json
import re
import sys
import time
from pathlib import Path

import discord
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eventos_app import console_bridge, lang  # noqa: E402
from eventos_app.lang import discord_hooks  # noqa: E402
from eventos_app.lang.extract import extract  # noqa: E402
from eventos_app.lang.translator import CATALOG, Translator, load  # noqa: E402

SLOT = re.compile(r"\{\d+\}")


@pytest.fixture(scope="module")
def tr():
    return load()


def test_the_catalogue_covers_every_text_of_the_bot_with_the_same_slots():
    catalog = {e["id"]: e for e in json.loads(CATALOG.read_text(encoding="utf-8"))}
    found = extract()
    missing = [t.en for t in found if t.id not in catalog]
    assert not missing, f"{len(missing)} texts of the bot have no Spanish (run `python -m eventos_app.i18n.extract`): {missing[:5]}"
    for entry in catalog.values():
        assert sorted(SLOT.findall(entry["en"])) == sorted(SLOT.findall(entry["es"])), entry["en"]
    assert len(catalog) > 1000


def test_a_sentence_with_values_is_translated_and_its_values_keep_their_place(tr):
    assert tr.text("✅ <@123> evaded! (0.42s)") == "✅ ¡<@123> esquivó! (0.42s)"
    assert tr.text("⚔️ BOSS FIGHT STARTED: Rey de las Maldiciones") == "⚔️ COMBATE CONTRA EL JEFE INICIADO: Rey de las Maldiciones"
    assert tr.text("Damage") == "Daño" and tr.text("  Status ") == "  Estado "                 # a field name, whole


def test_what_players_write_and_names_are_left_alone(tr):
    for text in ("hola a todos", "Kuro: *attack* ahora", "Damage control is my job", "Status quo", "", None, 5):
        assert tr.text(text) == text
    assert tr.text("Rey de las Maldiciones") == "Rey de las Maldiciones"


def test_several_sentences_glued_together_are_each_translated_and_nothing_is_translated_twice(tr):
    glued = "⚔️ BOSS FIGHT STARTED: Lyra\n✅ <@1> evaded! (1.00s)"
    assert tr.text(glued) == "⚔️ COMBATE CONTRA EL JEFE INICIADO: Lyra\n✅ ¡<@1> esquivó! (1.00s)"
    assert tr.text(tr.text(glued)) == tr.text(glued)


def test_a_known_word_dropped_into_a_sentence_is_translated_too():
    small = Translator([{"en": "Difficulty: {1} for {2}", "es": "Dificultad: {1} para {2}", "kind": "user"}])
    assert small.text("Difficulty: HARD for Ana") == "Dificultad: DIFÍCIL para Ana"
    assert small.text("Difficulty: medium for Medium") == "Dificultad: media para Media"


def test_a_broken_translation_is_never_used():
    bad = Translator([{"en": "Hit {1} for {2}", "es": "Golpe a {1}", "kind": "user"}, {"en": "Ready to go", "es": "Listo para ir", "kind": "user"}])
    assert bad.text("Hit Ana for 5") == "Hit Ana for 5" and bad.text("Ready to go") == "Listo para ir"


def test_translating_is_fast_enough_for_a_burst_of_qte_messages(tr):
    texts = [f"✅ <@{i}> evaded! ({i / 100:.2f}s)" for i in range(300)] + [f"Something nobody wrote {i}" for i in range(300)]
    start = time.perf_counter()
    for text in texts:
        tr.text(text)
    assert (time.perf_counter() - start) / len(texts) < 0.004                                    # a few milliseconds at most per message


def test_everything_discord_py_sends_goes_out_in_spanish_but_not_what_is_marked_as_a_players(tr):
    discord_hooks.install(tr)
    try:
        embed = discord.Embed(title="⚔️ BOSS FIGHT STARTED: Lyra", description="✅ <@1> evaded! (1.00s)")
        embed.add_field(name="Damage", value="150")
        embed.set_footer(text="Status")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Damage"))
        with discord.abc.handle_message_parameters(content="✅ <@2> evaded! (0.50s)", embed=embed, view=view) as params:
            payload = params.payload
        assert payload["content"] == "✅ ¡<@2> esquivó! (0.50s)"
        sent = payload["embeds"][0]
        assert sent["title"].startswith("⚔️ COMBATE CONTRA EL JEFE") and "esquivó" in sent["description"]
        assert sent["fields"][0]["name"] == "Daño" and sent["footer"]["text"] == "Estado"
        assert view.children[0].label == "Daño"
        with discord_hooks.untranslated():
            with discord.message.handle_message_parameters(content="✅ <@2> evaded! (0.50s)") as params:
                assert params.payload["content"] == "✅ <@2> evaded! (0.50s)"
        reply = discord.webhook.async_.interaction_message_response_params(type=4, content="Damage")
        assert reply.payload["data"]["content"] == "Daño"
        commands = [{"name": "resethp", "description": "[ADMIN] Reset HP for a specific player or all players", "options": [{"name": "player", "description": "Damage"}]}]
        discord_hooks._commands(tr, commands)
        assert commands[0]["description"].startswith("[ADMIN] Reinicia") and len(commands[0]["description"]) <= 100
        assert commands[0]["options"][0]["description"] == "Daño"
    finally:
        discord_hooks.uninstall()
    with discord.abc.handle_message_parameters(content="Damage") as params:
        assert params.payload["content"] == "Damage"                                              # back to English once removed


def test_the_app_log_is_translated_when_spanish_is_chosen_and_english_puts_everything_back():
    seen = []
    console_bridge.console.set_sink(lambda segments: seen.append("".join(s.text for s in segments)))
    try:
        assert lang.activate("es") is not None
        console_bridge.console.print("[green]✓ Special object approved: Espejo[/green]")
        lang.activate("en")
        console_bridge.console.print("[green]✓ Special object approved: Espejo[/green]")
    finally:
        console_bridge.console.set_sink(None)
        lang.activate("en")
    assert seen == ["✓ Objeto especial aprobado: Espejo", "✓ Special object approved: Espejo"]
