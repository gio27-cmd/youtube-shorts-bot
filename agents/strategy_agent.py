"""
Strategy Agent — Plant täglich 2 Videos.
Liest Memory + Research und entscheidet was gemacht wird.
Läuft täglich um 06:00 Uhr.
"""

import json
import google.generativeai as genai
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import (
    GEMINI_API_KEY, GEMINI_MODEL,
    HOOK_TEMPLATES, ANIMAL_CATEGORIES,
    UPLOAD_TIME_VIDEO_1, UPLOAD_TIME_VIDEO_2
)
from agents.memory_agent import MemoryAgent


class StrategyAgent:

    def __init__(self):
        self.memory = MemoryAgent()
        genai.configure(api_key=GEMINI_API_KEY)
        self.gemini = genai.GenerativeModel(GEMINI_MODEL)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    def plan_next_videos(self) -> list[dict]:
        logger.info("📊 Strategy Agent: Plane nächste Videos")

        best     = self.memory.get_best_patterns()
        worst    = self.memory.get_worst_patterns()
        research = self.memory.get_research()
        last_10  = self.memory.get_last_n_videos(10)
        ab_results = self.memory.get_all_ab_results()

        prompt = f"""
Du bist ein YouTube Shorts Stratege für einen Tier-Video Kanal.

BEWÄHRTE MUSTER (was viral geht):
{json.dumps(best, ensure_ascii=False)}

ZU VERMEIDEN (was schlecht performt):
{json.dumps(worst, ensure_ascii=False)}

AKTUELLE TRENDS (letzte 6h Research):
{json.dumps(research, ensure_ascii=False)}

LETZTE 10 VIDEOS (Performance):
{json.dumps(last_10, ensure_ascii=False)}

A/B TEST ERGEBNISSE:
{json.dumps(ab_results[-5:] if ab_results else [], ensure_ascii=False)}

Plane EXAKT 2 Videos für heute.
Video 1 → Upload um {UPLOAD_TIME_VIDEO_1} Uhr
Video 2 → Upload um {UPLOAD_TIME_VIDEO_2} Uhr

Für jedes Video:
- animal: Welches Tier (aus bewährten Mustern + aktuellen Trends)
- image_style: Kurze Beschreibung des gewünschten Bilds
- hook_style: "shock" | "question" | "pov" | "fact"
- hook_text_a: Hook-Text Variante A (für A/B Test)
- hook_text_b: Hook-Text Variante B (für A/B Test)
- music_mood: Musik-Stimmung für ACE-Step (keine Vocals, max 20 Wörter)
- upload_time: Uhrzeit
- reasoning: Kurze Begründung mit Daten

Antworte NUR als JSON-Array mit genau 2 Elementen.
"""

        try:
            response = self.gemini.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            plan = json.loads(text)
            if not isinstance(plan, list) or len(plan) != 2:
                raise ValueError("Ungültiges Format")
        except Exception as e:
            logger.error(f"Strategy Gemini error: {e} — nutze Fallback")
            plan = self._fallback_plan()

        self.memory.save_strategy({"videos": plan})
        logger.info(f"✅ Strategie: {[p['animal'] for p in plan]}")
        return plan

    def _fallback_plan(self) -> list[dict]:
        """Sicherer Fallback wenn Gemini nicht verfügbar."""
        best = self.memory.get_best_patterns()
        animal1 = best.get("best_animal", "golden retriever puppy")
        animal2 = "baby panda"
        return [
            {
                "animal": animal1,
                "image_style": f"close-up, natural lighting",
                "hook_style": best.get("best_hook_style", "shock"),
                "hook_text_a": "You won't believe this 😱",
                "hook_text_b": "Wait for it... 🤯",
                "music_mood": "upbeat happy 120bpm no vocals",
                "upload_time": UPLOAD_TIME_VIDEO_1,
                "reasoning": "Fallback: beste historische Muster"
            },
            {
                "animal": animal2,
                "image_style": "cute natural environment",
                "hook_style": "question",
                "hook_text_a": "Can you guess what happens next? 🤔",
                "hook_text_b": "Have you ever seen this? 😍",
                "music_mood": "peaceful nature ambient no vocals",
                "upload_time": UPLOAD_TIME_VIDEO_2,
                "reasoning": "Fallback: sicherer zweiter Slot"
            }
        ]
