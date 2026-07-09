"""Story-to-Video P1 — story_chunker tests (pure, deterministic)."""
from __future__ import annotations

from app.features.render.ai.llm.story_chunker import chunk_chapter


def test_empty_returns_empty_list():
    assert chunk_chapter("") == []
    assert chunk_chapter("   ") == []
    assert chunk_chapter(None) == []  # type: ignore[arg-type]


def test_short_text_single_chunk():
    assert chunk_chapter("A short chapter.", max_chars=1000) == ["A short chapter."]


def test_long_text_splits_with_overlap():
    paras = [f"Đoạn {i} " + ("từ " * 40) for i in range(20)]
    text = "\n\n".join(paras)
    chunks = chunk_chapter(text, max_chars=400, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 400 + 40 for c in chunks)  # cap + overlap seed slack
    # Overlap: the tail of chunk[0] reappears at the head of chunk[1].
    tail = chunks[0][-40:]
    assert any(part and part in chunks[1] for part in [tail[-10:]])


def test_oversized_single_unit_is_hard_sliced():
    giant = "x" * 1000  # one paragraph, no boundaries
    chunks = chunk_chapter(giant, max_chars=200, overlap=0)
    assert len(chunks) == 5
    assert all(len(c) <= 200 for c in chunks)


def test_never_raises_on_weird_input():
    assert isinstance(chunk_chapter("{}{}{}\n\n" + ("a" * 5000), max_chars=300), list)
