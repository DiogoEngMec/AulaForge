"""HTTP client for the Notion REST API (direct integration, no MCP protocol).

Low-level wrapper only: every function takes a token explicitly and knows
nothing about AulaForge's page/toggle conventions (that lives in notion.py).
Mirrors ollama_client.py's shape so it is just as easy to monkeypatch in
tests — plain functions, httpx, simple retry, no client classes/sessions.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("aulaforge.notion_client")


class NotionAPIError(RuntimeError):
    """Raised when a Notion API call fails after retries (network/429/5xx)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers(token: str, api_version: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": api_version,
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    url: str,
    token: str,
    api_version: str,
    timeout: float,
    max_retries: int = 3,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    """Send one Notion API request, retrying transient failures.

    Retries (up to `max_retries` total attempts) on connection/timeout errors
    and on HTTP 429/5xx. Any other status (2xx, or a "real" 4xx like
    400/401/403/404) is returned as-is without retry, so callers branch on
    `response.status_code` themselves instead of catching exceptions for
    expected outcomes like "page not found".
    """
    total_attempts = max(1, max_retries)
    last_exc: Exception | None = None
    last_status: int | None = None
    last_body = ""

    for attempt in range(total_attempts):
        try:
            response = httpx.request(
                method,
                url,
                headers=_headers(token, api_version),
                json=json_body,
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < total_attempts - 1:
                logger.warning(
                    "Notion API falhou (tentativa %d/%d): %s. Tentando novamente...",
                    attempt + 1,
                    total_attempts,
                    exc,
                )
            continue

        if response.status_code == 429 or response.status_code >= 500:
            last_status = response.status_code
            last_body = response.text
            if attempt < total_attempts - 1:
                logger.warning(
                    "Notion API retornou %d (tentativa %d/%d). Tentando novamente...",
                    response.status_code,
                    attempt + 1,
                    total_attempts,
                )
                continue
            break

        return response

    if last_status is not None:
        raise NotionAPIError(
            f"Notion API falhou apos {total_attempts} tentativa(s) "
            f"(status {last_status}): {last_body}",
            status_code=last_status,
        )
    raise NotionAPIError(
        f"Notion API falhou apos {total_attempts} tentativa(s): {last_exc}"
    ) from last_exc


def is_token_valid(token: str, base_url: str, api_version: str, timeout: float) -> bool:
    """Return True if `token` is accepted by Notion (GET /users/me => 200)."""
    try:
        response = httpx.get(
            f"{base_url}/users/me",
            headers=_headers(token, api_version),
            timeout=timeout,
        )
        return response.status_code == 200
    except (httpx.TimeoutException, httpx.RequestError):
        return False


def get_database(
    token: str, database_id: str, base_url: str, api_version: str, timeout: float
) -> dict[str, Any] | None:
    """Return the database object for `database_id`, or None if missing/not shared."""
    try:
        response = httpx.get(
            f"{base_url}/databases/{database_id}",
            headers=_headers(token, api_version),
            timeout=timeout,
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return None
    if response.status_code != 200:
        return None
    data: dict[str, Any] = response.json()
    return data


def find_database_by_name(
    token: str, name: str, base_url: str, api_version: str, timeout: float
) -> dict[str, Any] | None:
    """Search the workspace for a database whose title matches `name` exactly."""
    try:
        response = httpx.post(
            f"{base_url}/search",
            headers=_headers(token, api_version),
            json={"query": name, "filter": {"property": "object", "value": "database"}},
            timeout=timeout,
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return None
    if response.status_code != 200:
        return None
    results: list[dict[str, Any]] = response.json().get("results", [])
    for result in results:
        title_parts = result.get("title", [])
        title_text = "".join(str(part.get("plain_text", "")) for part in title_parts)
        if title_text.strip() == name.strip():
            return result
    return None


def find_page_by_title(
    token: str,
    database_id: str,
    title: str,
    base_url: str,
    api_version: str,
    timeout: float,
) -> dict[str, Any] | None:
    """Query `database_id` for a page whose title property equals `title` exactly."""
    try:
        response = httpx.post(
            f"{base_url}/databases/{database_id}/query",
            headers=_headers(token, api_version),
            json={"filter": {"property": "Name", "title": {"equals": title}}},
            timeout=timeout,
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return None
    if response.status_code != 200:
        return None
    results: list[dict[str, Any]] = response.json().get("results", [])
    return results[0] if results else None


def create_page(
    token: str,
    database_id: str,
    properties: dict[str, Any],
    children: list[dict[str, Any]],
    base_url: str,
    api_version: str,
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    """Create a page as a row of `database_id` with the given properties/body blocks."""
    response = _request(
        "POST",
        f"{base_url}/pages",
        token,
        api_version,
        timeout,
        max_retries,
        json_body={
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": children,
        },
    )
    if response.status_code not in (200, 201):
        raise NotionAPIError(
            f"Falha ao criar pagina no Notion (status {response.status_code}): {response.text}",
            status_code=response.status_code,
        )
    data: dict[str, Any] = response.json()
    return data


def append_block_children(
    token: str,
    block_id: str,
    children: list[dict[str, Any]],
    base_url: str,
    api_version: str,
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    """Append up to 100 child blocks to `block_id`. Caller must chunk larger lists."""
    response = _request(
        "PATCH",
        f"{base_url}/blocks/{block_id}/children",
        token,
        api_version,
        timeout,
        max_retries,
        json_body={"children": children},
    )
    if response.status_code != 200:
        raise NotionAPIError(
            f"Falha ao adicionar blocos no Notion (status {response.status_code}): {response.text}",
            status_code=response.status_code,
        )
    data: dict[str, Any] = response.json()
    return data


def list_block_children(
    token: str,
    block_id: str,
    base_url: str,
    api_version: str,
    timeout: float,
    max_retries: int,
) -> list[dict[str, Any]]:
    """Return every direct child block of `block_id`, paginating as needed."""
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        url = f"{base_url}/blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        response = _request("GET", url, token, api_version, timeout, max_retries)
        if response.status_code != 200:
            raise NotionAPIError(
                "Falha ao listar blocos do Notion"
                f" (status {response.status_code}): {response.text}",
                status_code=response.status_code,
            )
        data = response.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def delete_block(
    token: str,
    block_id: str,
    base_url: str,
    api_version: str,
    timeout: float,
    max_retries: int,
) -> None:
    """Archive/delete a block (Notion's DELETE /blocks/{id})."""
    response = _request(
        "DELETE", f"{base_url}/blocks/{block_id}", token, api_version, timeout, max_retries
    )
    if response.status_code != 200:
        raise NotionAPIError(
            f"Falha ao apagar bloco no Notion (status {response.status_code}): {response.text}",
            status_code=response.status_code,
        )
