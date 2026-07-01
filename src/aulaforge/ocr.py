"""OCR processing for video frames: Tesseract-based local text extraction (Phase 5).

All heavy imports (pytesseract, PIL, cv2) are done lazily inside functions so
this module stays importable even without the ``aulaforge[ocr]`` extras.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from aulaforge.audio import is_ffmpeg_available
from aulaforge.config import OcrConfig
from aulaforge.models import OcrFrameResult

logger = logging.getLogger("aulaforge.ocr")

# ── Output filenames (matching LOCAL_STORAGE_STRUCTURE.md) ───────────────────

OCR_JSON_FILENAME = "04_OCR_TELA.json"
OCR_MD_FILENAME = "05_OCR_TELA.md"
CODES_MD_FILENAME = "06_CODIGOS_DETECTADOS.md"
COMMANDS_MD_FILENAME = "07_COMANDOS_TERMINAL.md"

# ── Hash versioning ───────────────────────────────────────────────────────────

OCR_PROCESSING_VERSION = "v1"

# ── Screen-type heuristics ────────────────────────────────────────────────────

_TERMINAL_PATTERNS = [
    r"^\$\s",
    r"^>\s",
    r"^#\s",
    r"\bsudo\s",
    r"\bnpm\s",
    r"\bpip\s",
    r"\bgit\s",
    r"\bpython\s",
    r"\bnode\s",
    r"\bdocker\s",
    r"^\w+@\w+",
    r"C:\\.*>",
    r"PS\s+\w+.*>",
]

_CODE_PATTERNS = [
    r"\bdef\b",
    r"\bclass\b",
    r"\bimport\b",
    r"\bfrom\b.+\bimport\b",
    r"\bfunction\b",
    r"\bconst\b|\blet\b|\bvar\b",
    r"\bpublic\b|\bprivate\b|\bprotected\b",
    r"\bvoid\b|\bint\b|\bstring\b",
    r"[{}();]",
    r"\breturn\s+",
    r"//\s|/\*",
]

_BROWSER_PATTERNS = [
    r"https?://",
    r"www\.",
]

# Confidence thresholds (chars in stripped text)
_HIGH_CONFIDENCE_MIN = 100
_MEDIUM_CONFIDENCE_MIN = 30


# ── Dependency detection ──────────────────────────────────────────────────────


def is_tesseract_available() -> bool:
    """True if the ``tesseract`` binary is found on PATH."""
    return shutil.which("tesseract") is not None


def is_pytesseract_available() -> bool:
    """True if the ``pytesseract`` Python package is importable."""
    return importlib.util.find_spec("pytesseract") is not None


def is_pillow_available() -> bool:
    """True if ``Pillow`` (PIL) is importable."""
    return importlib.util.find_spec("PIL") is not None


def _check_tesseract_langs(lang: str) -> list[str]:
    """Return error messages for Tesseract language packs that are missing.

    Runs ``tesseract --list-langs`` and compares against the ``+``-separated
    list in *lang* (e.g. ``"por+eng"``).  Returns ``[]`` if the check cannot
    be run (missing binary, subprocess error) — the caller treats this as a
    best-effort check.
    """
    required = {part.strip() for part in lang.split("+") if part.strip()}
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
        available = {
            line.strip()
            for line in output.splitlines()
            if line.strip() and not line.lower().startswith("list")
        }
        missing = required - available
        if missing:
            return [
                f"Idiomas Tesseract ausentes: {', '.join(sorted(missing))}. "
                "Execute: tesseract --list-langs  para ver os disponíveis."
            ]
    except Exception:
        pass
    return []


def check_ocr_dependencies(lang: str = "por+eng") -> list[str]:
    """Return a list of error messages for missing OCR dependencies.

    An empty list means everything required by Phase 5 is present.
    Called lazily in the CLI — only when at least one lesson needs OCR.
    """
    errors: list[str] = []

    if not is_ffmpeg_available():
        errors.append(
            "ffmpeg nao encontrado no PATH. "
            "Instale em https://ffmpeg.org/download.html e adicione ao PATH."
        )
    if not is_tesseract_available():
        errors.append(
            "tesseract nao encontrado no PATH. "
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki"
        )
    if not is_pytesseract_available():
        errors.append(
            "pytesseract nao instalado. Execute: pip install 'aulaforge[ocr]'"
        )
    if not is_pillow_available():
        errors.append(
            "Pillow nao instalado. Execute: pip install 'aulaforge[ocr]'"
        )

    # Best-effort language pack check (only when tesseract binary is present)
    if is_tesseract_available():
        errors.extend(_check_tesseract_langs(lang))

    return errors


# ── Input hash ────────────────────────────────────────────────────────────────


def compute_ocr_input_hash(video_hash: str, cfg: OcrConfig) -> str:
    """Compute a deterministic hash over the video fingerprint + OCR config.

    Any config change that affects OCR output will change this hash and
    trigger reprocessing on the next run.  Bump ``OCR_PROCESSING_VERSION``
    when the OCR implementation changes in a way that would produce different
    results from the same input.
    """
    components = ":".join(
        [
            f"ocr:{OCR_PROCESSING_VERSION}",
            video_hash,
            str(cfg.frame_interval_seconds),
            cfg.lang,
            str(cfg.min_text_change_chars),
            str(int(cfg.save_screenshots_local)),
            str(int(cfg.preprocess_with_opencv)),
            str(int(cfg.detect_code)),
            str(int(cfg.detect_terminal)),
            str(int(cfg.detect_screen_type)),
        ]
    )
    return hashlib.sha256(components.encode()).hexdigest()


# ── Image preprocessing ───────────────────────────────────────────────────────


def _preprocess_image(frame_path: Path) -> object:
    """Preprocess a frame for better OCR quality.

    Uses OpenCV binarisation when available; falls back to a Pillow greyscale
    conversion.  The return value is a PIL Image (or compatible object) that
    pytesseract.image_to_string accepts.

    Isolated so tests can mock it without needing real image files.
    """
    if importlib.util.find_spec("cv2") is not None:
        try:
            import cv2

            img = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                _, binary = cv2.threshold(
                    img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                from PIL import Image

                return Image.fromarray(binary)
        except Exception:
            pass  # fall through to Pillow fallback

    from PIL import Image

    return Image.open(frame_path).convert("L")


# ── Core OCR ──────────────────────────────────────────────────────────────────


def run_ocr(frame_path: Path, lang: str) -> str:
    """Run Tesseract OCR on *frame_path* and return the extracted text.

    Raises ``OcrProcessingError`` if pytesseract or Pillow are not installed,
    or if Tesseract fails on this frame.  The caller should catch this and
    record an empty string so a single bad frame never aborts the batch.
    """
    try:
        import pytesseract
    except ImportError as exc:
        raise OcrProcessingError(
            f"pytesseract nao instalado: {exc}. "
            "Execute: pip install 'aulaforge[ocr]'"
        ) from exc

    try:
        image = _preprocess_image(frame_path)
        text: str = pytesseract.image_to_string(image, lang=lang)
        return text.strip()
    except OcrProcessingError:
        raise
    except Exception as exc:
        raise OcrProcessingError(
            f"Falha ao processar OCR em '{frame_path.name}': {exc}"
        ) from exc


class OcrProcessingError(RuntimeError):
    """Raised when OCR cannot be run on a frame."""


# ── Classification & detection ────────────────────────────────────────────────


def classify_screen_type(text: str) -> str:
    """Classify the type of screen visible in the frame from its OCR text.

    Returns one of: ``"terminal"``, ``"vscode"``, ``"browser"``,
    ``"slides"``, ``"other"``.
    """
    if not text.strip():
        return "other"

    terminal_score = sum(
        1 for p in _TERMINAL_PATTERNS if re.search(p, text, re.MULTILINE)
    )
    code_score = sum(
        1 for p in _CODE_PATTERNS if re.search(p, text, re.MULTILINE)
    )
    browser_score = sum(
        1 for p in _BROWSER_PATTERNS if re.search(p, text)
    )
    # Slides: few short lines, no code/terminal signals
    line_count = len([ln for ln in text.splitlines() if ln.strip()])
    slides_score = (
        1 if 2 <= line_count <= 5 and len(text) < 200 and terminal_score == 0 and code_score == 0
        else 0
    )

    best = max(terminal_score, code_score, browser_score, slides_score)
    if best == 0:
        return "other"
    if terminal_score == best:
        return "terminal"
    if code_score == best:
        return "vscode"
    if browser_score == best:
        return "browser"
    return "slides"


def assess_confidence(text: str) -> str:
    """Assess OCR confidence from text length and apparent coherence."""
    clean = text.strip()
    if len(clean) >= _HIGH_CONFIDENCE_MIN:
        return "high"
    if len(clean) >= _MEDIUM_CONFIDENCE_MIN:
        return "medium"
    return "low"


def detect_code_blocks(text: str) -> str | None:
    """Extract lines that look like source code. Returns None if none found."""
    if not text:
        return None
    code_lines = [
        line
        for line in text.splitlines()
        if any(re.search(p, line) for p in _CODE_PATTERNS)
    ]
    result = "\n".join(code_lines).strip()
    return result if result else None


def detect_terminal_commands(text: str) -> str | None:
    """Extract lines that look like shell commands. Returns None if none found."""
    if not text:
        return None
    cmd_lines = [
        line
        for line in text.splitlines()
        if any(re.search(p, line, re.MULTILINE) for p in _TERMINAL_PATTERNS)
    ]
    result = "\n".join(cmd_lines).strip()
    return result if result else None


# ── Deduplication ─────────────────────────────────────────────────────────────


def _is_important_frame(result: OcrFrameResult) -> bool:
    """True if the frame contains important content that should never be deduped."""
    return bool(
        result.detected_code
        or result.detected_commands
        or result.screen_type == "terminal"
    )


def _text_change_count(prev: str, curr: str) -> int:
    """Count characters in lines that appear in *curr* but not in *prev*."""
    lines_prev = set(prev.strip().splitlines())
    lines_curr = set(curr.strip().splitlines())
    new_lines = lines_curr - lines_prev
    return sum(len(ln) for ln in new_lines)


def dedup_results(
    results: list[OcrFrameResult],
    min_text_change_chars: int,
) -> list[OcrFrameResult]:
    """Remove near-duplicate frames while preserving frames with code/commands.

    A frame is considered a duplicate of the previous kept frame if:
    - it is not an "important" frame (code/commands/terminal), AND
    - the number of new characters vs. the previous kept frame is below
      *min_text_change_chars*.
    """
    if not results:
        return []

    kept: list[OcrFrameResult] = [results[0]]
    last = results[0]

    for result in results[1:]:
        if _is_important_frame(result):
            kept.append(result)
            last = result
            continue

        if _text_change_count(last.text, result.text) >= min_text_change_chars:
            kept.append(result)
            last = result

    return kept


# ── Save policy ───────────────────────────────────────────────────────────────


def _apply_save_policy(
    kept_results: list[OcrFrameResult],
    frames_dir: Path,
    save_screenshots_local: bool,
) -> None:
    """Delete frames from disk according to the save policy.

    If *save_screenshots_local* is False, the entire ``frames/`` directory is
    removed.  Otherwise only frames that did not survive deduplication are
    deleted, keeping one file per entry in *kept_results*.
    """
    if not frames_dir.exists():
        return

    if not save_screenshots_local:
        shutil.rmtree(frames_dir, ignore_errors=True)
        return

    kept_names = {Path(r.frame_path).name for r in kept_results}
    for frame_file in list(frames_dir.glob("*.png")):
        if frame_file.name not in kept_names:
            frame_file.unlink(missing_ok=True)


# ── Output file writers ───────────────────────────────────────────────────────


def _write_atomic(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via a .tmp sibling file."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_ocr_json(output_dir: Path, results: list[OcrFrameResult]) -> Path:
    """Write 04_OCR_TELA.json — the authoritative OCR data source."""
    path = output_dir / OCR_JSON_FILENAME
    content = json.dumps(
        [r.model_dump() for r in results], indent=2, ensure_ascii=False
    )
    _write_atomic(path, content)
    return path


def write_ocr_md(output_dir: Path, results: list[OcrFrameResult]) -> Path:
    """Write 05_OCR_TELA.md — human-readable OCR summary."""
    path = output_dir / OCR_MD_FILENAME
    lines: list[str] = ["# OCR — Texto Detectado no Vídeo", ""]
    if not results:
        lines.append("_Nenhum frame processado._")
    for r in results:
        lines.append(
            f"## [{r.timestamp}] Tela: `{r.screen_type}` | Confiança: `{r.confidence}`"
        )
        if r.text:
            lines.append("")
            lines.append(r.text)
        lines.append("")
    _write_atomic(path, "\n".join(lines))
    return path


def write_codes_md(output_dir: Path, results: list[OcrFrameResult]) -> Path:
    """Write 06_CODIGOS_DETECTADOS.md — extracted code blocks only."""
    path = output_dir / CODES_MD_FILENAME
    lines: list[str] = ["# Códigos Detectados no Vídeo", ""]
    found = False
    for r in results:
        if r.detected_code:
            found = True
            conf_warn = (
                ""
                if r.confidence == "high"
                else (
                    f"\n> ⚠️ Aviso: trecho extraído por OCR com confiança {r.confidence}."
                    " Pode exigir revisão manual."
                )
            )
            lines.append(f"## [{r.timestamp}]{conf_warn}")
            lines.append("")
            lines.append("```")
            lines.append(r.detected_code)
            lines.append("```")
            lines.append("")
    if not found:
        lines.append("_Nenhum código detectado nesta aula._")
    _write_atomic(path, "\n".join(lines))
    return path


def write_commands_md(output_dir: Path, results: list[OcrFrameResult]) -> Path:
    """Write 07_COMANDOS_TERMINAL.md — extracted terminal commands only."""
    path = output_dir / COMMANDS_MD_FILENAME
    lines: list[str] = ["# Comandos de Terminal Detectados", ""]
    found = False
    for r in results:
        if r.detected_commands:
            found = True
            conf_warn = (
                ""
                if r.confidence == "high"
                else (
                    f"\n> ⚠️ Aviso: trecho extraído por OCR com confiança {r.confidence}."
                    " Pode exigir revisão manual."
                )
            )
            lines.append(f"## [{r.timestamp}]{conf_warn}")
            lines.append("")
            lines.append("```bash")
            lines.append(r.detected_commands)
            lines.append("```")
            lines.append("")
    if not found:
        lines.append("_Nenhum comando de terminal detectado nesta aula._")
    _write_atomic(path, "\n".join(lines))
    return path


# ── Main OCR orchestrator ─────────────────────────────────────────────────────


def process_lesson_ocr_frames(
    video_path: Path,
    output_dir: Path,
    cfg: OcrConfig,
) -> list[OcrFrameResult]:
    """Extract frames from *video_path* and run OCR on each one.

    Returns the deduplicated list of ``OcrFrameResult`` objects.  Frame files
    in ``frames/`` are cleaned up according to *cfg.save_screenshots_local*.

    This function does NOT write the JSON/MD output files — the caller
    (``checkpoints.process_lesson_ocr``) does that so the writing and log
    recording remain co-located.
    """
    from aulaforge.video_frames import FRAMES_DIR_NAME, extract_frames

    frames_dir = output_dir / FRAMES_DIR_NAME
    frame_paths = extract_frames(video_path, frames_dir, cfg.frame_interval_seconds)

    results: list[OcrFrameResult] = []
    for frame_path in frame_paths:
        # Convert filename "HH-MM-SS.png" → display timestamp "HH:MM:SS"
        ts_display = frame_path.stem.replace("-", ":")

        try:
            text = run_ocr(frame_path, cfg.lang)
        except OcrProcessingError as exc:
            logger.warning("OCR falhou para frame '%s': %s", frame_path.name, exc)
            text = ""

        screen_type = classify_screen_type(text) if cfg.detect_screen_type else "other"
        confidence = assess_confidence(text)
        detected_code = detect_code_blocks(text) if cfg.detect_code else None
        detected_commands = detect_terminal_commands(text) if cfg.detect_terminal else None

        result = OcrFrameResult(
            timestamp=ts_display,
            frame_path=f"frames/{frame_path.name}",
            screen_type=screen_type,
            text=text,
            detected_code=detected_code,
            detected_commands=detected_commands,
            confidence=confidence,
        )
        results.append(result)
        logger.debug(
            "Frame '%s': tipo=%s conf=%s",
            frame_path.name,
            screen_type,
            confidence,
        )

    deduped = dedup_results(results, cfg.min_text_change_chars)
    logger.info(
        "OCR: %d frame(s) processados → %d apos deduplicacao.",
        len(results),
        len(deduped),
    )

    _apply_save_policy(deduped, frames_dir, cfg.save_screenshots_local)

    return deduped
