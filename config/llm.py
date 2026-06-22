"""
Gemeinsamer LLM-Client mit automatischem Fallback.

Reihenfolge: Google Gemini (primär) → OpenRouter (Fallback).

Bietet bewusst dieselbe Schnittstelle wie google.generativeai.GenerativeModel,
damit in den Agents nur die Instanziierung getauscht werden muss:

    from config.llm import LLMClient
    self.gemini = LLMClient()
    text = self.gemini.generate_content(prompt).text

Hintergrund: Der gesamte Bot hing zuvor an einem einzigen Gemini-Key. Sobald
dessen Quota erschöpft war (ResourceExhausted / HTTP 429 / 503), scheiterte u.a.
die Content-Generierung und es kam kein Video zustande. Dieser Client fängt das
ab, indem er bei einem Gemini-Fehler transparent auf OpenRouter ausweicht.
"""

from __future__ import annotations

import requests
from loguru import logger

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)

try:
    import google.generativeai as genai
except Exception:  # google-Lib nicht verfügbar → nur OpenRouter
    genai = None


class _Response:
    """Minimaler Ersatz für die genai-Antwort – die Agents nutzen nur .text."""

    def __init__(self, text: str):
        self.text = text


class LLMClient:
    """Drop-in-Ersatz für genai.GenerativeModel mit OpenRouter-Fallback."""

    def __init__(self, model: str | None = None):
        self._gemini = None
        if genai is not None and GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self._gemini = genai.GenerativeModel(model or GEMINI_MODEL)
            except Exception as e:  # pragma: no cover - Konfig-Fehler
                logger.warning(f"Gemini-Init fehlgeschlagen ({e}) → nur OpenRouter")

    def generate_content(self, prompt: str) -> _Response:
        # 1) Gemini zuerst
        if self._gemini is not None:
            try:
                resp = self._gemini.generate_content(prompt)
                text = getattr(resp, "text", None)
                if text and text.strip():
                    return _Response(text)
                logger.warning("Gemini lieferte leere Antwort → OpenRouter-Fallback")
            except Exception as e:
                logger.warning(
                    f"Gemini-Aufruf fehlgeschlagen ({type(e).__name__}: {e}) "
                    f"→ OpenRouter-Fallback"
                )

        # 2) OpenRouter als Fallback
        return _Response(self._openrouter(prompt))

    def _openrouter(self, prompt: str) -> str:
        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "Gemini nicht verfügbar und kein OpenRouter-Fallback konfiguriert "
                "(OPENROUTER_API_KEY fehlt)."
            )
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                # Optionales Attribution-Header-Paar von OpenRouter:
                "HTTP-Referer": "https://github.com/gio27-cmd/youtube-shorts-bot",
                "X-Title": "Animal Shorts Bot",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                # Deckel nötig: OpenRouter reserviert sonst das volle Output-Budget
                # des Modells (>64k Tokens) und lehnt bei wenig Guthaben mit 402 ab.
                # Unsere Antworten (Skripte/JSON) sind kurz.
                "max_tokens": 2048,
            },
            timeout=120,
        )
        res.raise_for_status()
        data = res.json()
        text = data["choices"][0]["message"]["content"]
        logger.info(f"OpenRouter-Fallback genutzt (Modell {OPENROUTER_MODEL})")
        return text.strip()
