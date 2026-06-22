"""
Strategy Agent — Plant täglich 2 Videos.
Liest Memory + Research und entscheidet was gemacht wird.
Läuft täglich um 06:00 Uhr.
"""

import json
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import (
    HOOK_TEMPLATES, ANIMAL_CATEGORIES,
    UPLOAD_TIME_VIDEO_1, UPLOAD_TIME_VIDEO_2
)
from config.llm import LLMClient
from agents.memory_agent import MemoryAgent


class StrategyAgent:

    def __init__(self):
        self.memory = MemoryAgent()
        # LLMClient: Gemini primär, OpenRouter als Fallback (siehe config/llm.py)
        self.gemini = LLMClient()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    def plan_next_videos(self) -> list[dict]:
        logger.info("📊 Strategy Agent: Plane nächste Videos")

        best     = self.memory.get_best_patterns()
        worst    = self.memory.get_worst_patterns()
        research = self.memory.get_research()
        last_10  = self.memory.get_last_n_videos(10)
        ab_results = self.memory.get_all_ab_results()

        prompt = f"""
Du bist ein datengetriebener YouTube-Shorts-Stratege für einen Tier-Kanal.

Es gibt ZWEI Wissensquellen — gewichte sie BEWUSST:

🧠 EIGENE ERFAHRUNG (höchste Priorität — hat bei UNS nachweislich funktioniert):
- Bewährte Muster (viral): {json.dumps(best, ensure_ascii=False)}
- Zu vermeiden (schlecht gelaufen): {json.dumps(worst, ensure_ascii=False)}
- Letzte 10 Videos (Performance): {json.dumps(last_10, ensure_ascii=False)}
- A/B-Test-Ergebnisse: {json.dumps(ab_results[-5:] if ab_results else [], ensure_ascii=False)}

🌍 EXTERNE BEOBACHTUNGEN (Trends da draußen — nutzen, aber der eigenen Erfahrung unterordnen):
{json.dumps(research, ensure_ascii=False)}

REGEL: Widersprechen sich eigene Erfahrung und externe Trends, folge der EIGENEN
Erfahrung. Gibt es noch keine eigene Erfahrung (Kanal neu), stütze dich auf die
'opportunities' aus den Beobachtungen.

Plane EXAKT 2 Videos für heute.
Video 1 → Upload um {UPLOAD_TIME_VIDEO_1} Uhr
Video 2 → Upload um {UPLOAD_TIME_VIDEO_2} Uhr

Analysiere für jedes Video ALLE Dimensionen:
- animal: Welches Tier
- angle: Erzähl-Winkel/Perspektive
- setting: Ort/Umgebung/Licht
- image_style: Kurze Bildbeschreibung (verbinde angle + setting sinnvoll)
- hook_style: "shock" | "question" | "pov" | "fact"
- hook_text_a: Hook-Text Variante A (für A/B Test)
- hook_text_b: Hook-Text Variante B (für A/B Test)
- hashtags: 3-5 relevante Hashtags (Array)
- music_mood: Musik-Stimmung für ACE-Step (keine Vocals, max 20 Wörter)
- upload_time: Uhrzeit
- reasoning: kurze, datenbasierte Begründung (nenne, ob eher eigene Erfahrung oder Trend ausschlaggebend war)

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
                "angle": "close-up reaction",
                "setting": "soft natural lighting indoors",
                "image_style": "close-up, natural lighting",
                "hook_style": best.get("best_hook_style", "shock"),
                "hook_text_a": "You won't believe this 😱",
                "hook_text_b": "Wait for it... 🤯",
                "hashtags": ["#shorts", "#animals", "#cute"],
                "music_mood": "upbeat happy 120bpm no vocals",
                "upload_time": UPLOAD_TIME_VIDEO_1,
                "reasoning": "Fallback: beste historische Muster"
            },
            {
                "animal": animal2,
                "angle": "playful discovery",
                "setting": "cute natural environment, daylight",
                "image_style": "cute natural environment",
                "hook_style": "question",
                "hook_text_a": "Can you guess what happens next? 🤔",
                "hook_text_b": "Have you ever seen this? 😍",
                "hashtags": ["#shorts", "#wildlife", "#aww"],
                "music_mood": "peaceful nature ambient no vocals",
                "upload_time": UPLOAD_TIME_VIDEO_2,
                "reasoning": "Fallback: sicherer zweiter Slot"
            }
        ]
