"""The review-fix-re-review loop.

The renderer is real; the assessor is replaced with one that reads the
rendered file and flags a page `dense` past a word count -- the same rule
qa.render_and_measure applies -- so no PowerPoint or model is needed.
"""

from __future__ import annotations

import pytest
from pptx import Presentation

from backend.tools.generation.deck import improve as I
from backend.tools.generation.deck import qa

LONG = ("Catalyst unloading proceeds under a continuous nitrogen blanket while hydrogen sulfide "
        "is monitored at every manway and the permit is renewed at each shift change")  # 25 words


def _spec(n_bullets: int = 5) -> dict:
    return {"title": "Hydrocracker changeout", "sources": [],
            "sections": [{"title": "Safety", "slides": [
                {"type": "points", "title": "Controls during unloading", "sources": [],
                 "bullets": [f"{LONG} ({i})." for i in range(n_bullets)]},
                {"type": "points", "title": "A short page", "sources": [], "bullets": ["One.", "Two."]},
            ]}]}


def _fake_assess(dense_over: int, reviewed: list):
    def assess(path, *, vision=True, pages=None, previous=None, progress=None, release_after=True):
        reviewed.append(pages)
        out = []
        for i, slide in enumerate(Presentation(path).slides, 1):
            words = sum(len(sh.text_frame.text.split()) for sh in slide.shapes if sh.has_text_frame)
            defects = ["dense"] if words > dense_over else []
            out.append(qa.PageQuality(page=i, title="", score=10.0 - sum(qa.PENALTY[d] for d in defects),
                                      defects=defects))
        score = round(sum(p.score for p in out) / len(out), 1)
        return qa.DeckQuality(score=score, grade=qa.grade_for(score), method="layout", pages=out)
    return assess


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    from backend.models import local_vision

    monkeypatch.setattr(local_vision, "release", lambda: None)


def test_a_crowded_slide_is_split_finer_and_the_change_is_kept(tmp_path, monkeypatch):
    reviewed: list = []
    monkeypatch.setattr(qa, "assess", _fake_assess(110, reviewed))
    result = I.improve(_spec(5), tmp_path / "deck.pptx", vision=False)

    slide = result.spec["sections"][0]["slides"][0]
    assert slide["max_items"] == 4
    assert result.rounds[0].kept == ["0/0"] and result.rounds[0].reverted == []
    assert not any("dense" in p.defects for p in result.quality.pages)
    assert result.quality.score > result.rounds[0].score_before or result.quality.score == 10.0
    assert (tmp_path / "deck.pptx").exists()
    assert not list(tmp_path.glob("*.round*.pptx")), "trial renders are cleaned up"


def test_the_items_are_the_same_only_split_differently(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "assess", _fake_assess(110, []))
    before = _spec(5)
    result = I.improve(before, tmp_path / "deck.pptx", vision=False)
    assert result.spec["sections"][0]["slides"][0]["bullets"] == before["sections"][0]["slides"][0]["bullets"]
    assert "max_items" not in before["sections"][0]["slides"][0], "the caller's spec is not mutated"


def test_a_change_that_does_not_help_is_reverted(tmp_path, monkeypatch):
    # Every page is "dense" whatever the split, so no change can earn its place.
    monkeypatch.setattr(qa, "assess", _fake_assess(0, []))
    result = I.improve(_spec(5), tmp_path / "deck.pptx", vision=False)
    assert result.rounds[0].kept == [] and result.rounds[0].reverted
    assert "max_items" not in result.spec["sections"][0]["slides"][0]
    assert result.unfixable, "pages that stayed weak are reported"


def test_only_the_changed_slides_pages_are_reviewed_again(tmp_path, monkeypatch):
    reviewed: list = []
    monkeypatch.setattr(qa, "assess", _fake_assess(110, reviewed))
    I.improve(_spec(5), tmp_path / "deck.pptx", vision=False)
    assert reviewed[0] is None  # first pass: every page
    second = reviewed[1]
    assert second and len(second) == 2, f"the split slide's two pages only, got {second}"


def test_without_powerpoint_nothing_is_attempted(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "assess", lambda *a, **k: qa.DeckQuality(
        score=None, grade="unrated", method="unavailable", pages=[]))
    result = I.improve(_spec(5), tmp_path / "deck.pptx", vision=False)
    assert result.rounds == [] and result.quality.method == "unavailable"


def test_page_keys_follow_a_slide_when_page_numbers_shift():
    before = I.page_keys([None, None, (0, 0), (0, 1), None])
    after = I.page_keys([None, None, (0, 0), (0, 0), (0, 1), None])
    assert before[3] == after[4] == ((0, 1), 0)
    assert before[-1] == after[-1] == (None, 2)


@pytest.mark.parametrize("sd, pages, expected", [
    ({"type": "points", "bullets": ["a"] * 5}, 1, 4),
    ({"type": "points", "bullets": ["a"] * 6}, 2, 2),
    ({"type": "points", "bullets": ["a"] * 2}, 2, None),   # one item a page already
    ({"type": "chart", "categories": ["a", "b"]}, 1, None),  # no list to split
])
def test_the_remedy(sd, pages, expected):
    page = qa.PageQuality(page=1, title="", score=5.0, defects=["dense"])
    assert I.remedy(page, sd, pages) == expected


def test_a_page_that_is_not_crowded_gets_no_remedy():
    page = qa.PageQuality(page=1, title="", score=5.0, ratings={"hierarchy": 1, "readability": 4})
    assert I.remedy(page, {"type": "points", "bullets": ["a"] * 5}, 1) is None
