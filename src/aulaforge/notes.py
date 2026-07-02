"""Generate structured Markdown lesson notes using local Ollama.

Reads the clean transcript produced by Phase 2, splits it into chunks when
necessary (never silently truncates), calls Ollama for each chunk, and
consolidates partial notes into the final `09_ANOTACAO_NOTION.md` file.
"""

from __future__ import annotations

import hashlib
import logging
import re

from aulaforge.config import LlmConfig
from aulaforge.models import Lesson
from aulaforge.ollama_client import generate_note
from aulaforge.transcription import CLEAN_TRANSCRIPT_FILENAME, RAW_TRANSCRIPT_FILENAME

logger = logging.getLogger("aulaforge.notes")

NOTES_FILENAME = "09_ANOTACAO_NOTION.md"

# Bump this constant whenever the prompt template changes significantly so that
# notes cached under the previous prompt are automatically regenerated.
NOTES_PROMPT_VERSION = "v1"

# Minimum number of non-whitespace characters required for a note to be valid.
# Responses below this threshold are treated as empty/malformed and trigger retry.
NOTE_MIN_CHARS = 200

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "Voce e um assistente tecnico especializado em documentar aulas de "
    "programacao.\n\n"
    "REGRAS OBRIGATORIAS:\n"
    "1. Use SOMENTE informacoes presentes na transcricao fornecida. Nunca "
    "invente\n"
    "   exemplos, fatos ou conceitos ausentes.\n"
    "2. Se uma secao nao puder ser preenchida com base na transcricao, "
    "escreva\n"
    '   exatamente: "Nao identificado na transcricao."\n'
    "3. Mantenha termos tecnicos em ingles. Escreva em portugues.\n"
    "4. Sugestoes e insights gerados pela IA devem ser precedidos por\n"
    '   "Sugestao:" para distingui-los de conteudo factual.\n'
    "5. Nao adicione informacoes que voce sabe sobre os assuntos mas que "
    "NAO\n"
    "   foram mencionadas na transcricao."
)

_PARTIAL_SYSTEM_PROMPT = (
    "Voce e um assistente tecnico especializado em resumir partes de aulas "
    "de\n"
    "programacao. A transcricao foi dividida em blocos porque e longa.\n"
    "Resuma os pontos principais deste bloco em bullet points, fiel ao "
    "conteudo.\n"
    "Use SOMENTE informacoes presentes neste trecho. Escreva em portugues,\n"
    "termos tecnicos em ingles."
)

_CONSOLIDATION_SYSTEM_PROMPT = (
    "Voce e um assistente tecnico especializado em consolidar resumos de "
    "aulas.\n"
    "Receberae varios resumos parciais (um por bloco) e deve gerar uma unica\n"
    "anotacao estruturada e coerente. Use SOMENTE informacoes presentes nos\n"
    "resumos fornecidos. Nunca invente conteudo. Escreva em portugues,\n"
    'termos tecnicos em ingles. Sugestoes de IA marcadas com "Sugestao:".'
)

_FULL_USER_TEMPLATE = """\
/no_think

Aula: {lesson_title}

TRANSCRICAO DA AULA:
---
{transcript_text}
---

Gere uma anotacao estruturada seguindo exatamente este formato:

# {lesson_title}

> Gerado automaticamente pela Fase 3 (Ollama qwen3) — baseado apenas
> na transcricao. Secoes com "Sugestao:" sao inferencias da IA, nao
> conteudo factual.

## Resumo Executivo
(3-5 frases resumindo o conteudo principal da transcricao)

## Ideia Central
(O conceito mais importante, em 1-2 frases)

## Indice com Timestamps
(Topicos aproximados com base nos blocos de tempo da transcricao)

## Anotacao Estruturada
(Pontos principais em bullet points, ordem cronologica)

## Conceitos Importantes
(Lista de termos e conceitos tecnicos mencionados na transcricao)

## Aplicacoes Praticas
(Como aplicar os conceitos. Inferencias da IA marcadas com "Sugestao:")

## Ideias de Projeto
Sugestao: (ideias inspiradas no conteudo da aula)

## Agentes Sugeridos
Sugestao: (agentes de IA uteis para os conceitos desta aula)

## Skills Sugeridas
Sugestao: (skills de Claude Code relacionadas ao conteudo)

## Prompts Prontos
Sugestao: (2-3 prompts para usar com Claude Code ou Codex)

---
_Codigos Detectados no Video: disponivel na Fase 5 (OCR)._
_Comandos de Terminal: disponivel na Fase 5 (OCR)._"""

_PARTIAL_USER_TEMPLATE = """\
/no_think

Aula: {lesson_title}
Bloco: {block_num}/{total_blocks}

TRANSCRICAO (trecho {block_num} de {total_blocks}):
---
{chunk}
---

Resuma os pontos principais deste trecho em bullet points. Inclua conceitos
tecnicos, exemplos e qualquer informacao relevante mencionada neste bloco."""

