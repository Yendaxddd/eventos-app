"""Tiny Ollama client for the settings page: which models are installed?"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def base_url(endpoint: str) -> str:
    """'http://localhost:11434/api/generate' -> 'http://localhost:11434'"""
    parts = urlsplit(endpoint.strip() or "http://localhost:11434")
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Dirección no válida: {endpoint!r}")
    return f"{parts.scheme}://{parts.netloc}"


def list_models(endpoint: str, timeout: float = 4.0) -> list[str]:
    """Names of the installed models. Raises ConnectionError with a message fit for the UI."""
    try:
        url = base_url(endpoint) + "/api/tags"
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - user-configured local URL
            data = json.load(response)
    except ValueError as exc:
        raise ConnectionError(str(exc)) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ConnectionError("No se pudo conectar con Ollama. ¿Está abierto?") from exc
    return sorted(m["name"] for m in data.get("models", []) if m.get("name"))
