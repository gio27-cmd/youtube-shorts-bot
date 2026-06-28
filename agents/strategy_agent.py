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
    UPLOAD_TIME_VIDEO_1, UPLOAD_TIME_VIDEO_2,
    MIN_VIEWS_FOR_SIGNAL, MIN_VIDEOS_FOR_PATTERNS
)
from config.llm import LLMClient
from agents.memory_agent import MemoryAgent


class StrategyAgent:

    def __init__(self):
        self.memory = MemoryAgent()
        # LLMClient: Gemini primär, OpenRouter als Fallback (siehe config/llm.py)
        self.gemini = LLMClient()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    def plan_next_videos(self, count: int = 2) -> list[dict]:
        logger.info(f"📊 Strategy Agent: Plane {count} Video-Kandidaten")

        best     = self.memory.get_best_patterns()
        worst    = self.memory.get_worst_patterns()
        research = self.memory.get_research()
        last_10  = self.memory.get_last_n_videos(10)
        ab_results = self.memory.get_all_ab_results()

        # Statistische Reife des Kanals: Wie viele Videos haben überhaupt genug
        # Reichweite, dass ihre Quoten etwas bedeuten? Erst ab MIN_VIDEOS_FOR_PATTERNS
        # solcher Videos darf die eigene Erfahrung externe Trends überstimmen.
        all_videos    = self.memory.get_all_videos()
        reliable      = [v for v in all_videos
                         if (v.get("views", 0) or 0) >= MIN_VIEWS_FOR_SIGNAL]
        total_views   = sum((v.get("views", 0) or 0) for v in all_videos)
        cold_start    = len(reliable) < MIN_VIDEOS_FOR_PATTERNS

        if cold_start:
            weighting_rule = f"""DATEN-LAGE: COLD-START. Der Kanal hat erst {len(all_videos)} Videos
und nur {len(reliable)} davon mit statistisch belastbarer Reichweite
(>= {MIN_VIEWS_FOR_SIGNAL} Views; gesamt {total_views} Views). Das reicht NICHT, um
zu beurteilen, welches Tier/Format bei UNS funktioniert.

REGEL (Cold-Start): FOLGE DEN EXTERNEN TRENDS / 'opportunities'. Behandle die
internen Quoten (Retention, Like-Rate, "best/worst patterns") als RAUSCHEN und
ignoriere sie als Entscheidungsgrundlage — sie stammen aus winzigen Stichproben.
Überstimme einen starken externen Trend NICHT mit internen Mini-Daten. Eine
Retention nahe oder über 100% ist ein Artefakt, KEIN Erfolgsbeleg. Wähle bewusst
breitere, trendstarke Formate, um überhaupt erst Reichweite und echte Daten
aufzubauen — Nischen-Verengung ist jetzt schädlich."""
        else:
            weighting_rule = f"""DATEN-LAGE: GENUG SIGNAL ({len(reliable)} Videos mit
>= {MIN_VIEWS_FOR_SIGNAL} Views, gesamt {total_views} Views).

REGEL: Jetzt darf die EIGENE Erfahrung externe Trends überstimmen — aber NUR,
soweit sie auf Videos mit echter Reichweite beruht. Quoten aus Videos mit sehr
wenigen Views bleiben Rauschen. Retention >100% ist ein Artefakt, kein Beleg."""

        prompt = f"""
Du bist ein datengetriebener YouTube-Shorts-Stratege für einen Tier-Kanal.

{weighting_rule}

🧠 EIGENE ERFAHRUNG (nur belastbar bei genug Reichweite — siehe DATEN-LAGE oben):
- Bewährte Muster (viral): {json.dumps(best, ensure_ascii=False)}
- Zu vermeiden (schlecht gelaufen): {json.dumps(worst, ensure_ascii=False)}
- Letzte 10 Videos (Performance): {json.dumps(last_10, ensure_ascii=False)}
- A/B-Test-Ergebnisse: {json.dumps(ab_results[-5:] if ab_results else [], ensure_ascii=False)}

🌍 EXTERNE BEOBACHTUNGEN (Trends da draußen):
{json.dumps(research, ensure_ascii=False)}

Plane EXAKT {count} VERSCHIEDENE Video-Kandidaten für heute (Vielfalt bei Tier,
Winkel und Hook). Aus diesen werden später die besten zum Upload ausgewählt.
Verteile sinnvolle Upload-Zeiten über den Tag (z.B. zwischen {UPLOAD_TIME_VIDEO_1}
und {UPLOAD_TIME_VIDEO_2} Uhr).

Analysiere für jedes Video ALLE Dimensionen:
- animal: Welches Tier
- angle: Erzähl-Winkel/Perspektive
- setting: Ort/Umgebung/Licht
- image_style: Kurze Bildbeschreibung (verbinde angle + setting sinnvoll)
- hook_style: "shock" | "question" | "pov" | "fact"
- hook_text_a: Hook-Text Variante A — AUF ENGLISCH (erscheint als Text im Video)
- hook_text_b: Hook-Text Variante B — AUF ENGLISCH
- hashtags: 3-5 relevante englische Hashtags (Array)
- music_mood: Musik-Stimmung für ACE-Step (keine Vocals, max 20 Wörter)
- upload_time: Uhrzeit
- reasoning: kurze, datenbasierte Begründung (nenne, ob eher eigene Erfahrung oder Trend ausschlaggebend war)

Antworte NUR als JSON-Array mit genau {count} Elementen.
"""

        try:
            response = self.gemini.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            plan = json.loads(text)
            if not isinstance(plan, list) or not plan:
                raise ValueError("Ungültiges Format")
        except Exception as e:
            logger.error(f"Strategy Gemini error: {e} — nutze Fallback")
            plan = self._fallback_plan()

        plan = plan[:count]   # nie mehr als gewünscht
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
