"""
A/B Tester — Vergleicht Hook-Text Varianten.
Beide Videos bekommen gleichen Inhalt, verschiedene Hook-Texte.
Ergebnis → Memory → zukünftige Strategy nutzt Gewinner.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from loguru import logger
from agents.memory_agent import MemoryAgent
from agents.analytics_agent import AnalyticsAgent


class ABTester:

    def __init__(self):
        self.memory    = MemoryAgent()
        self.analytics = AnalyticsAgent()

    def register_ab_test(
        self,
        video_id_a:    str,
        video_id_b:    str,
        hook_text_a:   str,
        hook_text_b:   str,
        hook_style:    str
    ) -> str:
        test_id = str(uuid.uuid4())[:8]
        self.memory.save_ab_result(test_id, {
            "test_id":     test_id,
            "video_id_a":  video_id_a,
            "video_id_b":  video_id_b,
            "hook_text_a": hook_text_a,
            "hook_text_b": hook_text_b,
            "hook_style":  hook_style,
            "status":      "running",
            "started_at":  datetime.now().isoformat()
        })
        logger.info(f"A/B Test registriert: {test_id}")
        return test_id

    def evaluate_pending_tests(self) -> None:
        """Evaluiert alle laufenden Tests die >48h alt sind."""
        all_results = self.memory.get_all_ab_results()
        now         = datetime.now()

        for result in all_results:
            if result.get("status") != "running":
                continue

            started  = datetime.fromisoformat(result["started_at"])
            if (now - started).total_seconds() < 48 * 3600:
                continue

            # 48 Stunden vorbei → evaluieren
            uploaded_at = started.isoformat()
            analytics_a = self.analytics.get_video_analytics(
                result["video_id_a"], uploaded_at
            )
            analytics_b = self.analytics.get_video_analytics(
                result["video_id_b"], uploaded_at
            )

            views_a = analytics_a.get("views", 0)
            views_b = analytics_b.get("views", 0)

            winner       = "a" if views_a >= views_b else "b"
            winner_hook  = result[f"hook_text_{winner}"]
            uplift       = (
                abs(views_a - views_b) / max(views_b, 1) * 100
            )

            result.update({
                "status":       "completed",
                "winner":       winner,
                "winner_hook":  winner_hook,
                "views_a":      views_a,
                "views_b":      views_b,
                "uplift_pct":   round(uplift, 1),
                "evaluated_at": now.isoformat()
            })

            self.memory.save_ab_result(result["test_id"], result)
            logger.info(
                f"A/B Test {result['test_id']}: "
                f"Gewinner={winner} ({winner_hook}) | "
                f"Views A={views_a} vs B={views_b} | "
                f"Uplift={uplift:.1f}%"
            )

    def get_winning_hook_style(self) -> str | None:
        """Gibt den Hook-Stil zurück der am häufigsten gewinnt."""
        results = [
            r for r in self.memory.get_all_ab_results()
            if r.get("status") == "completed"
        ]
        if not results:
            return None

        winner_styles = [r.get("hook_style") for r in results]
        return max(set(winner_styles), key=winner_styles.count)
