"""Tests for aulaforge.notion_client — httpx is monkeypatched, no real Notion needed."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

import aulaforge.notion_client as nc

_BASE_URL = "https://api.notion.com/v1"
_API_VERSION = "2022-06-28"
_TOKEN = "secret_fake_token"


def _mock_response(status_code: int, json_data: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# is_token_valid
# ---------------------------------------------------------------------------


def test_is_token_valid_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx, "get", lambda url, headers, timeout: _mock_response(200)
    )
    assert nc.is_token_valid(_TOKEN, _BASE_URL, _API_VERSION, 5.0) is True


def test_is_token_valid_false_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx, "get", lambda url, headers, timeout: _mock_response(401)
    )
    assert nc.is_token_valid(_TOKEN, _BASE_URL, _API_VERSION, 5.0) is False


def test_is_token_valid_false_on_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, headers: dict[str, str], timeout: float) -> None:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(nc.httpx, "get", boom)
    assert nc.is_token_valid(_TOKEN, _BASE_URL, _API_VERSION, 5.0) is False


# ---------------------------------------------------------------------------
# get_database
# ---------------------------------------------------------------------------


def test_get_database_returns_payload_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx, "get", lambda url, headers, timeout: _mock_response(200, {"id": "db-1"})
    )
    assert nc.get_database(_TOKEN, "db-1", _BASE_URL, _API_VERSION, 5.0) == {"id": "db-1"}


def test_get_database_none_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx, "get", lambda url, headers, timeout: _mock_response(404)
    )
    assert nc.get_database(_TOKEN, "missing", _BASE_URL, _API_VERSION, 5.0) is None


def test_get_database_none_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, headers: dict[str, str], timeout: float) -> None:
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(nc.httpx, "get", boom)
    assert nc.get_database(_TOKEN, "db-1", _BASE_URL, _API_VERSION, 5.0) is None


# ---------------------------------------------------------------------------
# find_database_by_name
# ---------------------------------------------------------------------------


def test_find_database_by_name_matches_exact_title(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {"id": "db-1", "title": [{"plain_text": "Aulas Processadas"}]},
            {"id": "db-2", "title": [{"plain_text": "Outro Database"}]},
        ]
    }
    monkeypatch.setattr(
        nc.httpx, "post", lambda url, headers, json, timeout: _mock_response(200, payload)
    )
    result = nc.find_database_by_name(_TOKEN, "Aulas Processadas", _BASE_URL, _API_VERSION, 5.0)
    assert result is not None
    assert result["id"] == "db-1"


def test_find_database_by_name_none_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"results": [{"id": "db-2", "title": [{"plain_text": "Outro Database"}]}]}
    monkeypatch.setattr(
        nc.httpx, "post", lambda url, headers, json, timeout: _mock_response(200, payload)
    )
    result = nc.find_database_by_name(_TOKEN, "Aulas Processadas", _BASE_URL, _API_VERSION, 5.0)
    assert result is None


def test_find_database_by_name_none_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx, "post", lambda url, headers, json, timeout: _mock_response(401)
    )
    result = nc.find_database_by_name(_TOKEN, "Aulas Processadas", _BASE_URL, _API_VERSION, 5.0)
    assert result is None


# ---------------------------------------------------------------------------
# find_page_by_title
# ---------------------------------------------------------------------------


def test_find_page_by_title_returns_first_match(monkeypatch: pytest.MonkeyPatch) -> None:
    page = {"id": "page-1", "url": "https://notion.so/page-1"}
    payload = {"results": [page]}
    monkeypatch.setattr(
        nc.httpx, "post", lambda url, headers, json, timeout: _mock_response(200, payload)
    )
    result = nc.find_page_by_title(_TOKEN, "db-1", "Curso X", _BASE_URL, _API_VERSION, 5.0)
    assert result == page


def test_find_page_by_title_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx,
        "post",
        lambda url, headers, json, timeout: _mock_response(200, {"results": []}),
    )
    result = nc.find_page_by_title(_TOKEN, "db-1", "Curso X", _BASE_URL, _API_VERSION, 5.0)
    assert result is None


# ---------------------------------------------------------------------------
# _request retry behavior (exercised through append_block_children / create_page)
# ---------------------------------------------------------------------------


def test_request_retries_on_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def flaky(
        method: str, url: str, headers: dict[str, str], json: Any, timeout: float
    ) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("timeout")
        return _mock_response(200, {"results": [{"id": "block-1"}]})

    monkeypatch.setattr(nc.httpx, "request", flaky)
    result = nc.append_block_children(
        _TOKEN, "block-0", [], _BASE_URL, _API_VERSION, 5.0, max_retries=3
    )
    assert result == {"results": [{"id": "block-1"}]}
    assert call_count == 3


def test_request_retries_on_429_then_raises_after_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        nc.httpx,
        "request",
        lambda method, url, headers, json, timeout: _mock_response(429, text="rate limited"),
    )
    with pytest.raises(nc.NotionAPIError) as exc_info:
        nc.append_block_children(
            _TOKEN, "block-0", [], _BASE_URL, _API_VERSION, 5.0, max_retries=2
        )
    assert exc_info.value.status_code == 429


def test_request_does_not_retry_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def fake(
        method: str, url: str, headers: dict[str, str], json: Any, timeout: float
    ) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return _mock_response(400, text="bad request")

    monkeypatch.setattr(nc.httpx, "request", fake)
    with pytest.raises(nc.NotionAPIError) as exc_info:
        nc.create_page(_TOKEN, "db-1", {}, [], _BASE_URL, _API_VERSION, 5.0, max_retries=3)
    assert exc_info.value.status_code == 400
    assert call_count == 1


# ---------------------------------------------------------------------------
# create_page / append_block_children
# ---------------------------------------------------------------------------


def test_create_page_returns_payload_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    page_payload = {"id": "page-1", "url": "https://notion.so/page-1"}
    monkeypatch.setattr(
        nc.httpx,
        "request",
        lambda method, url, headers, json, timeout: _mock_response(200, page_payload),
    )
    result = nc.create_page(
        _TOKEN, "db-1", {}, [], _BASE_URL, _API_VERSION, 5.0, max_retries=1
    )
    assert result["id"] == "page-1"


def test_append_block_children_returns_payload_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        nc.httpx,
        "request",
        lambda method, url, headers, json, timeout: _mock_response(
            200, {"results": [{"id": "b1"}]}
        ),
    )
    result = nc.append_block_children(
        _TOKEN, "block-1", [{"x": 1}], _BASE_URL, _API_VERSION, 5.0, max_retries=1
    )
    assert result["results"][0]["id"] == "b1"


# ---------------------------------------------------------------------------
# list_block_children (pagination)
# ---------------------------------------------------------------------------


def test_list_block_children_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        {"results": [{"id": "b1"}], "has_more": True, "next_cursor": "cursor-2"},
        {"results": [{"id": "b2"}], "has_more": False, "next_cursor": None},
    ]
    call_count = 0

    def fake(
        method: str, url: str, headers: dict[str, str], json: Any, timeout: float
    ) -> MagicMock:
        nonlocal call_count
        page = pages[call_count]
        call_count += 1
        return _mock_response(200, page)

    monkeypatch.setattr(nc.httpx, "request", fake)
    result = nc.list_block_children(
        _TOKEN, "toggle-1", _BASE_URL, _API_VERSION, 5.0, max_retries=1
    )
    assert [b["id"] for b in result] == ["b1", "b2"]
    assert call_count == 2


def test_list_block_children_raises_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx,
        "request",
        lambda method, url, headers, json, timeout: _mock_response(400, text="bad"),
    )
    with pytest.raises(nc.NotionAPIError):
        nc.list_block_children(
            _TOKEN, "toggle-1", _BASE_URL, _API_VERSION, 5.0, max_retries=1
        )


# ---------------------------------------------------------------------------
# delete_block
# ---------------------------------------------------------------------------


def test_delete_block_succeeds_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx,
        "request",
        lambda method, url, headers, json, timeout: _mock_response(200, {}),
    )
    nc.delete_block(_TOKEN, "block-1", _BASE_URL, _API_VERSION, 5.0, max_retries=1)


def test_delete_block_raises_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nc.httpx,
        "request",
        lambda method, url, headers, json, timeout: _mock_response(404, text="not found"),
    )
    with pytest.raises(nc.NotionAPIError):
        nc.delete_block(_TOKEN, "block-1", _BASE_URL, _API_VERSION, 5.0, max_retries=1)
