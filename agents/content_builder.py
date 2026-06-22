"""
Content Builder — Generiert alle Texte für ein Video.
Nutzt Gemini 2.5 Flash (kostenlos).
"""

import json
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.llm import LLMClient


class ContentBuilder:

    def __init__(self):
        # LLMClient: Gemini primär, OpenRouter als Fallback (siehe config/llm.py)
        self.gemini = LLMClient()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    def _ask_gemini(self, prompt: str) -> str:
        response = self.gemini.generate_content(prompt)
        return response.text.strip()

    def generate_video_prompt(self, animal: str, style: str) -> str:
        return self._ask_gemini(f"""
Create a short English image-to-video prompt for WAN 2.2 AI model.
Animal: {animal}
Style: {style}
Requirements: photorealistic, cinematic, natural movement, 9:16 portrait
Setting: beautiful natural environment
Action: gentle natural animal movement
Max 80 words. English only. No watermarks. No text in scene.
""")

    def generate_image_prompt(self, animal: str, style: str) -> str:
        return self._ask_gemini(f"""
Create an English image generation prompt for Kling O1.
Animal: {animal}
Style: {style}
Requirements: photorealistic 4K, close-up portrait, cute natural expression,
natural soft lighting, 9:16 vertical format, beautiful nature background.
No text, no watermarks, no humans.
Max 80 words. English only.
""")

    def generate_animal_fact(self, animal: str) -> str:
        return self._ask_gemini(f"""
Gib mir 1 überraschenden kurzen Tier-Fakt über: {animal}
Regeln: Max 55 Zeichen, 1 passendes Emoji am Ende, auf Deutsch.
Beispiel: "Pandas schlafen bis zu 14h am Tag! 🐼"
NUR den Fakt, kein anderer Text.
""")

    def generate_title(self, animal: str, hook_text: str) -> str:
        return self._ask_gemini(f"""
Erstelle einen YouTube Shorts Titel für ein {animal} Video.
Hook: {hook_text}
Regeln: Max 60 Zeichen, 1-2 Emojis, Neugier wecken, auf Deutsch.
NUR den Titel, kein anderer Text.
""")

    def generate_description(self, animal: str, fact: str) -> str:
        return self._ask_gemini(f"""
Erstelle eine kurze YouTube Beschreibung für ein {animal} Shorts Video.
Tier-Fakt: {fact}
Regeln: 2 Sätze, herzlich, auf Deutsch, max 150 Zeichen.
NUR die Beschreibung, kein anderer Text.
""")

    def generate_hashtags(self, animal: str) -> list[str]:
        result = self._ask_gemini(f"""
Erstelle 8 YouTube Hashtags für ein {animal} Video.
Immer inkludieren: #shorts #tiere #cute
Rest: tier-spezifisch und trending.
Antworte NUR als JSON-Array: ["#shorts", "#tiere", ...]
""")
        try:
            if result.startswith("```"):
                result = result.split("```")[1]
                if result.startswith("json"):
                    result = result[4:]
            return json.loads(result)
        except Exception:
            return ["#shorts", "#tiere", "#cute", "#animals",
                    "#viral", "#nature", f"#{animal.split()[0]}"]

    def generate_music_mood(self, animal: str, hook_style: str) -> str:
        mood_map = {
            "shock":    "dramatic tension building upbeat 120bpm no vocals",
            "question": "curious playful acoustic 100bpm no vocals",
            "pov":      "peaceful ambient nature piano 90bpm no vocals",
            "fact":     "light educational background music 95bpm no vocals"
        }
        base_mood = mood_map.get(hook_style, "upbeat happy 110bpm no vocals")
        return self._ask_gemini(f"""
Erstelle einen ACE-Step Musik-Prompt für ein {animal} Video.
Basis-Stimmung: {base_mood}
Regeln: Keine Vocals, 12 Sekunden Hintergrundmusik, max 20 Wörter.
Gib NUR den englischen Prompt zurück.
""")

    def build_content(self, video_plan: dict) -> dict:
        """Hauptfunktion: Generiert alle Inhalte für ein Video."""
        animal     = video_plan.get("animal", "golden retriever puppy")
        style      = video_plan.get("image_style", "natural close-up")
        angle      = video_plan.get("angle", "")
        setting    = video_plan.get("setting", "")
        hook_style = video_plan.get("hook_style", "shock")
        hook_a     = video_plan.get("hook_text_a", "You won't believe this 😱")
        hook_b     = video_plan.get("hook_text_b", "Wait for it... 🤯")

        # Winkel + Setting in den Bild-/Video-Stil einweben, damit die
        # strategische Analyse das tatsächlich generierte Material beeinflusst.
        full_style = ", ".join(s for s in [style, angle, setting] if s)

        logger.info(f"📝 Content Builder: Generiere für {animal}")

        video_prompt  = self.generate_video_prompt(animal, full_style)
        image_prompt  = self.generate_image_prompt(animal, full_style)
        animal_fact   = self.generate_animal_fact(animal)
        title         = self.generate_title(animal, hook_a)
        description   = self.generate_description(animal, animal_fact)
        # Vom Strategen geplante Hashtags bevorzugen, sonst selbst generieren.
        hashtags      = video_plan.get("hashtags") or self.generate_hashtags(animal)
        music_mood    = video_plan.get("music_mood") or \
                        self.generate_music_mood(animal, hook_style)

        content = {
            "video_prompt":  video_prompt,
            "image_prompt":  image_prompt,
            "animal_fact":   animal_fact,
            "hook_text_a":   hook_a,
            "hook_text_b":   hook_b,
            "title":         title,
            "description":   description,
            "hashtags":      hashtags,
            "music_mood":    music_mood
        }

        logger.info(f"✅ Content: '{title}'")
        return content
