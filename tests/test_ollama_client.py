"""Tests for aulaforge.ollama_client — httpx is monkeypatched, no real Ollama needed."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

import aulaforge.ollama_client as oc

# ---------------------------------------------------------------------------
# strip_thinking_tags
# ---------------------------------------------------------------------------


def test_strip_thinking_tags_removes_single_block() -> None:
    assert oc.strip_thinking_tags("<think>irrelevant</think>resposta") == "resposta"


def test_strip_thinking_tags_removes_multiline_block() -> None:
    text = "<think>\nmulti\nline\n</think>answer"
    assert oc.strip_thinking_tags(text) == "answer"


def test_strip_thinking_tags_passthrough_when_no_tags() -> None:
    assert oc.strip_thinking_tags("texto normal") == "texto normal"


def test_strip_thinking_tags_strips_surrounding_whitespace() -> None:
    assert oc.strip_thinking_tags("  <think>x</think>  result  ") == "result"


# ---------------------------------------------------------------------------
# is_ollama_available
# ---------------------------------------------------------------------------


def test_is_ollama_available_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = MagicMock()
    resp.status_code = 200
    monkeypatch.setattr(oc.httpx, "get", lambda url, timeout: resp)
    assert oc.is_ollama_available("http://localhost:11434") is True


def test_is_ollama_available_false_on_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float) -> None:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(oc.httpx, "get", boom)
    assert oc.is_ollama_available("http://localhost:11434") is False


def test_is_ollama_available_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float) -> None:
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(oc.httpx, "get", boom)
    assert oc.is_ollama_available("http://localhost:11434") is False


def test_is_ollama_available_false_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = MagicMock()
    resp.status_code = 500
    monkeypatch.setattr(oc.httpx, "get", lambda url, timeout: resp)
    assert oc.is_ollama_available("http://localhost:11434") is False


# ---------------------------------------------------------------------------
# is_model_available
# ---------------------------------------------------------------------------


def _mock_tags_response(models: list[dict[str, str]]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"models": models}
    return resp


def test_is_model_available_true_when_model_in_list(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _mock_tags_response([{"name": "qwen3:30b"}])
    monkeypatch.setattr(oc.httpx, "get", lambda url, timeout: resp)
    assert oc.is_model_available("qwen3:30b", "http://localhost:11434") is True


def test_is_model_available_true_with_variant_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    # "qwen3:30b".startswith("qwen3:30b") is True even for exact match
    resp = _mock_tags_response([{"name": "qwen3:30b-instruct-q4"}])
    monkeypatch.setattr(oc.httpx, "get", lambda url, timeout: resp)
    assert oc.is_model_available("qwen3:30b", "http://localhost:11434") is True


def test_is_model_available_false_when_model_not_in_list(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _mock_tags_response([{"name": "llama3:8b"}])
    monkeypatch.setattr(oc.httpx, "get", lambda url, timeout: resp)
    assert oc.is_model_available("qwen3:30b", "http://localhost:11434") is False


def test_is_model_available_false_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = MagicMock()
    resp.status_code = 503
    monkeypatch.setattr(oc.httpx, "get", lambda url, timeout: resp)
    assert oc.is_model_available("qwen3:30b", "http://localhost:11434") is False


def test_is_model_available_false_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float) -> None:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(oc.httpx, "get", boom)
    assert oc.is_model_available("qwen3:30b", "http://localhost:11434") is False


# ---------------------------------------------------------------------------
# check_ollama_dependencies
# ---------------------------------------------------------------------------


def test_check_ollama_deps_empty_when_both_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oc, "is_ollama_available", lambda base_url: True)
    monkeypatch.setattr(oc, "is_model_available", lambda model, base_url: True)
    assert oc.check_ollama_dependencies("http://localhost:11434", "qwen3:30b") == []


def test_check_ollama_deps_error_when_ollama_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oc, "is_ollama_available", lambda base_url: False)
    errors = oc.check_ollama_dependencies("http://localhost:11434", "qwen3:30b")
    assert len(errors) == 1
    assert "ollama serve" in errors[0].lower()


def test_check_ollama_deps_error_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oc, "is_ollama_available", lambda base_url: True)
    monkeypatch.setattr(oc, "is_model_available", lambda model, base_url: False)
    errors = oc.check_ollama_dependencies("http://localhost:11434", "qwen3:30b")
    assert len(errors) == 1
    assert "qwen3:30b" in errors[0]
    assert "ollama pull" in errors[0].lower()


def test_check_ollama_deps_does_not_check_model_when_ollama_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oc, "is_ollama_available", lambda base_url: False)
    called = {"is_model": False}

    def boom(model: str, base_url: str) -> bool:
        called["is_model"] = True
        return False

    monkeypatch.setattr(oc, "is_model_available", boom)
    oc.check_ollama_dependencies("http://localhost:11434", "qwen3:30b")
    assert not called["is_model"], "is_model_available nao deve ser chamado se Ollama esta off"


# ---------------------------------------------------------------------------
# generate_note
# ---------------------------------------------------------------------------


def _make_fake_post(content: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"message": {"content": content}}
    resp.raise_for_status = MagicMock()
    return resp


def test_generate_note_returns_content_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oc.httpx, "post", lambda url, json, timeout: _make_fake_post("nota gerada")
    )
    result = oc.generate_note("sys", "user", "qwen3:30b", 0.2, "http://localhost:11434")
    assert result == "nota gerada"


def test_generate_note_strips_think_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oc.httpx,
        "post",
        lambda url, json, timeout: _make_fake_post("<think>pensando</think>resposta"),
    )
    result = oc.generate_note("sys", "user", "qwen3:30b", 0.2, "http://localhost:11434")
    assert result == "resposta"


def test_generate_note_sends_no_think_prefix_in_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    def fake_post(url: str, json: dict[str, object], timeout: float) -> MagicMock:
        captured.append(json)
        return _make_fake_post("ok")

    monkeypatch.setattr(oc.httpx, "post", fake_post)
    oc.generate_note("sys", "/no_think\nconteudo", "qwen3:30b", 0.2, "http://localhost:11434")
    messages = captured[0]["messages"]  # type: ignore[index]
    assert isinstance(messages, list)
    user_content = next(m["content"] for m in messages if m["role"] == "user")  # type: ignore[index]
    assert "/no_think" in str(user_content)


def test_generate_note_retries_on_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def flaky_post(url: str, json: dict[str, object], timeout: float) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("timeout")
        return _make_fake_post("ok")

    monkeypatch.setattr(oc.httpx, "post", flaky_post)
    result = oc.generate_note(
        "sys", "user", "qwen3:30b", 0.2, "http://localhost:11434", max_retries=3
    )
    assert result == "ok"
    assert call_count == 3


def test_generate_note_raises_after_all_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(url: str, json: dict[str, object], timeout: float) -> MagicMock:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(oc.httpx, "post", boom)
    with pytest.raises(RuntimeError, match="Ollama falhou"):
        oc.generate_note(
            "sys", "user", "qwen3:30b", 0.2, "http://localhost:11434", max_retries=2
        )


def test_generate_note_attempts_at_least_once_when_max_retries_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """max_retries=0 should still make 1 attempt, not zero."""
    monkeypatch.setattr(
        oc.httpx, "post", lambda url, json, timeout: _make_fake_post("ok")
    )
    result = oc.generate_note(
        "sys", "user", "qwen3:30b", 0.2, "http://localhost:11434", max_retries=0
    )
    assert result == "ok"
