"""
Optimizer Agent — Wöchentliche Strategie-Optimierung.
Läuft jeden Sonntag um 23:00 Uhr.
"""

import json
from loguru import logger
from config.llm import LLMClient
from agents.memory_agent import MemoryAgent
from agents.ab_tester import ABTester


class OptimizerAgent:

    def __init__(self):
        self.memory   = MemoryAgent()
        self.ab_tester = ABTester()
        # LLMClient: Gemini primär, OpenRouter als Fallback (siehe config/llm.py)
        self.gemini   = LLMClient()

    def run_weekly_optimization(self) -> dict:
        logger.info("🎯 Optimizer Agent: Wöchentliche Analyse")

        videos      = self.memory.get_last_n_videos(14)
        ab_results  = self.memory.get_all_ab_results()
        best        = self.memory.get_best_patterns()
        worst       = self.memory.get_worst_patterns()

        prompt = f"""
Du bist ein YouTube Analytics Expert für einen Tier-Shorts Kanal.

LETZTE 14 VIDEOS (mit Performance):
{json.dumps(videos, ensure_ascii=False)}

A/B TEST ERGEBNISSE:
{json.dumps(ab_results, ensure_ascii=False)}

BISHERIGE MUSTER:
Gut: {json.dumps(best, ensure_ascii=False)}
Schlecht: {json.dumps(worst, ensure_ascii=False)}

Analysiere und erstelle Empfehlungen für nächste Woche.

Antworte als JSON:
{{
  "top_3_animals": ["tier1", "tier2", "tier3"],
  "best_hook_style": "shock|question|pov|fact",
  "best_upload_time": "HH:MM",
  "best_upload_day": "monday|...|sunday",
  "do_more": ["was mehr machen"],
  "do_less": ["was weniger machen"],
  "insight": "Wichtigste Erkenntnis der Woche",
  "next_week_focus": "Empfehlung für nächste Woche"
}}
"""

        try:
            response = self.gemini.generate_content(prompt)
            text     = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            report = json.loads(text)
        except Exception as e:
            logger.error(f"Optimizer Gemini error: {e}")
            report = {"error": str(e), "insight": "Analyse fehlgeschlagen"}

        self.memory.update_weekly_report(report)
        logger.info(f"✅ Wöchentlicher Report: {report.get('insight', '-')}")
        return report
