"""Merge de timeline: alinha transcrição com OCR por timestamps (Fase 6).

Lê os artefatos JSON já gerados pelas Fases 2 e 5 e produz
08_MERGE_AUDIO_VIDEO.md com a linha do tempo integrada.
Não depende de Whisper, Tesseract, Ollama, FFmpeg ou Notion.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import TypeAdapter

from aulaforge.config import MergeConfig
from aulaforge.models import OcrFrameResult, TranscriptSegment

logger = logging.getLogger("aulaforge.merge")

# ── Output filename (matching LOCAL_STORAGE_STRUCTURE.md) ────────────────────

MERGE_MD_FILENAME = "08_MERGE_AUDIO_VIDEO.md"

# ── Hash versioning ───────────────────────────────────────────────────────────

MERGE_PROCESSING_VERSION = "v1"

# ── TypeAdapters para parsing de listas Pydantic ─────────────────────────────

_TS_ADAPTER: TypeAdapter[list[TranscriptSegment]] = TypeAdapter(list[TranscriptSegment])
_OCR_ADAPTER: TypeAdapter[list[OcrFrameResult]] = TypeAdapter(list[OcrFrameResult])


# ── Hash ──────────────────────────────────────────────────────────────────────


def compute_merge_input_hash(
    transcript_raw: str | None,
    ocr_raw: str | None,
    cfg: MergeConfig,
) -> str:
    """SHA256 do conteúdo dos inputs + parâmetros de configuração que afetam o output."""
    transcript_token = transcript_raw if transcript_raw is not None else "no_transcript"
    ocr_token = ocr_raw if ocr_raw is not None else "no_ocr"
    key = (
        f"merge:{MERGE_PROCESSING_VERSION}:{cfg.window_seconds}:{cfg.group_minutes}:"
        f"{transcript_token}:{ocr_token}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ── Parsing ───────────────────────────────────────────────────────────────────


def parse_transcript_segments(raw: str) -> list[TranscriptSegment]:
    """Parse do conteúdo de 02_TRANSCRICAO_COM_TIMESTAMPS.json.

    Levanta ValidationError/JSONDecodeError se o conteúdo for inválido.
    Nunca retorna None — a ausência do arquivo deve ser detectada antes de chamar
    esta função.
    """
    return _TS_ADAPTER.validate_json(raw)


def parse_ocr_results(raw: str) -> list[OcrFrameResult]:
    """Parse do conteúdo de 04_OCR_TELA.json.

    Levanta ValidationError/JSONDecodeError se o conteúdo for inválido.
    """
    return _OCR_ADAPTER.validate_json(raw)


# ── Helpers de timestamp e formatação ────────────────────────────────────────


def _parse_hms(ts: str) -> float:
    """Converte 'HH:MM:SS' para segundos totais (float)."""
    parts = ts.split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return float(h * 3600 + m * 60 + s)


def _format_time(seconds: float) -> str:
    """Formata segundos como 'HH:MM:SS'."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _ocr_confidence_suffix(confidence: str) -> str:
    if confidence in ("medium", "low"):
        return f" _(confiança: {confidence})_"
    return ""


def _screen_type_lang(screen_type: str) -> str:
    if screen_type == "vscode":
        return "python"
    if screen_type == "terminal":
        return "bash"
    return "text"


# ── Lógica de alinhamento ─────────────────────────────────────────────────────


@dataclass
class MergeBlock:
    """Unidade da linha do tempo unificada: um segmento falado e seus frames OCR associados."""

    time_seconds: float  # chave de ordenação canônica
    transcript_segment: TranscriptSegment | None
    ocr_events: list[tuple[float, OcrFrameResult]] = field(default_factory=list)


