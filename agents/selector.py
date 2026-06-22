"""
Selector — bewertet generierte Video-Konzepte und wählt die besten zum Upload.

Kernidee (Stufe 3): Lieber mehr Videos generieren als hochladen und nur die mit
dem höchsten Potenzial posten. Erfolg = VIEWS, und die hängen an zwei Signalen:
  1. Verweildauer (wie lange schauen Zuschauer) — der stärkste Algorithmus-Hebel
  2. Like-Rate (wird es geliked)

Der Selector lässt das LLM beides je Konzept VORHERSAGEN, gestützt auf:
  🧠 eigene Erfahrung (bisherige Videos: echte Retention/Likes)  — höchste Priorität
  🌍 externe Signale (Fremdvideos: Views/Like-Rate aus Research) — ergänzend

Eigene Watch-Time gibt es erst mit der Zeit; anfangs zählen v.a. externe Signale.
"""

from __future__ import annotations

import json
from loguru import logger
from config.llm import LLMClient
from config.settings import (
    POTENTIAL_THRESHOLD, VIDEOS_UPLOADED_MIN, VIDEOS_UPLOADED_MAX,
)
from agents.memory_agent import MemoryAgent


class Selector:

    def __init__(self):
        self.memory = MemoryAgent()
        self.gemini = LLMClient()

    def evaluate(self, concepts: list[dict]) -> list[dict]:
        """Bewertet jedes Konzept und hängt potential/pred_retention/pred_like_rate an."""
        if not concepts:
            return []

        best     = self.memory.get_best_patterns()
        worst    = self.memory.get_worst_patterns()
        research = self.memory.get_research()
        recent   = self.memory.get_last_n_videos(10)

        # Kompakte Konzept-Liste für den Prompt (nur entscheidungsrelevante Felder).
        slim = [{
            "i":         idx,
            "animal":    c.get("animal"),
            "angle":     c.get("angle"),
            "setting":   c.get("setting"),
            "hook_style": c.get("hook_style"),
            "hook":      c.get("hook_text_a") or c.get("hook"),
            "title":     c.get("title"),
            "hashtags":  c.get("hashtags"),
        } for idx, c in enumerate(concepts)]

        prompt = f"""
Du bist ein YouTube-Shorts-Performance-Analyst. Bewerte Video-Konzepte für einen
Tier-Kanal und sage für JEDES voraus, wie gut es laufen wird.

Erfolg = Views. Views entstehen aus zwei Signalen:
- VERWEILDAUER (retention): Wie lange schauen Zuschauer? (0-100, stärkster Hebel)
- LIKE-RATE: Wie wahrscheinlich wird es geliked? (0.0-0.10 typisch)

Wissensbasis (gewichte EIGENE Erfahrung höher als externe Trends):
🧠 EIGENE bewährte Muster: {json.dumps(best, ensure_ascii=False)}
🧠 EIGENE Flops (vermeiden): {json.dumps(worst, ensure_ascii=False)}
🧠 Letzte eigene Videos (echte views/likes/avg_view_percentage): {json.dumps(recent, ensure_ascii=False)}
🌍 Externe Beobachtungen (Fremdvideos views/like_rate, Trends): {json.dumps(research, ensure_ascii=False)}

ZU BEWERTENDE KONZEPTE:
{json.dumps(slim, ensure_ascii=False)}

Gib für jedes Konzept (gleiche Reihenfolge, per "i" zugeordnet) zurück:
- pred_retention: 0-100 (erwartete Verweildauer)
- pred_like_rate: 0.0-0.10 (erwartete Like-Rate)
- potential: 0-100 (Gesamt-Potenzial; gewichte Verweildauer am stärksten)
- reason: 1 kurzer Satz

Antworte NUR als JSON-Array:
[{{"i":0,"pred_retention":0,"pred_like_rate":0.0,"potential":0,"reason":"..."}}]
"""
        try:
            text = self.gemini.generate_content(prompt).text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            scores = json.loads(text)
            by_i = {int(s["i"]): s for s in scores if "i" in s}
        except Exception as e:
            logger.error(f"Selector-Bewertung fehlgeschlagen: {e} — neutrale Scores")
            by_i = {}

        for idx, c in enumerate(concepts):
            s = by_i.get(idx, {})
            c["pred_retention"] = float(s.get("pred_retention", 50))
            c["pred_like_rate"] = float(s.get("pred_like_rate", 0.02))
            c["potential"]      = float(s.get("potential", 50))
            c["score_reason"]   = s.get("reason", "(keine Bewertung)")
            logger.info(
                f"📊 {c.get('animal')} | Potenzial {c['potential']:.0f} | "
                f"Retention {c['pred_retention']:.0f} | LikeRate {c['pred_like_rate']:.3f}"
            )
        return concepts

    def select(self, scored: list[dict],
               threshold: float | None = None,
               min_n: int | None = None,
               max_n: int | None = None) -> list[dict]:
        """Wählt adaptiv die besten Konzepte: alle über der Schwelle (max_n gedeckelt),
        aber immer mindestens min_n — egal wie viele 'auf Lager Potenzial haben'."""
        threshold = POTENTIAL_THRESHOLD if threshold is None else threshold
        min_n     = VIDEOS_UPLOADED_MIN if min_n is None else min_n
        max_n     = VIDEOS_UPLOADED_MAX if max_n is None else max_n

        ranked = sorted(scored, key=lambda c: c.get("potential", 0), reverse=True)
        above  = [c for c in ranked if c.get("potential", 0) >= threshold]
        chosen = above[:max_n]
        if len(chosen) < min_n:
            chosen = ranked[:min_n]          # Minimum auffüllen, auch unter Schwelle
        logger.info(
            f"✅ Auswahl: {len(chosen)}/{len(scored)} Videos "
            f"(über Schwelle {threshold}: {len(above)})"
        )
        return chosen
