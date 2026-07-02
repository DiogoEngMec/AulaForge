"""Tests for aulaforge.ocr. Never calls real Tesseract or FFmpeg."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import aulaforge.ocr as ocr_module
from aulaforge.config import OcrConfig
from aulaforge.models import OcrFrameResult
from aulaforge.ocr import (
    OcrProcessingError,
    _apply_save_policy,
    _text_change_count,
    assess_confidence,
    check_ocr_dependencies,
    classify_screen_type,
    compute_ocr_input_hash,
    configure_tesseract,
    dedup_results,
    detect_code_blocks,
    detect_terminal_commands,
    is_pillow_available,
    is_pytesseract_available,
    is_tesseract_available,
    resolve_tesseract_cmd,
    run_ocr,
    write_codes_md,
    write_commands_md,
    write_ocr_json,
    write_ocr_md,
)

# ── Availability checks ───────────────────────────────────────────────────────


def test_is_tesseract_available_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_module.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert is_tesseract_available() is True


def test_is_tesseract_available_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_module.shutil, "which", lambda name: None)
    assert is_tesseract_available() is False


def test_is_pytesseract_available_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ocr_module.importlib.util, "find_spec", lambda name: object()
    )
    assert is_pytesseract_available() is True


def test_is_pytesseract_available_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_module.importlib.util, "find_spec", lambda name: None)
    assert is_pytesseract_available() is False


def test_is_pillow_available_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ocr_module.importlib.util, "find_spec", lambda name: object()
    )
    assert is_pillow_available() is True


# ── check_ocr_dependencies ────────────────────────────────────────────────────


def _patch_all_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_module, "is_ffmpeg_available", lambda: True)
    monkeypatch.setattr(ocr_module, "resolve_tesseract_cmd", lambda cfg: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr_module, "is_pytesseract_available", lambda: True)
    monkeypatch.setattr(ocr_module, "is_pillow_available", lambda: True)
    monkeypatch.setattr(ocr_module, "_check_tesseract_langs", lambda lang, cmd="tesseract": [])


def test_check_ocr_dependencies_empty_when_all_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_all_available(monkeypatch)
    assert check_ocr_dependencies() == []


def test_check_ocr_dependencies_reports_missing_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_all_available(monkeypatch)
    monkeypatch.setattr(ocr_module, "is_ffmpeg_available", lambda: False)
    errors = check_ocr_dependencies()
    assert any("ffmpeg" in e for e in errors)


def test_check_ocr_dependencies_reports_missing_tesseract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_all_available(monkeypatch)
    monkeypatch.setattr(ocr_module, "resolve_tesseract_cmd", lambda cfg: None)
    errors = check_ocr_dependencies()
    assert any("tesseract" in e for e in errors)


def test_check_ocr_dependencies_reports_missing_pytesseract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_all_available(monkeypatch)
    monkeypatch.setattr(ocr_module, "is_pytesseract_available", lambda: False)
    errors = check_ocr_dependencies()
    assert any("pytesseract" in e for e in errors)


def test_check_ocr_dependencies_reports_missing_pillow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_all_available(monkeypatch)
    monkeypatch.setattr(ocr_module, "is_pillow_available", lambda: False)
    errors = check_ocr_dependencies()
    assert any("Pillow" in e for e in errors)


def test_check_ocr_dependencies_skips_lang_check_when_tesseract_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lang_check_called = {"called": False}

    def _lang_spy(lang: str, cmd: str = "tesseract") -> list[str]:
        lang_check_called["called"] = True
        return []

    _patch_all_available(monkeypatch)
    monkeypatch.setattr(ocr_module, "resolve_tesseract_cmd", lambda cfg: None)
    monkeypatch.setattr(ocr_module, "_check_tesseract_langs", _lang_spy)
    check_ocr_dependencies()
    assert not lang_check_called["called"]


# ── compute_ocr_input_hash ────────────────────────────────────────────────────


def test_compute_ocr_input_hash_is_deterministic() -> None:
    cfg = OcrConfig()
    h1 = compute_ocr_input_hash("abc123", cfg)
    h2 = compute_ocr_input_hash("abc123", cfg)
    assert h1 == h2


def test_compute_ocr_input_hash_changes_with_video_hash() -> None:
    cfg = OcrConfig()
    assert compute_ocr_input_hash("hash_a", cfg) != compute_ocr_input_hash("hash_b", cfg)


def test_compute_ocr_input_hash_changes_with_interval() -> None:
    cfg1 = OcrConfig(frame_interval_seconds=5)
    cfg2 = OcrConfig(frame_interval_seconds=10)
    assert compute_ocr_input_hash("abc", cfg1) != compute_ocr_input_hash("abc", cfg2)


def test_compute_ocr_input_hash_changes_with_lang() -> None:
    cfg1 = OcrConfig(lang="por+eng")
    cfg2 = OcrConfig(lang="eng")
    assert compute_ocr_input_hash("abc", cfg1) != compute_ocr_input_hash("abc", cfg2)


def test_compute_ocr_input_hash_changes_with_min_text_change_chars() -> None:
    cfg1 = OcrConfig(min_text_change_chars=30)
    cfg2 = OcrConfig(min_text_change_chars=50)
    assert compute_ocr_input_hash("abc", cfg1) != compute_ocr_input_hash("abc", cfg2)


def test_compute_ocr_input_hash_includes_version() -> None:
    cfg = OcrConfig()
    h = compute_ocr_input_hash("abc", cfg)
    assert isinstance(h, str) and len(h) == 64  # SHA256 hex


# ── classify_screen_type ──────────────────────────────────────────────────────


def test_classify_screen_type_terminal_dollar_prompt() -> None:
    assert classify_screen_type("$ git clone https://github.com/foo/bar") == "terminal"


def test_classify_screen_type_terminal_sudo() -> None:
    assert classify_screen_type("sudo apt install python3") == "terminal"


def test_classify_screen_type_vscode_python_def() -> None:
    text = "def my_function(x):\n    return x + 1\n"
    assert classify_screen_type(text) == "vscode"


def test_classify_screen_type_vscode_import() -> None:
    text = "import os\nfrom pathlib import Path\n"
    assert classify_screen_type(text) == "vscode"


def test_classify_screen_type_browser_url() -> None:
    assert classify_screen_type("https://docs.python.org/3/") == "browser"


def test_classify_screen_type_slides_few_lines() -> None:
    assert classify_screen_type("Introdução\nO que é Python?") == "slides"


def test_classify_screen_type_other_when_empty() -> None:
    assert classify_screen_type("") == "other"


def test_classify_screen_type_other_for_random_text() -> None:
    assert classify_screen_type("The quick brown fox jumps") == "other"


# ── assess_confidence ─────────────────────────────────────────────────────────


def test_assess_confidence_high_for_long_text() -> None:
    text = "a" * 100
    assert assess_confidence(text) == "high"


def test_assess_confidence_medium_for_medium_text() -> None:
    text = "a" * 30
    assert assess_confidence(text) == "medium"


def test_assess_confidence_low_for_short_text() -> None:
    assert assess_confidence("abc") == "low"


def test_assess_confidence_low_for_empty() -> None:
    assert assess_confidence("") == "low"


# ── detect_code_blocks ────────────────────────────────────────────────────────


def test_detect_code_blocks_finds_def() -> None:
    text = "def hello():\n    pass\n"
    result = detect_code_blocks(text)
    assert result is not None
    assert "def hello" in result


def test_detect_code_blocks_finds_import() -> None:
    text = "import os\nsome random text\n"
    result = detect_code_blocks(text)
    assert result is not None
    assert "import os" in result


def test_detect_code_blocks_returns_none_for_plain_text() -> None:
    assert detect_code_blocks("The quick brown fox") is None


def test_detect_code_blocks_returns_none_for_empty() -> None:
    assert detect_code_blocks("") is None


# ── detect_terminal_commands ──────────────────────────────────────────────────


def test_detect_terminal_commands_finds_dollar_prompt() -> None:
    text = "$ pip install requests\n"
    result = detect_terminal_commands(text)
    assert result is not None
    assert "pip" in result


def test_detect_terminal_commands_finds_sudo() -> None:
    text = "sudo apt update\n"
    result = detect_terminal_commands(text)
    assert result is not None
    assert "sudo" in result


def test_detect_terminal_commands_returns_none_for_plain_text() -> None:
    assert detect_terminal_commands("Hello world") is None


def test_detect_terminal_commands_returns_none_for_empty() -> None:
    assert detect_terminal_commands("") is None


# ── _text_change_count ────────────────────────────────────────────────────────


def test_text_change_count_identical_texts_is_zero() -> None:
    assert _text_change_count("hello world", "hello world") == 0


def test_text_change_count_completely_different() -> None:
    assert _text_change_count("foo bar", "baz qux") > 0


def test_text_change_count_one_new_line() -> None:
    prev = "line one"
    curr = "line one\nnew line added here"
    count = _text_change_count(prev, curr)
    assert count > 0


# ── dedup_results ─────────────────────────────────────────────────────────────


def _make_result(
    ts: str,
    text: str,
    screen_type: str = "other",
    code: str | None = None,
    commands: str | None = None,
) -> OcrFrameResult:
    return OcrFrameResult(
        timestamp=ts,
        frame_path=f"frames/{ts.replace(':', '-')}.png",
        screen_type=screen_type,
        text=text,
        detected_code=code,
        detected_commands=commands,
        confidence="medium",
    )


def test_dedup_results_keeps_first_frame_always() -> None:
    result = [_make_result("00:00:00", "hello")]
    assert dedup_results(result, 30) == result


def test_dedup_results_removes_near_duplicate() -> None:
    r1 = _make_result("00:00:00", "same text here")
    r2 = _make_result("00:00:05", "same text here")  # identical
    kept = dedup_results([r1, r2], min_text_change_chars=30)
    assert len(kept) == 1
    assert kept[0].timestamp == "00:00:00"


def test_dedup_results_keeps_sufficiently_different_frame() -> None:
    r1 = _make_result("00:00:00", "first slide title")
    r2 = _make_result("00:00:05", "a completely different slide with lots of new text here today")
    kept = dedup_results([r1, r2], min_text_change_chars=10)
    assert len(kept) == 2


def test_dedup_results_never_removes_frame_with_code() -> None:
    r1 = _make_result("00:00:00", "same text")
    r2 = _make_result("00:00:05", "same text", code="def foo(): pass")
    kept = dedup_results([r1, r2], min_text_change_chars=9999)
    assert len(kept) == 2


def test_dedup_results_never_removes_frame_with_commands() -> None:
    r1 = _make_result("00:00:00", "same text")
    r2 = _make_result("00:00:05", "same text", commands="$ git commit -m 'fix'")
    kept = dedup_results([r1, r2], min_text_change_chars=9999)
    assert len(kept) == 2


def test_dedup_results_never_removes_terminal_screen() -> None:
    r1 = _make_result("00:00:00", "same text")
    r2 = _make_result("00:00:05", "same text", screen_type="terminal")
    kept = dedup_results([r1, r2], min_text_change_chars=9999)
    assert len(kept) == 2


def test_dedup_results_empty_input_returns_empty() -> None:
    assert dedup_results([], 30) == []


# ── _apply_save_policy ────────────────────────────────────────────────────────


def test_apply_save_policy_false_removes_frames_dir(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "00-00-00.png").write_bytes(b"img")
    _apply_save_policy([], frames_dir, save_screenshots_local=False)
    assert not frames_dir.exists()


def test_apply_save_policy_true_removes_deduped_frames(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "00-00-00.png").write_bytes(b"keep")
    (frames_dir / "00-00-05.png").write_bytes(b"discard")

    kept = [_make_result("00:00:00", "text")]  # only first frame kept
    _apply_save_policy(kept, frames_dir, save_screenshots_local=True)

    assert (frames_dir / "00-00-00.png").exists()
    assert not (frames_dir / "00-00-05.png").exists()


def test_apply_save_policy_noop_when_frames_dir_absent(tmp_path: Path) -> None:
    # Should not raise even if frames_dir doesn't exist
    _apply_save_policy([], tmp_path / "frames", save_screenshots_local=False)


# ── write_ocr_json ────────────────────────────────────────────────────────────


def test_write_ocr_json_creates_file(tmp_path: Path) -> None:
    results = [_make_result("00:00:00", "hello", code="def f(): pass")]
    path = write_ocr_json(tmp_path, results)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["timestamp"] == "00:00:00"
    assert data[0]["detected_code"] == "def f(): pass"


def test_write_ocr_json_empty_results(tmp_path: Path) -> None:
    path = write_ocr_json(tmp_path, [])
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == []


# ── write_ocr_md ─────────────────────────────────────────────────────────────


def test_write_ocr_md_creates_file(tmp_path: Path) -> None:
    results = [_make_result("00:01:00", "some OCR text")]
    path = write_ocr_md(tmp_path, results)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "00:01:00" in content
    assert "some OCR text" in content


def test_write_ocr_md_empty_results_has_placeholder(tmp_path: Path) -> None:
    path = write_ocr_md(tmp_path, [])
    assert "Nenhum frame" in path.read_text(encoding="utf-8")


# ── write_codes_md ────────────────────────────────────────────────────────────


def test_write_codes_md_includes_code_block(tmp_path: Path) -> None:
    results = [_make_result("00:02:00", "x", code="def foo(): pass")]
    path = write_codes_md(tmp_path, results)
    content = path.read_text(encoding="utf-8")
    assert "def foo(): pass" in content
    assert "00:02:00" in content


def test_write_codes_md_empty_when_no_code(tmp_path: Path) -> None:
    results = [_make_result("00:00:00", "plain text")]
    path = write_codes_md(tmp_path, results)
    assert "Nenhum código" in path.read_text(encoding="utf-8")


def test_write_codes_md_adds_warning_for_low_confidence(tmp_path: Path) -> None:
    r = OcrFrameResult(
        timestamp="00:00:05",
        frame_path="frames/00-00-05.png",
        screen_type="vscode",
        text="def foo(): ...",
        detected_code="def foo(): ...",
        confidence="low",
    )
    path = write_codes_md(tmp_path, [r])
    assert "Aviso" in path.read_text(encoding="utf-8")


# ── write_commands_md ─────────────────────────────────────────────────────────


def test_write_commands_md_includes_command_block(tmp_path: Path) -> None:
    results = [_make_result("00:03:00", "x", commands="$ pip install flask")]
    path = write_commands_md(tmp_path, results)
    content = path.read_text(encoding="utf-8")
    assert "pip install flask" in content
    assert "00:03:00" in content


def test_write_commands_md_empty_when_no_commands(tmp_path: Path) -> None:
    results = [_make_result("00:00:00", "plain")]
    path = write_commands_md(tmp_path, results)
    assert "Nenhum comando" in path.read_text(encoding="utf-8")


# ── run_ocr (mocked pytesseract) ─────────────────────────────────────────────


class _FakePytesseract:
    @staticmethod
    def image_to_string(image: object, lang: str = "") -> str:
        return "  mocked OCR text  "


def test_run_ocr_returns_stripped_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = tmp_path / "00-00-00.png"
    frame.write_bytes(b"fake-png")

    monkeypatch.setattr(ocr_module, "_preprocess_image", lambda p: object())
    import builtins
    real_import = builtins.__import__

    def _mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "pytesseract":
            return _FakePytesseract
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    result = run_ocr(frame, lang="por+eng")
    assert result == "mocked OCR text"


# ── resolve_tesseract_cmd ─────────────────────────────────────────────────────


def test_resolve_tesseract_cmd_uses_explicit_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cfg.tesseract_cmd tem prioridade absoluta sobre PATH e fallbacks."""
    monkeypatch.setattr(ocr_module.shutil, "which", lambda name: "/other/tesseract")
    cfg = OcrConfig(tesseract_cmd="/explicit/path/tesseract.exe")
    assert resolve_tesseract_cmd(cfg) == "/explicit/path/tesseract.exe"


