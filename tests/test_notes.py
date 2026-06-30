"""Tests for aulaforge.notes — no real Ollama needed."""

from __future__ import annotations

from pathlib import Path

import pytest

import aulaforge.notes as notes_module
from aulaforge.config import LlmConfig
from aulaforge.models import Lesson

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lesson(tmp_path: Path) -> Lesson:
    output_dir = tmp_path / "output" / "aula_01_intro"
    return Lesson(
        number=1,
        title="Intro",
        slug="aula_01_intro",
        video_path=tmp_path / "aula.mp4",
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# get_transcript_for_notes
# ---------------------------------------------------------------------------


def test_get_transcript_prefers_clean_over_raw(tmp_path: Path) -> None:
    lesson = _make_lesson(tmp_path)
    lesson.output_dir.mkdir(parents=True)
    (lesson.output_dir / "03_TRANSCRICAO_LIMPA.md").write_text("clean", encoding="utf-8")
    (lesson.output_dir / "01_TRANSCRICAO_BRUTA.txt").write_text("raw", encoding="utf-8")
    assert notes_module.get_transcript_for_notes(lesson) == "clean"


def test_get_transcript_falls_back_to_raw_when_clean_absent(tmp_path: Path) -> None:
    lesson = _make_lesson(tmp_path)
    lesson.output_dir.mkdir(parents=True)
    (lesson.output_dir / "01_TRANSCRICAO_BRUTA.txt").write_text("raw only", encoding="utf-8")
    assert notes_module.get_transcript_for_notes(lesson) == "raw only"


def test_get_transcript_returns_none_when_neither_file_exists(tmp_path: Path) -> None:
    lesson = _make_lesson(tmp_path)
    lesson.output_dir.mkdir(parents=True)
    assert notes_module.get_transcript_for_notes(lesson) is None


# ---------------------------------------------------------------------------
# compute_notes_input_hash
# ---------------------------------------------------------------------------


def test_compute_notes_input_hash_is_deterministic() -> None:
    cfg = LlmConfig()
    h1 = notes_module.compute_notes_input_hash("texto", cfg)
    h2 = notes_module.compute_notes_input_hash("texto", cfg)
    assert h1 == h2


def test_compute_notes_input_hash_changes_with_transcript() -> None:
    cfg = LlmConfig()
    assert notes_module.compute_notes_input_hash("A", cfg) != notes_module.compute_notes_input_hash(
        "B", cfg
    )


def test_compute_notes_input_hash_changes_with_model() -> None:
    h1 = notes_module.compute_notes_input_hash("t", LlmConfig(model="qwen3:30b"))
    h2 = notes_module.compute_notes_input_hash("t", LlmConfig(model="qwen3:7b"))
    assert h1 != h2


def test_compute_notes_input_hash_changes_with_temperature() -> None:
    h1 = notes_module.compute_notes_input_hash("t", LlmConfig(temperature=0.2))
    h2 = notes_module.compute_notes_input_hash("t", LlmConfig(temperature=0.9))
    assert h1 != h2


def test_compute_notes_input_hash_changes_with_max_input_chars() -> None:
    h1 = notes_module.compute_notes_input_hash("t", LlmConfig(max_input_chars=5000))
    h2 = notes_module.compute_notes_input_hash("t", LlmConfig(max_input_chars=10000))
    assert h1 != h2


def test_compute_notes_input_hash_includes_prompt_version() -> None:
    cfg = LlmConfig()
    original_version = notes_module.NOTES_PROMPT_VERSION
    h1 = notes_module.compute_notes_input_hash("t", cfg)
    notes_module.NOTES_PROMPT_VERSION = "v99"
    try:
        h2 = notes_module.compute_notes_input_hash("t", cfg)
    finally:
        notes_module.NOTES_PROMPT_VERSION = original_version
    assert h1 != h2


# ---------------------------------------------------------------------------
# split_at_block_boundaries
# ---------------------------------------------------------------------------


def test_split_returns_single_chunk_when_fits() -> None:
    text = "## Bloco curto\nconteudo"
    chunks = notes_module.split_at_block_boundaries(text, max_chars=10000)
    assert chunks == [text]


def test_split_divides_at_bloco_headers() -> None:
    block1 = "## Bloco (00:00:00 - 00:15:00)\n" + "a" * 300
    block2 = "## Bloco (00:15:00 - 00:30:00)\n" + "b" * 300
    text = block1 + block2
    chunks = notes_module.split_at_block_boundaries(text, max_chars=400)
    assert len(chunks) == 2
    assert "aaa" in chunks[0]
    assert "bbb" in chunks[1]


def test_split_handles_no_bloco_headers() -> None:
    text = "sem headers\n" + "x" * 200
    chunks = notes_module.split_at_block_boundaries(text, max_chars=50)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_oversized_single_block_gets_own_chunk() -> None:
    block = "## Bloco 1\n" + "z" * 200
    chunks = notes_module.split_at_block_boundaries(block, max_chars=50)
    assert len(chunks) == 1


def test_split_returns_non_empty_list_always() -> None:
    chunks = notes_module.split_at_block_boundaries("", max_chars=100)
    assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# generate_lesson_note
# ---------------------------------------------------------------------------


def test_generate_lesson_note_single_call_when_transcript_fits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = LlmConfig(max_input_chars=99999)
    call_log: list[str] = []

    def fake_generate(
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        base_url: str,
        max_retries: int,
    ) -> str:
        call_log.append(user_message[:20])
        return "# Nota"

    monkeypatch.setattr(notes_module, "generate_note", fake_generate)
    result = notes_module.generate_lesson_note("Aula 1", "texto curto", cfg)
    assert result == "# Nota"
    assert len(call_log) == 1


def test_generate_lesson_note_chunked_path_used_for_long_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = LlmConfig(max_input_chars=50)
    call_log: list[str] = []

    def fake_generate(
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        base_url: str,
        max_retries: int,
    ) -> str:
        call_log.append(f"call_{len(call_log) + 1}")
        return f"resposta_{len(call_log)}"

    monkeypatch.setattr(notes_module, "generate_note", fake_generate)
    block1 = "## Bloco 1\n" + "a" * 100
    block2 = "## Bloco 2\n" + "b" * 100
    text = block1 + block2
    result = notes_module.generate_lesson_note("Aula X", text, cfg)
    # 2 partial + 1 consolidation = 3 total calls
    assert len(call_log) == 3
    assert result == "resposta_3"


def test_generate_lesson_note_includes_no_think_in_single_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = LlmConfig(max_input_chars=99999)
    captured_user_messages: list[str] = []

    def fake_generate(
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        base_url: str,
        max_retries: int,
    ) -> str:
        captured_user_messages.append(user_message)
        return "nota"

    monkeypatch.setattr(notes_module, "generate_note", fake_generate)
    notes_module.generate_lesson_note("Test", "texto", cfg)
    assert any("/no_think" in msg for msg in captured_user_messages)


def test_generate_lesson_note_includes_no_think_in_chunked_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = LlmConfig(max_input_chars=50)
    captured_user_messages: list[str] = []

    def fake_generate(
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        base_url: str,
        max_retries: int,
    ) -> str:
        captured_user_messages.append(user_message)
        return "nota"

    monkeypatch.setattr(notes_module, "generate_note", fake_generate)
    block1 = "## Bloco 1\n" + "a" * 100
    block2 = "## Bloco 2\n" + "b" * 100
    notes_module.generate_lesson_note("Test", block1 + block2, cfg)
    assert all("/no_think" in msg for msg in captured_user_messages)


def test_generate_lesson_note_passes_model_and_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = LlmConfig(model="qwen3:7b", temperature=0.5, max_input_chars=99999)
    captured: list[dict[str, object]] = []

    def fake_generate(
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: float,
        base_url: str,
        max_retries: int,
    ) -> str:
        captured.append({"model": model, "temperature": temperature})
        return "ok"

    monkeypatch.setattr(notes_module, "generate_note", fake_generate)
    notes_module.generate_lesson_note("Test", "texto", cfg)
    assert captured[0]["model"] == "qwen3:7b"
    assert captured[0]["temperature"] == 0.5