def _closest_segment_index(
    ocr_time: float,
    segments: list[TranscriptSegment],
    window_seconds: float,
) -> int | None:
    """Índice do segmento mais próximo do frame OCR dentro da janela, ou None."""
    best_idx: int | None = None
    best_dist = float("inf")
    for i, seg in enumerate(segments):
        if seg.start <= ocr_time <= seg.end:
            dist = 0.0
        elif ocr_time < seg.start:
            dist = seg.start - ocr_time
        else:
            dist = ocr_time - seg.end
        if dist <= window_seconds and dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _build_blocks(
    segments: list[TranscriptSegment] | None,
    ocr_results: list[OcrFrameResult] | None,
    window_seconds: float,
) -> list[MergeBlock]:
    """Constrói a lista ordenada de MergeBlock para uma aula.

    Cada segmento de transcrição vira um bloco; frames OCR são atribuídos ao
    segmento mais próximo dentro de `window_seconds`. Frames sem segmento
    próximo geram blocos standalone.
    """
    # Parsear timestamps OCR; inválidos são descartados com warning
    parsed_ocr: list[tuple[float, OcrFrameResult]] = []
    if ocr_results:
        for ocr in ocr_results:
            try:
                t = _parse_hms(ocr.timestamp)
                parsed_ocr.append((t, ocr))
            except (ValueError, IndexError):
                logger.warning("Timestamp OCR inválido ignorado: %r", ocr.timestamp)

    # Criar um bloco por segmento de transcrição
    seg_blocks: dict[int, MergeBlock] = {}
    if segments:
        for i, seg in enumerate(segments):
            seg_blocks[i] = MergeBlock(
                time_seconds=seg.start,
                transcript_segment=seg,
            )

    # Atribuir cada frame OCR ao segmento mais próximo (ou manter standalone)
    standalone_ocr: list[tuple[float, OcrFrameResult]] = []
    for ocr_time, ocr in parsed_ocr:
        if segments:
            idx = _closest_segment_index(ocr_time, segments, window_seconds)
            if idx is not None:
                seg_blocks[idx].ocr_events.append((ocr_time, ocr))
                continue
        standalone_ocr.append((ocr_time, ocr))

    # Ordenar os eventos OCR dentro de cada bloco por tempo
    for block in seg_blocks.values():
        block.ocr_events.sort(key=lambda x: x[0])

    # Coletar todos os blocos
    blocks: list[MergeBlock] = list(seg_blocks.values())

    # Adicionar frames OCR sem segmento associado como blocos independentes
    for ocr_time, ocr in standalone_ocr:
        blocks.append(MergeBlock(
            time_seconds=ocr_time,
            transcript_segment=None,
            ocr_events=[(ocr_time, ocr)],
        ))

    blocks.sort(key=lambda b: b.time_seconds)
    return blocks


# ── Geração do Markdown ───────────────────────────────────────────────────────


def merge_lesson(
    transcript_segments: list[TranscriptSegment] | None,
    ocr_results: list[OcrFrameResult] | None,
    lesson_title: str,
    cfg: MergeConfig,
) -> str:
    """Gera o conteúdo de 08_MERGE_AUDIO_VIDEO.md para uma aula.

    Funciona em modo parcial (apenas transcrição, ou apenas OCR) indicando
    no cabeçalho o que está disponível.
    """
    has_transcript = bool(transcript_segments)
    has_ocr = bool(ocr_results)

    lines: list[str] = [
        f"# Merge Audio/Vídeo — {lesson_title}",
        "",
        "> Gerado automaticamente por AulaForge.",
        "> Fontes: **transcrição** (Whisper local) e **OCR de tela** (Tesseract local).",
        f"> Transcrição disponível: **{'Sim' if has_transcript else 'Não'}**"
        f" | OCR disponível: **{'Sim' if has_ocr else 'Não'}**",
        "",
        "## Linha do Tempo",
        "",
    ]

    blocks = _build_blocks(transcript_segments, ocr_results, cfg.window_seconds)

    if not blocks:
        lines.append("_Nenhum evento encontrado._")
        return "\n".join(lines) + "\n"

    group_secs = cfg.group_minutes * 60
    current_group = -1

    for block in blocks:
        group = int(block.time_seconds) // group_secs
        if group != current_group:
            current_group = group
            group_start = group * group_secs
            group_end = group_start + group_secs
            lines.append(f"### {_format_time(group_start)} – {_format_time(group_end)}")
            lines.append("")

        # Trecho falado
        if block.transcript_segment:
            seg = block.transcript_segment
            ts_start = _format_time(seg.start)
            ts_end = _format_time(seg.end)
            lines.append(f"**[Falado]** `{ts_start} – {ts_end}`")
            lines.append(f"> {seg.text.strip()}")
            lines.append("")

        # Eventos visuais associados
        for ocr_time, ocr in block.ocr_events:
            ts = _format_time(ocr_time)
            confidence_note = _ocr_confidence_suffix(ocr.confidence)
            screen_label = ocr.screen_type or "other"

            lines.append(f"**[Visual — {screen_label}]** `{ts}`{confidence_note}")

            has_content = False
            if ocr.detected_commands:
                lines.append("```bash")
                lines.append(ocr.detected_commands.strip())
                lines.append("```")
                has_content = True
            if ocr.detected_code:
                lang = _screen_type_lang(ocr.screen_type)
                lines.append(f"```{lang}")
                lines.append(ocr.detected_code.strip())
                lines.append("```")
                has_content = True
            if not has_content and ocr.text:
                lines.append(f"_{ocr.text.strip()}_")

            lines.append("")

    return "\n".join(lines) + "\n"


# ── I/O ───────────────────────────────────────────────────────────────────────


def write_merge_md(output_dir: Path, content: str) -> None:
    """Escrita atômica de 08_MERGE_AUDIO_VIDEO.md via arquivo .tmp + os.replace()."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / MERGE_MD_FILENAME
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
