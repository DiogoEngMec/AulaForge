"""HTTP client for the local Ollama REST API.

Provides availability checks and a `generate_note` function that calls
`/api/chat` with retry and strips qwen3 thinking-mode tags from responses.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger("aulaforge.ollama_client")


def strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks emitted by qwen3 in thinking mode."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def is_ollama_available(base_url: str, timeout: float = 5.0) -> bool:
    """Return True if the Ollama server responds at `base_url`."""
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=timeout)
        return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return False


def is_model_available(model_name: str, base_url: str) -> bool:
    """Return True if `model_name` appears in Ollama's local model registry."""
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=10.0)
        if response.status_code != 200:
            return False
        models: list[dict[str, object]] = response.json().get("models", [])
        return any(str(m.get("name", "")).startswith(model_name) for m in models)
    except Exception:  # noqa: BLE001
        return False


def check_ollama_dependencies(base_url: str, model_name: str) -> list[str]:
    """Return a list of human-readable dependency errors, or [] if everything is OK."""
    if not is_ollama_available(base_url):
        return [
            f"Ollama nao esta rodando em {base_url}. "
            "Inicie com: ollama serve"
        ]
    if not is_model_available(model_name, base_url):
        return [
            f"Modelo '{model_name}' nao disponivel no Ollama. "
            f"Execute: ollama pull {model_name}"
        ]
    return []


def generate_note(
    system_prompt: str,
    user_message: str,
    model: str,
    temperature: float,
    base_url: str,
    max_retries: int = 3,
) -> str:
    """POST to /api/chat and return the assistant's text content.

    `max_retries` is the total number of attempts (1 = no retry).
    Strips <think>...</think> blocks from the response automatically.
    Raises RuntimeError if all attempts fail.
    """
    total_attempts = max(1, max_retries)
    last_exc: Exception | None = None
    for attempt in range(total_attempts):
        try:
            response = httpx.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=600.0,
            )
            response.raise_for_status()
            content: str = response.json().get("message", {}).get("content", "")
            return strip_thinking_tags(content)
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < total_attempts - 1:
                logger.warning(
                    "Ollama falhou (tentativa %d/%d): %s. Tentando novamente...",
                    attempt + 1,
                    total_attempts,
                    exc,
                )
    raise RuntimeError(
        f"Ollama falhou apos {total_attempts} tentativa(s): {last_exc}"
    ) from last_exc
