import pytest

from eventos_app.activity.hub import RpcError
from eventos_app.activity.results import ResultsBook, RoundTracker, awards_of, build_screen, clean_screen
from eventos_app.activity.staff import OP_PERMS

NAMES = {1: "Ana", 2: "Mina"}


def fight() -> RoundTracker:
    r = RoundTracker()
    r.track("fight_start", {})
    r.track("boss_spawn", {"name": "Sukuna"})
    r.track("black_flash", {"user": 1, "damage": 30, "ms": 250})
    r.track("black_flash", {"user": 1, "damage": 20, "ms": 210})
    r.track("parry_ok", {"user": 2, "ms": 180})
    r.track("rescue_ok", {"user": 2, "ms": 400})
    r.track("player_hit", {"user": 2, "amount": 15})
    r.track("qte_fail", {"user": 1})
    r.track("boss_hit", {"amount": 50})
    r.track("boss_defeated", {"name": "Sukuna"})
    r.track("evade_ok", {"user": "bad id"})                 # never breaks
    r.track("unknown_event", {"user": 1})
    return r


def test_the_round_counts_what_each_player_did():
    rows = {r["name"]: r for r in fight().table(NAMES.get)}
    assert rows["Ana"]["bf"] == 2 and rows["Ana"]["damage"] == 50 and rows["Ana"]["best_bf"] == 210 and rows["Ana"]["fails"] == 1
    assert rows["Mina"]["parries"] == 1 and rows["Mina"]["saves"] == 1 and rows["Mina"]["taken"] == 15 and rows["Mina"]["best_parry"] == 180
    assert rows["Ana"]["score"] == 50 + 2 * 15 - 3


def test_a_new_fight_starts_a_new_round():
    r = fight()
    r.track("fight_start", {})
    assert r.players == {} and r.boss is None


def test_awards_go_round_and_read_well():
    rows = fight().table(NAMES.get)
    awards = {a["id"]: a for a in awards_of(rows)}
    assert awards["parry"]["name"] == "Mina" and awards["parry"]["value"] == "180 ms"
    assert awards["guardian"]["value"] == "1 rescate"              # singular
    assert awards["bf"]["value"] == "2 Black Flash"
    counts = {}
    for a in awards.values():
        counts[a["name"]] = counts.get(a["name"], 0) + 1
    assert max(counts.values()) <= 3


def test_a_screen_from_the_round_and_one_edited_by_hand(tmp_path):
    state = fight().public(NAMES.get)
    screen = build_screen(state, by="Ana")
    kinds = [b["type"] for b in screen["blocks"]]
    assert kinds == ["podium", "awards", "stats"]
    assert "derrotado" in screen["subtitle"]
    assert screen["blocks"][0]["entries"][0]["name"] == "Ana"
    # hand edits are cleaned: unknown blocks dropped, long text cut
    edited = clean_screen({"id": screen["id"], "title": "x" * 300, "blocks": screen["blocks"] + [{"type": "nope"}, {"type": "text", "body": "Decisión"}]})
    assert len(edited["title"]) == 80 and [b["type"] for b in edited["blocks"]][-1] == "text"
    book = ResultsBook(tmp_path / "r.json")
    saved = book.put(edited)
    book.show(saved["id"])
    again = ResultsBook(tmp_path / "r.json")
    assert again.get(saved["id"])["blocks"][-1]["body"] == "Decisión" and again.last == saved["id"]
    again.delete(saved["id"])
    with pytest.raises(RpcError):
        again.show(saved["id"])


def test_results_ops_need_the_results_box():
    for op in ("gm.results", "gm.results_build", "gm.results_save", "gm.results_show", "gm.results_hide", "gm.results_delete",
               "gm.results_auto", "gm.results_reset"):
        assert OP_PERMS[op] == "results"