_CONSOLIDATION_USER_TEMPLATE = """\
/no_think

Aula: {lesson_title}

Os resumos abaixo cobrem {total_blocks} blocos sequenciais da aula completa.
Consolide-os em uma unica anotacao estruturada e coerente:

{partial_notes_block}

Gere a anotacao final no seguinte formato:

# {lesson_title}

> Gerado automaticamente pela Fase 3 (Ollama qwen3) a partir de
> {total_blocks} blocos. Secoes com "Sugestao:" sao inferencias da IA.

## Resumo Executivo
## Ideia Central
## Indice com Timestamps
## Anotacao Estruturada
## Conceitos Importantes
## Aplicacoes Praticas
## Ideias de Projeto
## Agentes Sugeridos
## Skills Sugeridas
## Prompts Prontos

---
_Codigos Detectados no Video: disponivel na Fase 5 (OCR)._
_Comandos de Terminal: disponivel na Fase 5 (OCR)._"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_note_content(content: str) -> None:
    """Raise RuntimeError when Ollama returned an unusably short response.

    The CLI retry loop catches RuntimeError from process_lesson_notes, so
    raising here activates the existing retry/backoff without any extra
    wiring.
    """
    if len(content.strip()) < NOTE_MIN_CHARS:
        raise RuntimeError(
            f"Anotacao gerada esta vazia ou curta demais "
            f"({len(content.strip())} chars, minimo {NOTE_MIN_CHARS}); "
            "o Ollama pode ter retornado resposta invalida."
        )


def get_transcript_for_notes(lesson: Lesson) -> str | None:
    """Read the best available transcript for this lesson.

    Prefers `03_TRANSCRICAO_LIMPA.md`; falls back to `01_TRANSCRICAO_BRUTA.txt`.
    Returns None if neither exists so callers can handle the missing prerequisite.
    """
    clean_path = lesson.output_dir / CLEAN_TRANSCRIPT_FILENAME
    if clean_path.exists():
        return clean_path.read_text(encoding="utf-8")
    raw_path = lesson.output_dir / RAW_TRANSCRIPT_FILENAME
    if raw_path.exists():
        return raw_path.read_text(encoding="utf-8")
    return None


def compute_notes_input_hash(transcript_text: str, cfg_llm: LlmConfig) -> str:
    """Return a SHA256 hash capturing every input that affects the notes output.

    Any change to the transcript, model, temperature, max_input_chars, or
    NOTES_PROMPT_VERSION (bumped when the prompt template changes significantly)
    will produce a different hash, automatically invalidating cached notes.
    """
    components = ":".join([
        NOTES_PROMPT_VERSION,
        cfg_llm.model,
        str(cfg_llm.temperature),
        str(cfg_llm.max_input_chars),
        transcript_text,
    ])
    return hashlib.sha256(components.encode("utf-8")).hexdigest()


def split_at_block_boundaries(transcript_text: str, max_chars: int) -> list[str]:
    """Split `transcript_text` into chunks of at most `max_chars` characters.

    Only splits at `## Bloco` section boundaries produced by Phase 2, so no
    sentence is cut in the middle. If a single block already exceeds `max_chars`,
    it is kept as its own chunk. Falls back to a single chunk when no headers
    are present.
    """
    if len(transcript_text) <= max_chars:
        return [transcript_text]

    # Keep the "## Bloco" header together with its body by using a lookahead.
    parts = re.split(r"(?=## Bloco )", transcript_text)
    parts = [p for p in parts if p.strip()]

    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                chunks.append(current.strip())
            current = part  # oversized single block gets its own chunk
    if current:
        chunks.append(current.strip())

    return chunks or [transcript_text]


def generate_lesson_note(
    lesson_title: str,
    transcript_text: str,
    cfg_llm: LlmConfig,
) -> str:
    """Generate a structured Markdown note for one lesson.

    Routes to a single Ollama call when the transcript fits within
    `cfg_llm.max_input_chars`, or to a chunked + consolidation path otherwise
    (never silently truncates content).
    """
    chunks = split_at_block_boundaries(transcript_text, cfg_llm.max_input_chars)
    if len(chunks) == 1:
        note = _generate_single(lesson_title, chunks[0], cfg_llm)
    else:
        note = _generate_chunked(lesson_title, chunks, cfg_llm)
    validate_note_content(note)
    return note


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _generate_single(
    lesson_title: str, transcript_text: str, cfg_llm: LlmConfig
) -> str:
    user_msg = _FULL_USER_TEMPLATE.format(
        lesson_title=lesson_title,
        transcript_text=transcript_text,
    )
    return generate_note(
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_msg,
        model=cfg_llm.model,
        temperature=cfg_llm.temperature,
        base_url=cfg_llm.base_url,
        max_retries=cfg_llm.max_retries,
    )


def _generate_chunked(
    lesson_title: str,
    chunks: list[str],
    cfg_llm: LlmConfig,
) -> str:
    total = len(chunks)
    partial_notes: list[str] = []

    for i, chunk in enumerate(chunks, 1):
        logger.info(
            "Aula '%s': gerando nota parcial (bloco %d/%d).", lesson_title, i, total
        )
        user_msg = _PARTIAL_USER_TEMPLATE.format(
            lesson_title=lesson_title,
            block_num=i,
            total_blocks=total,
            chunk=chunk,
        )
        partial = generate_note(
            system_prompt=_PARTIAL_SYSTEM_PROMPT,
            user_message=user_msg,
            model=cfg_llm.model,
            temperature=cfg_llm.temperature,
            base_url=cfg_llm.base_url,
            max_retries=cfg_llm.max_retries,
        )
        partial_notes.append(f"### Bloco {i}\n{partial}")

    logger.info("Aula '%s': consolidando %d blocos.", lesson_title, total)
    partial_notes_block = "\n\n".join(partial_notes)
    consolidation_user_msg = _CONSOLIDATION_USER_TEMPLATE.format(
        lesson_title=lesson_title,
        partial_notes_block=partial_notes_block,
        total_blocks=total,
    )
    return generate_note(
        system_prompt=_CONSOLIDATION_SYSTEM_PROMPT,
        user_message=consolidation_user_msg,
        model=cfg_llm.model,
        temperature=cfg_llm.temperature,
        base_url=cfg_llm.base_url,
        max_retries=cfg_llm.max_retries,
    )
