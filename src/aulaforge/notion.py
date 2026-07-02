"""Sync Phase 3 lesson notes to Notion via direct REST API calls.

Reads only `09_ANOTACAO_NOTION.md` per lesson (never raw transcripts, audio,
screenshots or OCR files) and creates/updates one Notion page per course,
with each lesson as a Toggle Heading 1 block. No MCP protocol, no Ollama
calls — this module is pure orchestration over `notion_client`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aulaforge import notion_client
from aulaforge.config import NotionConfig
from aulaforge.models import Course, Lesson, NotionLessonInfo, NotionPageInfo
from aulaforge.notes import NOTE_MIN_CHARS, NOTES_FILENAME

logger = logging.getLogger("aulaforge.notion")

NOTION_PAGE_INFO_FILENAME = "NOTION_PAGE_INFO.json"

# Bump whenever the Markdown->blocks conversion or page/toggle structure
# changes meaningfully, so previously-synced content is detected as stale
# and resynced even if the note file's own content did not change.
NOTION_SYNC_VERSION = "v1"

_MAX_RICH_TEXT_CHARS = 2000
_MAX_CHILDREN_PER_REQUEST = 100

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_DIVIDER_RE = re.compile(r"^-{3,}\s*$")
_ITALIC_LINE_RE = re.compile(r"^_(.+)_$")


@dataclass
class NotionAvailability:
    """Result of checking whether a Notion sync can run this batch.

    `errors` empty means `token` and `database_id` are both populated and
    usable. Non-empty `errors` is treated by the caller as a missing
    dependency (exit code 2), not a processing failure.
    """

    errors: list[str] = field(default_factory=list)
    token: str | None = None
    database_id: str | None = None


# ---------------------------------------------------------------------------
# Dependency / availability check
# ---------------------------------------------------------------------------


def check_notion_dependencies(cfg: NotionConfig) -> NotionAvailability:
    """Resolve a usable token + database_id, or return actionable errors.

    Order: env var present -> token accepted by Notion -> database resolved
    (by `cfg.database_id` if set, else by searching for `cfg.database_name`).
    Each step short-circuits the next so we never call the API with a token
    we already know is invalid.
    """
    token = os.environ.get(cfg.token_env_var)
    if not token:
        return NotionAvailability(
            errors=[
                f"Variavel de ambiente {cfg.token_env_var} nao definida. Crie uma "
                "integracao em https://www.notion.so/my-integrations e defina "
                f"{cfg.token_env_var} com o token secreto antes de rodar a Fase 4."
            ]
        )

    if not notion_client.is_token_valid(token, cfg.base_url, cfg.api_version, cfg.request_timeout):
        return NotionAvailability(
            errors=[
                f"Token Notion invalido ou sem permissao (variavel {cfg.token_env_var}). "
                "Gere um novo token da integracao em https://www.notion.so/my-integrations."
            ],
            token=token,
        )

    if cfg.database_id:
        database = notion_client.get_database(
            token, cfg.database_id, cfg.base_url, cfg.api_version, cfg.request_timeout
        )
        if database is None:
            return NotionAvailability(
                errors=[
                    f"Database '{cfg.database_id}' (notion.database_id) nao encontrada ou "
                    "nao compartilhada com a integracao. Compartilhe o database com a "
                    "integracao no Notion (... > Connections) ou corrija notion.database_id."
                ],
                token=token,
            )
        return NotionAvailability(errors=[], token=token, database_id=cfg.database_id)

    database = notion_client.find_database_by_name(
        token, cfg.database_name, cfg.base_url, cfg.api_version, cfg.request_timeout
    )
    if database is None:
        return NotionAvailability(
            errors=[
                f"Database '{cfg.database_name}' nao encontrada no workspace Notion (ou nao "
                "compartilhada com a integracao). Crie o database e compartilhe-o com a "
                "integracao, ou defina notion.database_id na config apontando para ele."
            ],
            token=token,
        )
    return NotionAvailability(errors=[], token=token, database_id=str(database["id"]))


# ---------------------------------------------------------------------------
# Local inputs / hashing
# ---------------------------------------------------------------------------


def get_note_for_sync(lesson: Lesson) -> str | None:
    """Read the Phase 3 lesson note — the only file Phase 4 ever reads.

    Returns None if `09_ANOTACAO_NOTION.md` doesn't exist yet (Phase 3
    hasn't run or failed for this lesson), so callers can skip without
    treating it as a Notion-step failure.

    Raises RuntimeError when the file exists but contains less than
    NOTE_MIN_CHARS of useful content — empty notes must not be synced.
    """
    note_path = lesson.output_dir / NOTES_FILENAME
    if not note_path.exists():
        return None
    content = note_path.read_text(encoding="utf-8")
    if len(content.strip()) < NOTE_MIN_CHARS:
        raise RuntimeError(
            "Anotacao esta vazia ou curta demais; gere novamente a etapa "
            "notes antes de sincronizar com o Notion."
        )
    return content


def compute_notion_input_hash(note_content: str, database_ref: str) -> str:
    """SHA256 over everything that affects what gets written to Notion.

    Changing the note content, switching the target database, or bumping
    NOTION_SYNC_VERSION (when the block-mapping/page structure changes) all
    produce a different hash, automatically invalidating the cached sync.
    """
    components = ":".join([NOTION_SYNC_VERSION, database_ref, note_content])
    return hashlib.sha256(components.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# NOTION_PAGE_INFO.json persistence
# ---------------------------------------------------------------------------


def read_notion_page_info(course_output_path: Path) -> NotionPageInfo | None:
    path = course_output_path / NOTION_PAGE_INFO_FILENAME
    if not path.exists():
        return None
    return NotionPageInfo.model_validate_json(path.read_text(encoding="utf-8"))


def write_notion_page_info(course_output_path: Path, info: NotionPageInfo) -> None:
    """Write NOTION_PAGE_INFO.json atomically (.tmp then os.replace)."""
    course_output_path.mkdir(parents=True, exist_ok=True)
    path = course_output_path / NOTION_PAGE_INFO_FILENAME
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(info.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Markdown -> Notion blocks
# ---------------------------------------------------------------------------


def _rich_text(text: str, italic: bool = False) -> list[dict[str, Any]]:
    """Split `text` into <=2000-char segments (Notion's per-rich-text limit)."""
    if not text:
        return [{"type": "text", "text": {"content": ""}}]
    step = _MAX_RICH_TEXT_CHARS
    segments = [text[i : i + step] for i in range(0, len(text), step)]
    result: list[dict[str, Any]] = []
    for segment in segments:
        item: dict[str, Any] = {"type": "text", "text": {"content": segment}}
        if italic:
            item["annotations"] = {"italic": True}
        result.append(item)
    return result


def _paragraph_block(text: str, italic: bool = False) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text, italic=italic)},
    }


