import pytest

from eventos_app.activity.agenda import HOURS, AgendaBook, clean_week
from eventos_app.activity.hub import RpcError
from eventos_app.activity.staff import OP_PERMS

NOW = 1_800_000_000_000
H = 3_600_000


def test_clean_week_is_always_168_valid_hours():
    assert clean_week(None) == "0" * HOURS
    assert clean_week("2x1" + "9" * 400) == "201" + "0" * (HOURS - 3)
    assert clean_week([2, 1, 0]) .startswith("210")


def test_week_is_kept_and_an_empty_week_forgets_the_person(tmp_path):
    book = AgendaBook(tmp_path / "a.json")
    book.set_week(7, "Mina", "2" * 10, "solo tardes", "Europe/Madrid")
    again = AgendaBook(tmp_path / "a.json")
    assert again.people["7"]["week"].startswith("2" * 10) and again.people["7"]["note"] == "solo tardes"
    again.set_week(7, "Mina", "", "")
    assert "7" not in AgendaBook(tmp_path / "a.json").people


def test_a_poll_from_proposal_to_chosen_date(tmp_path):
    book = AgendaBook(tmp_path / "a.json")
    with pytest.raises(RpcError):
        book.propose("Ana", "x", [NOW - 30 * 24 * H], now_ms=NOW)          # only dates from today on
    poll = book.propose("Ana", "Capítulo 4", [NOW + 50 * H, NOW + 26 * H, NOW + 26 * H], 90, now_ms=NOW)
    assert [o["at"] for o in poll["options"]] == [NOW + 26 * H, NOW + 50 * H]   # sorted, no repeats
    first, second = (o["id"] for o in poll["options"])
    book.vote(poll["id"], 7, "Mina", {first: "yes", second: "maybe", "nope": "yes"})
    book.vote(poll["id"], 8, "Luis", {first: "no", second: "bad"})
    assert book.poll(poll["id"])["votes"] == {"7": {first: "yes", second: "maybe"}, "8": {first: "no"}}
    book.vote(poll["id"], 8, "Luis", {})                                      # answering nothing takes the vote back
    assert "8" not in book.poll(poll["id"])["votes"]
    book.close(poll["id"], first)
    with pytest.raises(RpcError):
        book.vote(poll["id"], 7, "Mina", {first: "no"})
    nxt = book.next_event(now_ms=NOW)
    assert nxt["at"] == NOW + 26 * H and nxt["title"] == "Capítulo 4" and nxt["minutes"] == 90
    assert book.next_event(now_ms=NOW + 30 * H) is None                       # it is over
    book.close(poll["id"], None)
    assert book.poll(poll["id"])["open"] and book.next_event(now_ms=NOW) is None
    book.delete(poll["id"])
    assert AgendaBook(tmp_path / "a.json").polls == []


def test_the_agenda_box_guards_the_game_master_ops():
    for op in ("gm.schedule_propose", "gm.schedule_close", "gm.schedule_delete"):
        assert OP_PERMS[op] == "schedule"


def test_concrete_dates_override_the_week_and_keep_the_zone(tmp_path):
    from eventos_app.activity.agenda import MAX_DAYS
    book = AgendaBook(tmp_path / "a.json")
    book.set_day(7, "Mina", "2026-11-15", {"a": "yes", "from": "18:00", "to": "23:00", "note": "  desde   el móvil "}, today="2026-11-04",
                 tz="America/Mexico_City", offset=-360)
    book.set_day(7, "Mina", "2026-11-20", {"a": "no", "from": "10:00", "to": "12:00", "note": "boda"}, today="2026-11-04")
    again = AgendaBook(tmp_path / "a.json").people["7"]
    assert again["days"]["2026-11-15"] == {"a": "yes", "from": "18:00", "to": "23:00", "note": "desde el móvil"}
    assert again["days"]["2026-11-20"] == {"a": "no", "from": "", "to": "", "note": "boda"}          # «no» has no hours
    assert again["tz"] == "America/Mexico_City" and again["offset"] == -360 and again["week"] == "0" * HOURS
    with pytest.raises(RpcError, match="fecha"):
        book.set_day(7, "Mina", "2026-02-30", {"a": "yes"})
    with pytest.raises(RpcError, match="fin"):
        book.set_day(7, "Mina", "2026-11-16", {"a": "yes", "from": "20:00", "to": "19:00"})
    with pytest.raises(RpcError):
        book.set_day(7, "Mina", "2026-11-16", {"a": "sí"})
    book.set_week(7, "Mina", "2" * 5, "", "Europe/Madrid", 60)                     # the week keeps the days
    assert set(book.people["7"]["days"]) == {"2026-11-15", "2026-11-20"} and book.people["7"]["tz"] == "Europe/Madrid"
    book.set_zone(7, "Mina", "Asia/Tokyo", 540)                                     # picked by hand: the browser no longer changes it
    book.set_week(7, "Mina", "2" * 5, "", "Europe/Madrid", 60)
    assert book.people["7"]["tz"] == "Asia/Tokyo" and book.people["7"]["tzManual"]
    book.set_day(7, "Mina", "2026-11-16", {"a": "maybe"}, today="2026-11-19")      # days long gone are dropped
    assert set(book.people["7"]["days"]) == {"2026-11-20"}                         # the 15th and 16th are over by the 19th
    book.set_zone(7, "Mina", "Europe/Madrid", 60, manual=False)
    book.set_week(7, "Mina", "", "")
    for key in list(book.people["7"]["days"]):
        book.set_day(7, "Mina", key, None, today="2026-11-04")
    assert "7" not in book.people                                                   # nothing left: forgotten
    for i in range(MAX_DAYS):
        book.set_day(8, "Luis", f"2027-{1 + i // 28:02d}-{1 + i % 28:02d}", {"a": "yes"}, today="2026-11-04")
    with pytest.raises(RpcError, match="hasta"):
        book.set_day(8, "Luis", "2027-12-31", {"a": "yes"}, today="2026-11-04")
