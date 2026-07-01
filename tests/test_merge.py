"""Tests for aulaforge.merge (Fase 6) — sem Whisper, Tesseract, Ollama, FFmpeg ou Notion."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import aulaforge.cli as cli_module
from aulaforge.checkpoints import (
    MERGE_STEP,
    PROCESSING_LOG_FILENAME,
    needs_merge_processing,
    process_lesson_merge,
    read_processing_log,
    record_merge_skipped_disabled,
    record_merge_skipped_no_inputs,
    record_skipped_merge,
)
from aulaforge.cli import app
from aulaforge.config import MergeConfig
from aulaforge.discovery import discover_course
from aulaforge.merge import (
    MERGE_MD_FILENAME,
    _build_blocks,
    _closest_segment_index,
    _parse_hms,
    compute_merge_input_hash,
    merge_lesson,
    parse_ocr_results,
    parse_transcript_segments,
    write_merge_md,
)
from aulaforge.models import OcrFrameResult, Status, TranscriptSegment

runner = CliRunner()

# ── Builders de fixtures in-memory ───────────────────────────────────────────


def _seg(start: float, end: float, text: str = "texto falado") -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text=text)


def _ocr(
    timestamp: str,
    screen_type: str = "other",
    text: str = "texto visual",
    detected_code: str | None = None,
    detected_commands: str | None = None,
    confidence: str = "high",
) -> OcrFrameResult:
    return OcrFrameResult(
        timestamp=timestamp,
        frame_path=f"frames/{timestamp.replace(':', '-')}.png",
        screen_type=screen_type,
        text=text,
        detected_code=detected_code,
        detected_commands=detected_commands,
        confidence=confidence,
    )


_DEFAULT_CFG = MergeConfig(window_seconds=15.0, group_minutes=10)

FAKE_TRANSCRIPT_JSON = json.dumps(
    [{"start": 0.0, "end": 10.0, "text": "Olá, vamos começar."}]
)
FAKE_OCR_JSON = json.dumps(
    [
        {
            "timestamp": "00:00:05",
            "frame_path": "frames/00-00-05.png",
            "screen_type": "vscode",
            "text": "def main():",
            "detected_code": "def main():\n    pass",
            "detected_commands": None,
            "confidence": "high",
        }
    ]
)


# ── Section 1: _parse_hms ─────────────────────────────────────────────────────


def test_parse_hms_zero() -> None:
    assert _parse_hms("00:00:00") == 0.0


def test_parse_hms_minutes_only() -> None:
    assert _parse_hms("00:01:00") == 60.0


def test_parse_hms_hours_only() -> None:
    assert _parse_hms("01:00:00") == 3600.0


def test_parse_hms_mixed() -> None:
    assert _parse_hms("00:12:15") == 735.0


def test_parse_hms_large() -> None:
    assert _parse_hms("02:30:45") == 2 * 3600 + 30 * 60 + 45


def test_parse_hms_invalid_raises() -> None:
    with pytest.raises((ValueError, IndexError)):
        _parse_hms("invalid")


def test_parse_hms_too_few_parts_raises() -> None:
    with pytest.raises((ValueError, IndexError)):
        _parse_hms("12:15")


# ── Section 2: _closest_segment_index ─────────────────────────────────────────


def test_closest_segment_inside_interval() -> None:
    segs = [_seg(0.0, 20.0)]
    assert _closest_segment_index(10.0, segs, window_seconds=5.0) == 0


def test_closest_segment_before_within_window() -> None:
    segs = [_seg(10.0, 20.0)]
    assert _closest_segment_index(5.0, segs, window_seconds=10.0) == 0


def test_closest_segment_before_outside_window() -> None:
    segs = [_seg(10.0, 20.0)]
    assert _closest_segment_index(0.0, segs, window_seconds=5.0) is None


def test_closest_segment_after_within_window() -> None:
    segs = [_seg(0.0, 10.0)]
    assert _closest_segment_index(20.0, segs, window_seconds=15.0) == 0


def test_closest_segment_picks_nearest_of_two() -> None:
    segs = [_seg(0.0, 5.0), _seg(20.0, 30.0)]
    # Frame at t=18 is 8s after seg0's end vs 2s before seg1's start → seg1 wins
    assert _closest_segment_index(18.0, segs, window_seconds=15.0) == 1


# ── Section 3: _build_blocks ──────────────────────────────────────────────────


def test_build_blocks_transcript_only() -> None:
    segs = [_seg(0.0, 5.0, "ola"), _seg(10.0, 15.0, "mundo")]
    blocks = _build_blocks(segs, None, window_seconds=15.0)
    assert len(blocks) == 2
    assert all(b.transcript_segment is not None for b in blocks)
    assert all(b.ocr_events == [] for b in blocks)


def test_build_blocks_ocr_only() -> None:
    ocrs = [_ocr("00:00:05"), _ocr("00:00:20")]
    blocks = _build_blocks(None, ocrs, window_seconds=15.0)
    assert len(blocks) == 2
    assert all(b.transcript_segment is None for b in blocks)


def test_build_blocks_ocr_assigned_to_segment() -> None:
    segs = [_seg(0.0, 20.0)]
    ocrs = [_ocr("00:00:10")]  # t=10, inside [0, 20]
    blocks = _build_blocks(segs, ocrs, window_seconds=15.0)
    assert len(blocks) == 1
    assert blocks[0].transcript_segment is not None
    assert len(blocks[0].ocr_events) == 1


def test_build_blocks_multiple_ocr_same_segment_no_duplication() -> None:
    """Vários frames OCR dentro do mesmo segmento → apenas 1 bloco de transcrição."""
    segs = [_seg(0.0, 30.0, "segmento longo")]
    ocrs = [_ocr("00:00:05"), _ocr("00:00:15"), _ocr("00:00:25")]
    blocks = _build_blocks(segs, ocrs, window_seconds=5.0)
    # Deve existir apenas 1 bloco (o do segmento de transcrição)
    assert len(blocks) == 1
    assert blocks[0].transcript_segment is not None
    assert len(blocks[0].ocr_events) == 3


def test_build_blocks_ocr_outside_window_standalone() -> None:
    segs = [_seg(0.0, 10.0)]
    ocrs = [_ocr("00:01:00")]  # t=60, muito longe do segmento
    blocks = _build_blocks(segs, ocrs, window_seconds=5.0)
    assert len(blocks) == 2
    standalone = [b for b in blocks if b.transcript_segment is None]
    assert len(standalone) == 1


def test_build_blocks_sorted_by_time() -> None:
    segs = [_seg(100.0, 110.0), _seg(10.0, 20.0)]  # fora de ordem
    blocks = _build_blocks(segs, None, window_seconds=5.0)
    times = [b.time_seconds for b in blocks]
    assert times == sorted(times)


def test_build_blocks_invalid_ocr_timestamp_skipped() -> None:
    segs = [_seg(0.0, 10.0)]
    bad_ocr = [
        _ocr("invalid"),
        _ocr("00:00:05"),
    ]
    blocks = _build_blocks(segs, bad_ocr, window_seconds=15.0)
    # O frame inválido é descartado; o válido deve ser atribuído ao segmento
    assert len(blocks) == 1
    assert len(blocks[0].ocr_events) == 1


def test_build_blocks_empty_inputs() -> None:
    assert _build_blocks(None, None, window_seconds=15.0) == []
    assert _build_blocks([], [], window_seconds=15.0) == []


# ── Section 4: merge_lesson ────────────────────────────────────────────────────


def test_merge_lesson_full_contains_both_labels() -> None:
    segs = [_seg(0.0, 10.0, "texto falado")]
    ocrs = [_ocr("00:00:05", screen_type="vscode", text="código")]
    content = merge_lesson(segs, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "[Falado]" in content
    assert "[Visual — vscode]" in content


def test_merge_lesson_transcript_only_flags_ocr_unavailable() -> None:
    segs = [_seg(0.0, 10.0)]
    content = merge_lesson(segs, None, "Aula 1", _DEFAULT_CFG)
    assert "OCR disponível: **Não**" in content
    assert "[Falado]" in content


def test_merge_lesson_ocr_only_flags_transcript_unavailable() -> None:
    ocrs = [_ocr("00:00:05")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "Transcrição disponível: **Não**" in content
    assert "[Visual" in content


def test_merge_lesson_both_available_flags() -> None:
    segs = [_seg(0.0, 10.0)]
    ocrs = [_ocr("00:00:05")]
    content = merge_lesson(segs, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "Transcrição disponível: **Sim**" in content
    assert "OCR disponível: **Sim**" in content


def test_merge_lesson_empty_both_shows_no_event_message() -> None:
    content = merge_lesson([], [], "Aula 1", _DEFAULT_CFG)
    assert "Nenhum evento encontrado" in content


def test_merge_lesson_code_rendered_in_code_block() -> None:
    ocrs = [_ocr("00:00:05", screen_type="vscode", detected_code="def foo(): pass")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "```python" in content
    assert "def foo(): pass" in content


def test_merge_lesson_commands_rendered_in_bash_block() -> None:
    ocrs = [_ocr("00:00:05", screen_type="terminal", detected_commands="pip install aulaforge")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "```bash" in content
    assert "pip install aulaforge" in content


def test_merge_lesson_low_confidence_annotated() -> None:
    ocrs = [_ocr("00:00:05", confidence="low", text="texto incerto")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "confiança: low" in content


def test_merge_lesson_medium_confidence_annotated() -> None:
    ocrs = [_ocr("00:00:05", confidence="medium", text="texto médio")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "confiança: medium" in content


def test_merge_lesson_high_confidence_not_annotated() -> None:
    ocrs = [_ocr("00:00:05", confidence="high", text="texto claro")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "confiança" not in content


def test_merge_lesson_grouping_produces_headings() -> None:
    # 3 segmentos em minutos diferentes
    segs = [_seg(0.0, 5.0), _seg(600.0, 605.0), _seg(1200.0, 1205.0)]
    content = merge_lesson(segs, None, "Aula 1", _DEFAULT_CFG)
    assert "### 00:00:00" in content
    assert "### 00:10:00" in content
    assert "### 00:20:00" in content


def test_merge_lesson_transcript_segment_appears_once() -> None:
    """Garante que o texto do segmento não é duplicado quando vários OCR o referem."""
    segs = [_seg(0.0, 30.0, "segmento único")]
    ocrs = [_ocr("00:00:05"), _ocr("00:00:15"), _ocr("00:00:25")]
    content = merge_lesson(segs, ocrs, "Aula 1", _DEFAULT_CFG)
    # O texto falado deve aparecer exatamente uma vez
    assert content.count("segmento único") == 1


def test_merge_lesson_title_in_header() -> None:
    content = merge_lesson([_seg(0.0, 5.0)], None, "Minha Aula de Teste", _DEFAULT_CFG)
    assert "Minha Aula de Teste" in content


def test_merge_lesson_fallback_to_text_when_no_code_or_commands() -> None:
    ocrs = [_ocr("00:00:05", screen_type="slides", text="texto de slide")]
    content = merge_lesson(None, ocrs, "Aula 1", _DEFAULT_CFG)
    assert "_texto de slide_" in content


# ── Section 5: compute_merge_input_hash ──────────────────────────────────────


def test_compute_merge_input_hash_deterministic() -> None:
    h1 = compute_merge_input_hash("transcript", "ocr", _DEFAULT_CFG)
    h2 = compute_merge_input_hash("transcript", "ocr", _DEFAULT_CFG)
    assert h1 == h2


def test_compute_merge_input_hash_changes_on_transcript() -> None:
    cfg = _DEFAULT_CFG
    h1 = compute_merge_input_hash("transcript_v1", "ocr", cfg)
    h2 = compute_merge_input_hash("transcript_v2", "ocr", cfg)
    assert h1 != h2


def test_compute_merge_input_hash_changes_on_ocr() -> None:
    cfg = _DEFAULT_CFG
    h1 = compute_merge_input_hash("transcript", "ocr_v1", cfg)
    h2 = compute_merge_input_hash("transcript", "ocr_v2", cfg)
    assert h1 != h2


def test_compute_merge_input_hash_changes_on_window_seconds() -> None:
    cfg1 = MergeConfig(window_seconds=5.0, group_minutes=10)
    cfg2 = MergeConfig(window_seconds=30.0, group_minutes=10)
    assert compute_merge_input_hash("t", "o", cfg1) != compute_merge_input_hash("t", "o", cfg2)


def test_compute_merge_input_hash_changes_on_group_minutes() -> None:
    cfg1 = MergeConfig(window_seconds=15.0, group_minutes=5)
    cfg2 = MergeConfig(window_seconds=15.0, group_minutes=15)
    assert compute_merge_input_hash("t", "o", cfg1) != compute_merge_input_hash("t", "o", cfg2)


def test_compute_merge_input_hash_none_uses_sentinel() -> None:
    """None e string vazia devem produzir hashes diferentes."""
    h_none = compute_merge_input_hash(None, "ocr", _DEFAULT_CFG)
    h_empty = compute_merge_input_hash("", "ocr", _DEFAULT_CFG)
    assert h_none != h_empty


def test_compute_merge_input_hash_both_none() -> None:
    h = compute_merge_input_hash(None, None, _DEFAULT_CFG)
    assert isinstance(h, str) and len(h) == 64  # SHA256 hex


def test_merge_config_group_minutes_zero_raises() -> None:
    with pytest.raises(ValidationError):
        MergeConfig(window_seconds=15.0, group_minutes=0)


# ── Section 6: parse functions ────────────────────────────────────────────────


def test_parse_transcript_segments_valid() -> None:
    segs = parse_transcript_segments(FAKE_TRANSCRIPT_JSON)
    assert len(segs) == 1
    assert segs[0].start == 0.0
    assert segs[0].text == "Olá, vamos começar."


def test_parse_transcript_segments_invalid_raises() -> None:
    with pytest.raises(ValidationError):
        parse_transcript_segments('{"not": "a list"}')


def test_parse_transcript_segments_wrong_schema_raises() -> None:
    # Lista de objetos com campos errados
    with pytest.raises(ValidationError):
        parse_transcript_segments(json.dumps([{"x": 1}]))


def test_parse_ocr_results_valid() -> None:
    results = parse_ocr_results(FAKE_OCR_JSON)
    assert len(results) == 1
    assert results[0].timestamp == "00:00:05"
    assert results[0].screen_type == "vscode"


def test_parse_ocr_results_invalid_raises() -> None:
    with pytest.raises(ValidationError):
        parse_ocr_results("not json at all")


def test_parse_ocr_results_wrong_schema_raises() -> None:
    with pytest.raises(ValidationError):
        parse_ocr_results(json.dumps([{"nope": True}]))


# ── Section 7: write_merge_md ─────────────────────────────────────────────────


def test_write_merge_md_creates_file(tmp_path: Path) -> None:
    write_merge_md(tmp_path, "# conteúdo\n")
    assert (tmp_path / MERGE_MD_FILENAME).exists()
    assert (tmp_path / MERGE_MD_FILENAME).read_text(encoding="utf-8") == "# conteúdo\n"


def test_write_merge_md_atomic_no_tmp_left(tmp_path: Path) -> None:
    write_merge_md(tmp_path, "# conteúdo\n")
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"arquivo .tmp deixado no disco: {tmp_files}"


def test_write_merge_md_overwrites_existing(tmp_path: Path) -> None:
    write_merge_md(tmp_path, "versão 1\n")
    write_merge_md(tmp_path, "versão 2\n")
    assert (tmp_path / MERGE_MD_FILENAME).read_text(encoding="utf-8") == "versão 2\n"


# ── Section 8: checkpoint functions ──────────────────────────────────────────


def test_needs_merge_processing_no_log_returns_true(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    assert needs_merge_processing(lesson, "any_hash") is True


def test_needs_merge_processing_done_returns_false(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    # Escrever arquivo de output + log com hash correto
    merge_hash = compute_merge_input_hash(FAKE_TRANSCRIPT_JSON, FAKE_OCR_JSON, _DEFAULT_CFG)
    write_merge_md(lesson.output_dir, "# ok\n")
    record_skipped_merge(lesson, merge_hash, datetime.now())
    assert needs_merge_processing(lesson, merge_hash) is False


def test_needs_merge_processing_hash_mismatch_returns_true(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    write_merge_md(lesson.output_dir, "# ok\n")
    record_skipped_merge(lesson, "old_hash", datetime.now())
    assert needs_merge_processing(lesson, "new_hash") is True


def test_needs_merge_processing_file_absent_returns_true(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    merge_hash = compute_merge_input_hash(FAKE_TRANSCRIPT_JSON, FAKE_OCR_JSON, _DEFAULT_CFG)
    # Log diz que está feito, mas o arquivo não existe no disco
    record_skipped_merge(lesson, merge_hash, datetime.now())
    assert needs_merge_processing(lesson, merge_hash) is True


def test_needs_merge_processing_force_returns_true(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    merge_hash = compute_merge_input_hash(FAKE_TRANSCRIPT_JSON, FAKE_OCR_JSON, _DEFAULT_CFG)
    write_merge_md(lesson.output_dir, "# ok\n")
    record_skipped_merge(lesson, merge_hash, datetime.now())
    assert needs_merge_processing(lesson, merge_hash, force=True) is True


def test_record_skipped_merge_logs_entry(course_dir: Path, output_root: Path) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    entry = record_skipped_merge(lesson, "abc123", datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    assert log.latest(MERGE_STEP) is not None
    assert log.latest(MERGE_STEP).source_hash == "abc123"  # type: ignore[union-attr]


def test_record_merge_skipped_no_inputs_logs_entry(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    entry = record_merge_skipped_no_inputs(lesson, datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert "Fases 2" in (entry.message or "")


def test_record_merge_skipped_disabled_logs_entry(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    entry = record_merge_skipped_disabled(lesson, datetime.now())
    assert entry.status == Status.SKIPPED_UNCHANGED
    assert "merge.enabled" in (entry.message or "")


def test_process_lesson_merge_completes_and_writes_file(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    merge_hash = compute_merge_input_hash(FAKE_TRANSCRIPT_JSON, FAKE_OCR_JSON, _DEFAULT_CFG)

    content, entry = process_lesson_merge(
        lesson, merge_hash, FAKE_TRANSCRIPT_JSON, FAKE_OCR_JSON, _DEFAULT_CFG
    )

    assert entry.status == Status.COMPLETED
    assert entry.source_hash == merge_hash
    merge_file = lesson.output_dir / MERGE_MD_FILENAME
    assert merge_file.exists()
    assert "[Falado]" in merge_file.read_text(encoding="utf-8")


def test_process_lesson_merge_partial_transcript_only(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    merge_hash = compute_merge_input_hash(FAKE_TRANSCRIPT_JSON, None, _DEFAULT_CFG)

    content, entry = process_lesson_merge(
        lesson, merge_hash, FAKE_TRANSCRIPT_JSON, None, _DEFAULT_CFG
    )

    assert entry.status == Status.COMPLETED
    assert "OCR disponível: **Não**" in content


def test_process_lesson_merge_invalid_transcript_raises(
    course_dir: Path, output_root: Path
) -> None:
    """Arquivo existente mas inválido deve causar falha real (não skip)."""
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValidationError):
        process_lesson_merge(lesson, "any", "INVALID JSON", None, _DEFAULT_CFG)


def test_process_lesson_merge_invalid_ocr_raises(
    course_dir: Path, output_root: Path
) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValidationError):
        process_lesson_merge(lesson, "any", None, '{"not": "a list"}', _DEFAULT_CFG)


def test_process_lesson_merge_logs_step(course_dir: Path, output_root: Path) -> None:
    course = discover_course(course_dir, output_root)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True, exist_ok=True)
    merge_hash = compute_merge_input_hash(FAKE_TRANSCRIPT_JSON, None, _DEFAULT_CFG)

    process_lesson_merge(lesson, merge_hash, FAKE_TRANSCRIPT_JSON, None, _DEFAULT_CFG)

    log = read_processing_log(lesson.output_dir / PROCESSING_LOG_FILENAME, lesson.slug)
    entry = log.latest(MERGE_STEP)
    assert entry is not None
    assert entry.status == Status.COMPLETED
    assert entry.source_hash == merge_hash


# ── Section 9: CLI integration ────────────────────────────────────────────────


def _write_config_with_merge(
    tmp_path: Path, output_root: Path, merge_enabled: bool = True
) -> Path:
    config_file = tmp_path / "aulaforge.yaml"
    config_file.write_text(
        f'project:\n  output_dir: "{output_root.as_posix()}"\n'
        f"merge:\n  enabled: {str(merge_enabled).lower()}\n",
        encoding="utf-8",
    )
    return config_file


class _FakeWhisperModel:
    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, object]:
        return {
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "ola"},
                {"start": 5.0, "end": 10.0, "text": "mundo"},
            ]
        }


def _fake_extract_audio(video_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"fake-audio")
    return output_path


@pytest.fixture
def mock_merge_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks mínimos para que foundation + transcrição funcionem sem FFmpeg/Whisper.
    Notes e Notion ficam desabilitados (não há mock para eles).
    """
    monkeypatch.setattr(cli_module, "check_transcription_dependencies", lambda: [])
    monkeypatch.setattr("aulaforge.checkpoints.extract_audio", _fake_extract_audio)
    monkeypatch.setattr(cli_module, "load_whisper_model", lambda _: _FakeWhisperModel())
    # Notes/Notion/OCR — reportar como dependência ausente (não falha real)
    monkeypatch.setattr(
        cli_module, "check_ollama_dependencies", lambda *_: ["Ollama ausente (mock)"]
    )


