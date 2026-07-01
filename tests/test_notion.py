"""Tests for aulaforge.notion — notion_client is monkeypatched, no real Notion/network."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import aulaforge.notion as notion_mod
from aulaforge.config import NotionConfig
from aulaforge.models import Course, Lesson, NotionLessonInfo, NotionPageInfo
from aulaforge.notes import NOTES_FILENAME

_CFG = NotionConfig(database_name="Aulas Processadas")


def _make_course(tmp_path: Path, lesson_count: int = 1) -> Course:
    output_path = tmp_path / "output" / "Curso X"
    lessons = []
    for i in range(1, lesson_count + 1):
        lessons.append(
            Lesson(
                number=i,
                title=f"Aula {i}",
                slug=f"aula_{i:02d}",
                video_path=tmp_path / f"video{i}.mp4",
                output_dir=output_path / f"aula_{i:02d}",
            )
        )
    return Course(
        name="Curso X",
        input_path=tmp_path / "Curso X",
        output_path=output_path,
        lessons=lessons,
    )


# ---------------------------------------------------------------------------
# markdown_to_notion_blocks
# ---------------------------------------------------------------------------


def test_markdown_converter_skips_h1_title() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("# Aula 1 — Intro")
    assert blocks == []


def test_markdown_converter_h2_becomes_heading_2() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("## Resumo Executivo")
    assert blocks[0]["type"] == "heading_2"
    content = blocks[0]["heading_2"]["rich_text"][0]["text"]["content"]
    assert content == "Resumo Executivo"


def test_markdown_converter_deep_heading_clamped_to_3() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("##### Muito fundo")
    assert blocks[0]["type"] == "heading_3"


def test_markdown_converter_quote() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("> Gerado automaticamente")
    assert blocks[0]["type"] == "quote"
    content = blocks[0]["quote"]["rich_text"][0]["text"]["content"]
    assert content == "Gerado automaticamente"


def test_markdown_converter_bullet_list() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("- ponto um\n* ponto dois")
    assert [b["type"] for b in blocks] == ["bulleted_list_item", "bulleted_list_item"]


def test_markdown_converter_numbered_list() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("1. primeiro\n2. segundo")
    assert [b["type"] for b in blocks] == ["numbered_list_item", "numbered_list_item"]


def test_markdown_converter_divider() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("---")
    assert blocks[0]["type"] == "divider"


def test_markdown_converter_italic_line() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("_disponivel na Fase 5_")
    assert blocks[0]["type"] == "paragraph"
    assert blocks[0]["paragraph"]["rich_text"][0]["annotations"]["italic"] is True


def test_markdown_converter_plain_paragraph_fallback() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("Texto comum sem marcacao especial.")
    assert blocks[0]["type"] == "paragraph"
    assert "annotations" not in blocks[0]["paragraph"]["rich_text"][0]


def test_markdown_converter_unsupported_syntax_degrades_to_paragraph() -> None:
    # Table syntax is not in the supported subset; must not raise.
    blocks = notion_mod.markdown_to_notion_blocks("| col1 | col2 |")
    assert blocks[0]["type"] == "paragraph"


def test_markdown_converter_skips_blank_lines() -> None:
    blocks = notion_mod.markdown_to_notion_blocks("texto um\n\n\ntexto dois")
    assert len(blocks) == 2


def test_markdown_converter_long_paragraph_splits_rich_text_segments() -> None:
    long_text = "a" * 2500
    blocks = notion_mod.markdown_to_notion_blocks(long_text)
    rich_text = blocks[0]["paragraph"]["rich_text"]
    assert len(rich_text) == 2
    assert len(rich_text[0]["text"]["content"]) == 2000
    assert len(rich_text[1]["text"]["content"]) == 500


# ---------------------------------------------------------------------------
# chunk_blocks
# ---------------------------------------------------------------------------


def test_chunk_blocks_splits_at_100() -> None:
    blocks = [{"i": i} for i in range(250)]
    chunks = notion_mod.chunk_blocks(blocks)
    assert [len(c) for c in chunks] == [100, 100, 50]


def test_chunk_blocks_empty_input_returns_no_chunks() -> None:
    assert notion_mod.chunk_blocks([]) == []


# ---------------------------------------------------------------------------
# compute_notion_input_hash
# ---------------------------------------------------------------------------


def test_notion_input_hash_deterministic() -> None:
    h1 = notion_mod.compute_notion_input_hash("conteudo", "db-1")
    h2 = notion_mod.compute_notion_input_hash("conteudo", "db-1")
    assert h1 == h2


def test_notion_input_hash_changes_with_content() -> None:
    h1 = notion_mod.compute_notion_input_hash("conteudo A", "db-1")
    h2 = notion_mod.compute_notion_input_hash("conteudo B", "db-1")
    assert h1 != h2


def test_notion_input_hash_changes_with_database() -> None:
    h1 = notion_mod.compute_notion_input_hash("conteudo", "db-1")
    h2 = notion_mod.compute_notion_input_hash("conteudo", "db-2")
    assert h1 != h2


# ---------------------------------------------------------------------------
# get_note_for_sync
# ---------------------------------------------------------------------------


def test_get_note_for_sync_returns_none_when_missing(tmp_path: Path) -> None:
    course = _make_course(tmp_path)
    assert notion_mod.get_note_for_sync(course.lessons[0]) is None


def test_get_note_for_sync_reads_existing_file(tmp_path: Path) -> None:
    course = _make_course(tmp_path)
    lesson = course.lessons[0]
    lesson.output_dir.mkdir(parents=True)
    (lesson.output_dir / NOTES_FILENAME).write_text("# Aula 1\nconteudo", encoding="utf-8")
    assert notion_mod.get_note_for_sync(lesson) == "# Aula 1\nconteudo"


# ---------------------------------------------------------------------------
# NOTION_PAGE_INFO.json persistence
# ---------------------------------------------------------------------------


def test_notion_page_info_roundtrip(tmp_path: Path) -> None:
    course_output = tmp_path / "output" / "Curso X"
    lesson_info = NotionLessonInfo(toggle_block_id="block-1", synced_hash="hash-1")
    info = NotionPageInfo(
        course_page_id="page-1",
        course_page_url="https://notion.so/page-1",
        database_id="db-1",
        lessons={"aula_01": lesson_info},
    )
    notion_mod.write_notion_page_info(course_output, info)
    loaded = notion_mod.read_notion_page_info(course_output)
    assert loaded == info
    tmp_file = course_output / (notion_mod.NOTION_PAGE_INFO_FILENAME + ".tmp")
    assert not tmp_file.exists()


def test_notion_page_info_none_when_absent(tmp_path: Path) -> None:
    assert notion_mod.read_notion_page_info(tmp_path / "output" / "Curso X") is None


# ---------------------------------------------------------------------------
# check_notion_dependencies
# ---------------------------------------------------------------------------


def test_check_notion_deps_error_when_token_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    result = notion_mod.check_notion_dependencies(_CFG)
    assert len(result.errors) == 1
    assert "NOTION_TOKEN" in result.errors[0]
    assert result.token is None


def test_check_notion_deps_error_when_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "bad-token")
    monkeypatch.setattr(notion_mod.notion_client, "is_token_valid", lambda *a, **k: False)
    result = notion_mod.check_notion_dependencies(_CFG)
    assert len(result.errors) == 1
    assert result.errors[0]


def test_check_notion_deps_error_when_database_id_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = NotionConfig(database_id="explicit-db-id")
    monkeypatch.setenv("NOTION_TOKEN", "good-token")
    monkeypatch.setattr(notion_mod.notion_client, "is_token_valid", lambda *a, **k: True)
    monkeypatch.setattr(notion_mod.notion_client, "get_database", lambda *a, **k: None)
    result = notion_mod.check_notion_dependencies(cfg)
    assert len(result.errors) == 1
    assert "explicit-db-id" in result.errors[0]


def test_check_notion_deps_ok_with_explicit_database_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = NotionConfig(database_id="explicit-db-id")
    monkeypatch.setenv("NOTION_TOKEN", "good-token")
    monkeypatch.setattr(notion_mod.notion_client, "is_token_valid", lambda *a, **k: True)
    monkeypatch.setattr(
        notion_mod.notion_client,
        "get_database",
        lambda *a, **k: {"id": "explicit-db-id"},
    )
    result = notion_mod.check_notion_dependencies(cfg)
    assert result.errors == []
    assert result.database_id == "explicit-db-id"
    assert result.token == "good-token"


def test_check_notion_deps_error_when_database_name_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "good-token")
    monkeypatch.setattr(notion_mod.notion_client, "is_token_valid", lambda *a, **k: True)
    monkeypatch.setattr(
        notion_mod.notion_client, "find_database_by_name", lambda *a, **k: None
    )
    result = notion_mod.check_notion_dependencies(_CFG)
    assert len(result.errors) == 1
    assert "Aulas Processadas" in result.errors[0]


def test_check_notion_deps_ok_resolves_database_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "good-token")
    monkeypatch.setattr(notion_mod.notion_client, "is_token_valid", lambda *a, **k: True)
    monkeypatch.setattr(
        notion_mod.notion_client,
        "find_database_by_name",
        lambda *a, **k: {"id": "found-db"},
    )
    result = notion_mod.check_notion_dependencies(_CFG)
    assert result.errors == []
    assert result.database_id == "found-db"


# ---------------------------------------------------------------------------
# sync_lesson_to_notion (full orchestration, notion_client mocked)
# ---------------------------------------------------------------------------


def test_sync_creates_course_page_and_new_toggle_when_nothing_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = _make_course(tmp_path)
    lesson = course.lessons[0]

    monkeypatch.setattr(notion_mod.notion_client, "find_page_by_title", lambda *a, **k: None)
    create_page_calls: list[dict[str, Any]] = []

    def fake_create_page(
        token: str, database_id: str, properties: Any, children: Any, *a: Any, **k: Any
    ) -> dict[str, Any]:
        create_page_calls.append({"properties": properties, "children": children})
        return {"id": "page-new", "url": "https://notion.so/page-new"}

    monkeypatch.setattr(notion_mod.notion_client, "create_page", fake_create_page)
    monkeypatch.setattr(
        notion_mod.notion_client,
        "append_block_children",
        lambda token, block_id, children, *a, **k: {"results": [{"id": "toggle-new"}]},
    )
    monkeypatch.setattr(notion_mod.notion_client, "list_block_children", lambda *a, **k: [])
    monkeypatch.setattr(notion_mod.notion_client, "delete_block", lambda *a, **k: None)

    page_info, toggle_id = notion_mod.sync_lesson_to_notion(
        course, lesson, "## Resumo\nconteudo", "hash-1", _CFG, "token", "db-1"
    )

    assert create_page_calls, "create_page deveria ter sido chamado"
    assert page_info.course_page_id == "page-new"
    assert toggle_id == "toggle-new"
    assert page_info.lessons["aula_01"].toggle_block_id == "toggle-new"
    assert page_info.lessons["aula_01"].synced_hash == "hash-1"

    reloaded = notion_mod.read_notion_page_info(course.output_path)
    assert reloaded == page_info


def test_sync_reuses_cached_course_page_without_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = _make_course(tmp_path)
    lesson = course.lessons[0]
    cached = NotionPageInfo(
        course_page_id="page-cached",
        course_page_url="url",
        database_id="db-1",
        lessons={},
    )
    notion_mod.write_notion_page_info(course.output_path, cached)

    monkeypatch.setattr(
        notion_mod.notion_client,
        "find_page_by_title",
        MagicMock(side_effect=AssertionError("nao deveria buscar pagina; cache deve ser usado")),
    )
    monkeypatch.setattr(
        notion_mod.notion_client,
        "create_page",
        MagicMock(side_effect=AssertionError("nao deveria criar pagina")),
    )
    monkeypatch.setattr(notion_mod.notion_client, "list_block_children", lambda *a, **k: [])
    monkeypatch.setattr(
        notion_mod.notion_client,
        "append_block_children",
        lambda token, block_id, children, *a, **k: {"results": [{"id": "toggle-1"}]},
    )
    monkeypatch.setattr(notion_mod.notion_client, "delete_block", lambda *a, **k: None)

    page_info, _toggle_id = notion_mod.sync_lesson_to_notion(
        course, lesson, "conteudo", "hash-1", _CFG, "token", "db-1"
    )
    assert page_info.course_page_id == "page-cached"


def test_sync_updates_existing_toggle_appends_before_deleting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = _make_course(tmp_path)
    lesson = course.lessons[0]
    lesson_info = NotionLessonInfo(toggle_block_id="toggle-1", synced_hash="old-hash")
    cached = NotionPageInfo(
        course_page_id="page-1",
        course_page_url="url",
        database_id="db-1",
        lessons={"aula_01": lesson_info},
    )
    notion_mod.write_notion_page_info(course.output_path, cached)

    call_order: list[str] = []

    monkeypatch.setattr(
        notion_mod.notion_client,
        "list_block_children",
        lambda *a, **k: [{"id": "old-block-1"}, {"id": "old-block-2"}],
    )

    def fake_append(
        token: str, block_id: str, children: Any, *a: Any, **k: Any
    ) -> dict[str, Any]:
        call_order.append("append")
        return {"results": [{"id": "new-block"}]}

    def fake_delete(token: str, block_id: str, *a: Any, **k: Any) -> None:
        call_order.append(f"delete:{block_id}")

    monkeypatch.setattr(notion_mod.notion_client, "append_block_children", fake_append)
    monkeypatch.setattr(notion_mod.notion_client, "delete_block", fake_delete)

    page_info, toggle_id = notion_mod.sync_lesson_to_notion(
        course, lesson, "novo conteudo", "new-hash", _CFG, "token", "db-1"
    )

    assert toggle_id == "toggle-1"  # reused, not recreated
    assert call_order[0] == "append"
    assert call_order[1:] == ["delete:old-block-1", "delete:old-block-2"]
    assert page_info.lessons["aula_01"].synced_hash == "new-hash"


def test_sync_chunks_content_over_100_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = _make_course(tmp_path)
    lesson = course.lessons[0]
    lesson_info = NotionLessonInfo(toggle_block_id="toggle-1", synced_hash="old-hash")
    cached = NotionPageInfo(
        course_page_id="page-1",
        course_page_url="url",
        database_id="db-1",
        lessons={"aula_01": lesson_info},
    )
    notion_mod.write_notion_page_info(course.output_path, cached)

    append_calls: list[int] = []

    def fake_append(
        token: str, block_id: str, children: Any, *a: Any, **k: Any
    ) -> dict[str, Any]:
        append_calls.append(len(children))
        return {"results": [{"id": "new-block"}]}

    monkeypatch.setattr(notion_mod.notion_client, "list_block_children", lambda *a, **k: [])
    monkeypatch.setattr(notion_mod.notion_client, "append_block_children", fake_append)
    monkeypatch.setattr(notion_mod.notion_client, "delete_block", lambda *a, **k: None)

    big_note = "\n".join(f"- item {i}" for i in range(150))
    notion_mod.sync_lesson_to_notion(course, lesson, big_note, "hash-x", _CFG, "token", "db-1")

    assert append_calls == [100, 50]


# ---------------------------------------------------------------------------
# _toggle_skeleton_block (B6: lesson_blocks_as_toggle_h1 respected)
# ---------------------------------------------------------------------------


def test_toggle_skeleton_block_uses_heading_1_by_default() -> None:
    block = notion_mod._toggle_skeleton_block("Aula 1 — Introducao")
    assert block["type"] == "heading_1"
    assert block["heading_1"]["is_toggleable"] is True
    assert block["heading_1"]["rich_text"][0]["text"]["content"] == "Aula 1 — Introducao"


def test_toggle_skeleton_block_uses_plain_toggle_when_use_heading_false() -> None:
    block = notion_mod._toggle_skeleton_block("Aula 1 — Introducao", use_heading=False)
    assert block["type"] == "toggle"
    assert "heading_1" not in block
    assert block["toggle"]["rich_text"][0]["text"]["content"] == "Aula 1 — Introducao"


def test_sync_creates_plain_toggle_block_when_lesson_blocks_as_toggle_h1_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = NotionConfig(database_name="Aulas", lesson_blocks_as_toggle_h1=False)
    course = _make_course(tmp_path)
    lesson = course.lessons[0]

    monkeypatch.setattr(notion_mod.notion_client, "find_page_by_title", lambda *a, **k: None)
    monkeypatch.setattr(
        notion_mod.notion_client,
        "create_page",
        lambda *a, **k: {"id": "page-1", "url": "url"},
    )

    appended_blocks: list[list[Any]] = []

    def fake_append(
        token: str, block_id: str, children: Any, *a: Any, **k: Any
    ) -> dict[str, Any]:
        appended_blocks.append(list(children))
        return {"results": [{"id": "toggle-new"}]}

    monkeypatch.setattr(notion_mod.notion_client, "append_block_children", fake_append)
    monkeypatch.setattr(notion_mod.notion_client, "list_block_children", lambda *a, **k: [])
    monkeypatch.setattr(notion_mod.notion_client, "delete_block", lambda *a, **k: None)

    notion_mod.sync_lesson_to_notion(
        course, lesson, "conteudo da aula", "hash-1", cfg, "token", "db-1"
    )

    # First append_block_children call creates the skeleton block on the course page.
    # With lesson_blocks_as_toggle_h1=False it must be type 'toggle', not 'heading_1'.
    skeleton_call = appended_blocks[0]
    assert len(skeleton_call) == 1
    assert skeleton_call[0]["type"] == "toggle"
    assert "heading_1" not in skeleton_call[0]


# ---------------------------------------------------------------------------
# B1 — guard against empty results from append_block_children
# ---------------------------------------------------------------------------


def test_resolve_lesson_toggle_raises_when_notion_returns_empty_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = _make_course(tmp_path)
    lesson = course.lessons[0]

    monkeypatch.setattr(notion_mod.notion_client, "find_page_by_title", lambda *a, **k: None)
    monkeypatch.setattr(
        notion_mod.notion_client,
        "create_page",
        lambda *a, **k: {"id": "page-1", "url": "url"},
    )
    monkeypatch.setattr(notion_mod.notion_client, "list_block_children", lambda *a, **k: [])
    # Notion returns 200 but with an empty results list — B1 guard must raise clearly.
    monkeypatch.setattr(
        notion_mod.notion_client,
        "append_block_children",
        lambda *a, **k: {"results": []},
    )

    with pytest.raises(notion_mod.notion_client.NotionAPIError, match="toggle criado"):
        notion_mod.sync_lesson_to_notion(
            course, lesson, "conteudo", "hash-1", _CFG, "token", "db-1"
        )
