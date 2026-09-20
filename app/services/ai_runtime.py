from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class LocalModelRuntime:
    """Adapter for optional local-only LLM endpoints.

    Supported modes deliberately accept loopback URLs only. This keeps the
    local-model feature genuinely local and prevents a misconfigured profile
    from silently sending the ORBIT library to a remote host.
    """

    @staticmethod
    def _endpoint(config: dict[str, Any]) -> tuple[str, str, str, float]:
        provider = str(config.get("provider") or "ollama").strip().casefold()
        endpoint = str(config.get("endpoint") or "http://127.0.0.1:11434").strip().rstrip("/")
        model = str(config.get("model") or "").strip()
        try:
            timeout = max(1.0, min(30.0, float(config.get("timeout_seconds") or 8)))
        except (TypeError, ValueError):
            timeout = 8.0
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or (parsed.hostname or "").casefold() not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("El modelo local debe usar una dirección local (127.0.0.1/localhost).")
        if provider not in {"ollama", "openai-compatible"}:
            raise ValueError("Proveedor de modelo local no compatible.")
        if not model:
            raise ValueError("Configura el nombre del modelo local.")
        return provider, endpoint, model, timeout

    def generate(self, config: dict[str, Any], prompt: str, context: dict[str, Any]) -> str:
        provider, endpoint, model, timeout = self._endpoint(config)
        system = (
            "Eres ORBIT AI, un asistente local para un launcher de videojuegos. "
            "Responde en español de forma breve y útil. Usa únicamente el contexto proporcionado. "
            "No afirmes haber ejecutado acciones ni modifiques archivos."
        )
        context_text = json.dumps(context, ensure_ascii=False, separators=(",", ":"))[:24000]
        if provider == "ollama":
            url = endpoint + "/api/generate"
            body = {
                "model": model,
                "stream": False,
                "prompt": f"{system}\n\nContexto ORBIT:\n{context_text}\n\nUsuario: {prompt}\nORBIT AI:",
                "options": {"temperature": 0.2},
            }
        else:
            url = endpoint + "/v1/chat/completions"
            body = {
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Contexto ORBIT:\n{context_text}\n\nPetición:\n{prompt}"},
                ],
            }
        request = Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "ORBIT/0.6.2"}, method="POST")
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024)
        payload = json.loads(raw.decode("utf-8"))
        if provider == "ollama":
            answer = payload.get("response") if isinstance(payload, dict) else None
        else:
            choices = payload.get("choices") if isinstance(payload, dict) else None
            answer = choices[0].get("message", {}).get("content") if isinstance(choices, list) and choices else None
        text = str(answer or "").strip()
        if not text:
            raise ValueError("El modelo local no devolvió una respuesta utilizable.")
        return text[:12000]


class OnlineSearchRuntime:
    """Optional online lookup kept separate from the offline assistant."""

    def search(self, query: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        language = str(config.get("language") or "es").strip().casefold()
        if not re.fullmatch(r"[a-z]{2,3}", language):
            language = "es"
        q = str(query or "").strip()
        if not q:
            return []
        # MediaWiki search is keyless, documented and returns structured text;
        # it is used only when the user explicitly enables online search.
        url = (
            f"https://{language}.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={quote(q)}&utf8=1&format=json&srlimit=6&origin=*"
        )
        req = Request(url, headers={"User-Agent": "ORBIT/0.6.2 (local launcher)"})
        with urlopen(req, timeout=8) as response:
            raw = response.read(2 * 1024 * 1024)
        payload = json.loads(raw.decode("utf-8"))
        rows = payload.get("query", {}).get("search", []) if isinstance(payload, dict) else []
        results: list[dict[str, Any]] = []
        for row in rows[:6]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            snippet = re.sub(r"<[^>]+>", " ", str(row.get("snippet") or ""))
            snippet = html.unescape(" ".join(snippet.split()))
            if title:
                results.append({
                    "title": title,
                    "snippet": snippet[:500],
                    "url": f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                    "source": "Wikipedia",
                })
        return results