def test_resolve_tesseract_cmd_uses_path_when_no_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem tesseract_cmd na config, usa o binário encontrado no PATH."""
    monkeypatch.setattr(ocr_module.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert resolve_tesseract_cmd(OcrConfig()) == "/usr/bin/tesseract"


def test_resolve_tesseract_cmd_uses_windows_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando PATH não tem tesseract, usa caminhos padrão do Windows se o arquivo existir."""
    fake_binary = tmp_path / "tesseract.exe"
    fake_binary.write_bytes(b"fake")

    monkeypatch.setattr(ocr_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(ocr_module, "_WINDOWS_TESSERACT_FALLBACKS", [str(fake_binary)])

    assert resolve_tesseract_cmd(OcrConfig()) == str(fake_binary)


def test_resolve_tesseract_cmd_returns_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retorna None quando tesseract não está no config, PATH ou fallbacks."""
    monkeypatch.setattr(ocr_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(ocr_module, "_WINDOWS_TESSERACT_FALLBACKS", [])

    assert resolve_tesseract_cmd(OcrConfig()) is None


# ── configure_tesseract ───────────────────────────────────────────────────────


def test_configure_tesseract_raises_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando resolve_tesseract_cmd retorna None, levanta OcrProcessingError."""
    monkeypatch.setattr(ocr_module, "resolve_tesseract_cmd", lambda cfg: None)
    with pytest.raises(OcrProcessingError, match="tesseract"):
        configure_tesseract(OcrConfig())


def test_configure_tesseract_sets_pytesseract_cmd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando resolve retorna um caminho, pytesseract.tesseract_cmd é configurado."""
    import sys
    import types

    fake_inner = types.SimpleNamespace(tesseract_cmd="tesseract")
    fake_pytesseract = types.SimpleNamespace(pytesseract=fake_inner)

    monkeypatch.setattr(ocr_module, "resolve_tesseract_cmd", lambda cfg: "/resolved/tesseract")
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    configure_tesseract(OcrConfig())

    assert fake_inner.tesseract_cmd == "/resolved/tesseract"
