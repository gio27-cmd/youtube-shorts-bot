"""
Music Generator — ACE-Step (open-source, originales Audio, keine Vocals).

WARUM ORIGINALMUSIK:
- Kein Revenue-Cut durch Musik-Publisher
- YouTube Original-Sound Bonus (+20-40% Revenue für Kanäle <50k Subs)
- Kein Copyright-Risiko

QUELLEN / FALLBACK-KETTE:
1. ACE-Step HuggingFace Space (ZeroGPU) — /__call__ Endpoint
2. Stille MP3 via FFmpeg (damit die Post-Produktion nie blockiert)

WICHTIG: braucht gradio_client >= 2.x => Python 3.10+.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from gradio_client import Client
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import HF_TOKEN, TEMP_DIR


ACE_STEP_SPACE = "ACE-Step/ACE-Step"
ACE_STEP_API   = "/__call__"


class MusicGenerator:

    def __init__(self, token: str | None = None):
        # Pro Video rotierbarer HF-Account (siehe run_task). Standard: HF_TOKEN.
        self.token = token or HF_TOKEN

    def _extract_audio(self, result, output_path: str) -> str | None:
        """Findet den Audio-Pfad in den verschiedenen Gradio-Rückgabeformaten."""
        found = []

        def walk(x):
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                found.append(x)

        walk(result)
        for c in found:
            if isinstance(c, str) and c.lower().endswith((".mp3", ".wav", ".flac", ".ogg")) \
                    and os.path.exists(c):
                shutil.copy(c, output_path)
                return output_path
        return None

    def generate_with_hf(self, mood: str, duration: int, output_path: str) -> str | None:
        """Generiert instrumentale Musik via ACE-Step HuggingFace Space."""
        try:
            client = Client(ACE_STEP_SPACE, token=self.token, verbose=False)
            result = client.predict(
                audio_duration=float(duration),
                prompt=mood,
                lyrics="[inst]",          # rein instrumental, keine Vocals
                infer_step=27,            # schneller -> ZeroGPU-schonend
                api_name=ACE_STEP_API
            )
            return self._extract_audio(result, output_path)
        except Exception as e:
            logger.error(f"ACE-Step HF error: {e}")
            return None

    def generate_silent_fallback(self, duration: int, output_path: str) -> str:
        """Erstellt stille MP3 als letzten Fallback via FFmpeg."""
        cmd = [
            "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration), "-q:a", "9", "-acodec", "libmp3lame",
            output_path, "-y"
        ]
        subprocess.run(cmd, capture_output=True)
        logger.warning("Stille MP3 als Fallback erstellt")
        return output_path

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=5, max=30))
    def generate(self, mood: str, video_id: str, duration: int = 12) -> str:
        """Hauptfunktion mit Fallback-Kette."""
        output_path = os.path.join(TEMP_DIR, f"{video_id}_music.mp3")
        os.makedirs(TEMP_DIR, exist_ok=True)

        # HuggingFace Space
        result = self.generate_with_hf(mood, duration, output_path)
        if result and os.path.exists(result) and os.path.getsize(result) > 1000:
            logger.info(f"✅ Musik generiert: {output_path}")
            return result

        # Stille als letzter Fallback
        return self.generate_silent_fallback(duration, output_path)
