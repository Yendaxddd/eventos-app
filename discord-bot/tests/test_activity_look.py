from eventos_app.activity.look import LookBook, clean_look
from eventos_app.activity.staff import OP_PERMS


def test_clean_look_keeps_only_look_settings_and_checks_them():
    look = clean_look({"theme": "ocean", "accent": "custom", "accentColor": "#12ab34", "volume": 3, "corners": "nope"})
    assert look["theme"] == "ocean" and look["accent"] == "custom" and look["accentColor"] == "#12ab34"
    assert "volume" not in look
    assert look["corners"] == "round"                      # a bad value falls back to the default
    assert clean_look(None) is None and clean_look({}) is None and clean_look("x") is None


def test_look_book_survives_a_restart(tmp_path):
    path = tmp_path / "look.json"
    book = LookBook(path)
    assert book.value is None
    book.set({"theme": "sepia", "accent": "gold"}, "Pergamino")
    again = LookBook(path)
    assert again.value["theme"] == "sepia" and again.name == "Pergamino"
    again.set(None)
    assert LookBook(path).value is None and LookBook(path).name == ""


def test_changing_the_event_look_needs_the_live_box():
    assert OP_PERMS["gm.look_set"] == "stage"