def _heading_block(text: str, level: int) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _rich_text(text)}}


def _quote_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "quote", "quote": {"rich_text": _rich_text(text)}}


def _bulleted_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _numbered_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": _rich_text(text)},
    }


def _divider_block() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _toggle_skeleton_block(title: str, use_heading: bool = True) -> dict[str, Any]:
    if use_heading:
        return {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": _rich_text(title),
                "is_toggleable": True,
                "color": "default",
            },
        }
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {"rich_text": _rich_text(title)},
    }


def markdown_to_notion_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Convert a lesson note's Markdown into Notion block objects.

    Only supports the subset Phase 3's templates actually produce: headings,
    `>` quotes, `-`/`*` bullets, `1.` numbered lists, `---` dividers, and
    `_italic_` lines. Anything else (and any heading level 1, which would
    duplicate the toggle's own title) degrades to a plain paragraph instead
    of raising, per Fase 4 scope.
    """
    blocks: list[dict[str, Any]] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            if level == 1:
                continue
            blocks.append(_heading_block(heading_match.group(2).strip(), level=min(level, 3)))
            continue

        if _DIVIDER_RE.match(line):
            blocks.append(_divider_block())
            continue

        quote_match = _QUOTE_RE.match(line)
        if quote_match:
            blocks.append(_quote_block(quote_match.group(1).strip()))
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            blocks.append(_bulleted_block(bullet_match.group(1).strip()))
            continue

        numbered_match = _NUMBERED_RE.match(line)
        if numbered_match:
            blocks.append(_numbered_block(numbered_match.group(1).strip()))
            continue

        italic_match = _ITALIC_LINE_RE.match(line)
        if italic_match:
            blocks.append(_paragraph_block(italic_match.group(1).strip(), italic=True))
            continue

        blocks.append(_paragraph_block(line))

    return blocks


def chunk_blocks(
    blocks: list[dict[str, Any]], size: int = _MAX_CHILDREN_PER_REQUEST
) -> list[list[dict[str, Any]]]:
    """Split `blocks` into chunks of at most `size` (Notion's 100-children-per-request limit)."""
    step = max(1, size)
    return [blocks[i : i + step] for i in range(0, len(blocks), step)]


# ---------------------------------------------------------------------------
# Course page / lesson toggle orchestration
# ---------------------------------------------------------------------------


def _lesson_toggle_title(lesson: Lesson) -> str:
    if lesson.number is not None:
        return f"Aula {lesson.number} — {lesson.title}"
    return lesson.title


def _course_page_properties(course: Course) -> dict[str, Any]:
    """Minimal, safely-derivable properties only.

    Aggregate fields (Categoria, Tema principal, Duracao total, Aulas
    processadas, checkboxes) need cross-lesson analysis that belongs to a
    later phase, per the approved Fase 4 scope — left at their database
    defaults here.
    """
    return {
        "Name": {"title": [{"text": {"content": course.name}}]},
        "Pasta local": {"rich_text": [{"text": {"content": str(course.output_path)}}]},
        "Último processamento": {"date": {"start": datetime.now().date().isoformat()}},
    }


def _course_page_skeleton_blocks() -> list[dict[str, Any]]:
    """Empty top-level headings from NOTION_PAGE_TEMPLATE.md, written once at creation.

    Their content (course overview, lesson map, ...) needs aggregation logic
    out of Fase 4 scope, and is never regenerated on later runs so a future
    phase (or manual edits) filling them in is never clobbered.
    """
    headings = [
        "Visão Geral do Curso",
        "Mapa das Aulas",
        "Principais Conceitos",
        "Projetos Possíveis",
        "Agentes Sugeridos",
        "Skills Sugeridas",
        "Prompts Prontos",
    ]
    blocks: list[dict[str, Any]] = [_heading_block(h, level=2) for h in headings]
    blocks.append(_divider_block())
    return blocks


def _find_toggle_block_id(
    token: str, cfg: NotionConfig, course_page_id: str, title: str
) -> str | None:
    block_type = "heading_1" if cfg.lesson_blocks_as_toggle_h1 else "toggle"
    children = notion_client.list_block_children(
        token, course_page_id, cfg.base_url, cfg.api_version, cfg.request_timeout, cfg.max_retries
    )
    for block in children:
        if block.get("type") != block_type:
            continue
        rich_text = block.get(block_type, {}).get("rich_text", [])
        text = "".join(str(part.get("plain_text", "")) for part in rich_text)
        if text.strip() == title.strip():
            block_id = block.get("id")
            return str(block_id) if block_id is not None else None
    return None


def _resolve_course_page(
    course: Course, cfg: NotionConfig, token: str, database_id: str
) -> NotionPageInfo:
    """Find-or-create the course page, trusting NOTION_PAGE_INFO.json first.

    Local cache is the primary source of truth (no network call needed when
    it already points at the right database); a remote title search is only
    a fallback for the first run or a lost/stale local cache.
    """
    existing = read_notion_page_info(course.output_path)
    if existing is not None and existing.database_id == database_id:
        return existing

    remote = notion_client.find_page_by_title(
        token, database_id, course.name, cfg.base_url, cfg.api_version, cfg.request_timeout
    )
    if remote is not None:
        info = NotionPageInfo(
            course_page_id=str(remote["id"]),
            course_page_url=str(remote.get("url", "")),
            database_id=database_id,
            lessons=existing.lessons if existing is not None else {},
        )
    else:
        created = notion_client.create_page(
            token,
            database_id,
            _course_page_properties(course),
            _course_page_skeleton_blocks(),
            cfg.base_url,
            cfg.api_version,
            cfg.request_timeout,
            cfg.max_retries,
        )
        info = NotionPageInfo(
            course_page_id=str(created["id"]),
            course_page_url=str(created.get("url", "")),
            database_id=database_id,
            lessons={},
        )

    write_notion_page_info(course.output_path, info)
    return info


def _resolve_lesson_toggle(
    token: str, cfg: NotionConfig, course_page_id: str, lesson: Lesson, page_info: NotionPageInfo
) -> tuple[str, bool]:
    """Return (toggle_block_id, is_new_block)."""
    existing = page_info.lessons.get(lesson.slug)
    if existing is not None:
        return existing.toggle_block_id, False

    title = _lesson_toggle_title(lesson)
    found_id = _find_toggle_block_id(token, cfg, course_page_id, title)
    if found_id is not None:
        return found_id, False

    result = notion_client.append_block_children(
        token,
        course_page_id,
        [_toggle_skeleton_block(title, use_heading=cfg.lesson_blocks_as_toggle_h1)],
        cfg.base_url,
        cfg.api_version,
        cfg.request_timeout,
        cfg.max_retries,
    )
    results_list = result.get("results", [])
    if not results_list or "id" not in results_list[0]:
        raise notion_client.NotionAPIError(
            "Notion nao retornou o ID do toggle criado na pagina do curso."
        )
    new_id = str(results_list[0]["id"])
    return new_id, True


def _replace_toggle_children(
    token: str,
    cfg: NotionConfig,
    toggle_id: str,
    content_blocks: list[dict[str, Any]],
    is_new: bool,
) -> None:
    """Append the fresh content before deleting the stale content.

    This ordering means the toggle is never empty even if the process is
    interrupted mid-update — worst case it briefly has both old and new
    content, never neither.
    """
    old_children_ids: list[str] = []
    if not is_new:
        old_children = notion_client.list_block_children(
            token, toggle_id, cfg.base_url, cfg.api_version, cfg.request_timeout, cfg.max_retries
        )
        old_children_ids = [str(block["id"]) for block in old_children]

    for chunk in chunk_blocks(content_blocks):
        notion_client.append_block_children(
            token, toggle_id, chunk,
            cfg.base_url, cfg.api_version, cfg.request_timeout, cfg.max_retries,
        )

    for block_id in old_children_ids:
        notion_client.delete_block(
            token, block_id, cfg.base_url, cfg.api_version, cfg.request_timeout, cfg.max_retries
        )


def sync_lesson_to_notion(
    course: Course,
    lesson: Lesson,
    note_content: str,
    notion_hash: str,
    cfg: NotionConfig,
    token: str,
    database_id: str,
) -> tuple[NotionPageInfo, str]:
    """Ensure the course page and this lesson's toggle exist and are current.

    Persists NOTION_PAGE_INFO.json before returning. Returns the updated
    page info and the toggle_block_id that was created/updated.
    """
    page_info = _resolve_course_page(course, cfg, token, database_id)
    course_page_id = page_info.course_page_id
    toggle_id, is_new = _resolve_lesson_toggle(token, cfg, course_page_id, lesson, page_info)

    content_blocks = markdown_to_notion_blocks(note_content)
    _replace_toggle_children(token, cfg, toggle_id, content_blocks, is_new)

    page_info.lessons[lesson.slug] = NotionLessonInfo(
        toggle_block_id=toggle_id, synced_hash=notion_hash
    )
    write_notion_page_info(course.output_path, page_info)
    return page_info, toggle_id