def test_cli_merge_generates_output_file(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_merge_success: None,
) -> None:
    config_file = _write_config_with_merge(tmp_path, output_root, merge_enabled=True)
    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    # Pode sair com código 2 (dep ausente: Ollama) mas não deve ter traceback
    assert result.exit_code in (0, 2), result.output
    course_output = output_root / course_dir.name
    for lesson_dir in [p for p in course_output.iterdir() if p.is_dir()]:
        # Transcrição gerou 02_TRANSCRICAO_COM_TIMESTAMPS.json → merge deve rodar
        if (lesson_dir / "02_TRANSCRICAO_COM_TIMESTAMPS.json").exists():
            assert (lesson_dir / MERGE_MD_FILENAME).exists(), (
                f"08_MERGE_AUDIO_VIDEO.md esperado em {lesson_dir}"
            )


def test_cli_merge_skipped_on_second_run(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_merge_success: None,
) -> None:
    config_file = _write_config_with_merge(tmp_path, output_root, merge_enabled=True)
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code in (0, 2), result.output
    # Segunda execução deve reportar etapas puladas
    assert "pulada" in result.output


def test_cli_merge_skipped_no_inputs(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando nenhuma fase upstream rodou, merge deve registrar SKIPPED_UNCHANGED."""
    config_file = _write_config_with_merge(tmp_path, output_root, merge_enabled=True)
    # Forçar falha na transcrição para que nenhum JSON de entrada exista
    monkeypatch.setattr(
        cli_module,
        "check_transcription_dependencies",
        lambda: ["ffmpeg ausente (mock)"],
    )

    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code == 2, result.output  # dep ausente
    course_output = output_root / course_dir.name
    for lesson_dir in [p for p in course_output.iterdir() if p.is_dir()]:
        # Sem transcrição e sem OCR, merge deve ser skipped (não falha)
        log_path = lesson_dir / PROCESSING_LOG_FILENAME
        if log_path.exists():
            import json as _json

            log = _json.loads(log_path.read_text(encoding="utf-8"))
            merge_entries = [s for s in log.get("steps", []) if s.get("step") == MERGE_STEP]
            if merge_entries:
                assert merge_entries[-1]["status"] == "skipped_unchanged"


def test_cli_merge_disabled_in_config_skipped(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_merge_success: None,
) -> None:
    """merge.enabled=false deve registrar step merge como skipped."""
    config_file = _write_config_with_merge(tmp_path, output_root, merge_enabled=False)
    result = runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    assert result.exit_code in (0, 2), result.output
    course_output = output_root / course_dir.name
    for lesson_dir in [p for p in course_output.iterdir() if p.is_dir()]:
        log_path = lesson_dir / PROCESSING_LOG_FILENAME
        if log_path.exists():
            import json as _json

            log = _json.loads(log_path.read_text(encoding="utf-8"))
            merge_entries = [s for s in log.get("steps", []) if s.get("step") == MERGE_STEP]
            if merge_entries:
                assert merge_entries[-1]["status"] == "skipped_unchanged"
            assert not (lesson_dir / MERGE_MD_FILENAME).exists()


def test_cli_merge_continues_after_invalid_json(
    course_dir: Path,
    output_root: Path,
    tmp_path: Path,
    mock_merge_success: None,
) -> None:
    """JSON corrompido → step merge FAILED nessa aula → batch continua → outras aulas OK.

    O segundo run não usa --force: a transcrição é pulada (vídeo inalterado, log
    diz COMPLETED, arquivo existe no disco — mesmo que corrompido), então o arquivo
    inválido permanece até o passo merge tentar lê-lo e falhar com ValidationError.
    """
    config_file = _write_config_with_merge(tmp_path, output_root, merge_enabled=True)
    # Primeiro run normal — cria transcrições e merge para todas as aulas
    runner.invoke(app, ["process-course", str(course_dir), "--config", str(config_file)])

    course_output = output_root / course_dir.name
    lesson_dirs = sorted(p for p in course_output.iterdir() if p.is_dir())
    if not lesson_dirs:
        return

    ts_file = lesson_dirs[0] / "02_TRANSCRICAO_COM_TIMESTAMPS.json"
    if not ts_file.exists():
        return  # precondição: transcrição deve existir após o primeiro run

    # Corromper o JSON e apagar o merge da primeira aula
    ts_file.write_text("INVALID JSON", encoding="utf-8")
    merge_file_0 = lesson_dirs[0] / MERGE_MD_FILENAME
    merge_file_0.unlink(missing_ok=True)

    # Segundo run SEM --force:
    # - transcrição é pulada (needs_transcription_processing → False)
    # - arquivo corrompido permanece no disco
    # - merge detecta hash diferente (conteúdo mudou) e tenta rodar
    # - parse_transcript_segments("INVALID JSON") → ValidationError → FAILED
    # - continue_on_error=true → batch segue para as outras aulas
    result = runner.invoke(
        app,
        ["process-course", str(course_dir), "--config", str(config_file)],
    )

    # Falha de processamento real (exit 1), não apenas ausência de dependência (exit 2)
    assert result.exit_code == 1, result.output
    # A primeira aula não deve ter merge (falhou e o arquivo foi apagado antes do run)
    assert not merge_file_0.exists()
    # As outras aulas não são afetadas
    for lesson_dir in lesson_dirs[1:]:
        if (lesson_dir / "02_TRANSCRICAO_COM_TIMESTAMPS.json").exists():
            assert (lesson_dir / MERGE_MD_FILENAME).exists()
