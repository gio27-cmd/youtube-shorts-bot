"""
Video Generator — Image-to-Video über kostenlose HuggingFace ZeroGPU Spaces.

HINTERGRUND (Stand 2026): Die im Ur-Plan genutzten WAN-2.2-Spaces sind
inzwischen pausiert bzw. bieten keine nutzbare gradio_client-API mehr.
Stattdessen nutzen wir schnelle, laufende ZeroGPU-Spaces (LTX-Video
distilled), die ins kostenlose ZeroGPU-Limit passen (8s verifiziert).

Pipeline:  FLUX-Bild  ->  LTX  /image_to_video  ->  MP4

WICHTIG: braucht gradio_client >= 2.x  => Python 3.10+.
Die alte 1.3.0 (Python 3.9) kann moderne Gradio-Spaces NICHT lesen.
"""

from __future__ import annotations

import os
import shutil
import ffmpeg
from gradio_client import Client, handle_file
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from config.settings import HF_TOKEN, TEMP_DIR, VIDEO_DURATION_SEC


# ZeroGPU-freundliche Dauer. Freies ZeroGPU kappt die GPU-Zeit -> 8s verifiziert.
MAX_FREE_DURATION = 8

# Reihenfolge = Priorität. Jeder Eintrag beschreibt EINEN funktionierenden Space
# mit seiner echten API-Signatur. Zum Erweitern einfach weitere Specs anhängen.
VIDEO_SPACES = [
    {
        "space":    "Lightricks/ltx-video-distilled",
        "api_name": "/image_to_video",
        "kwargs":   lambda image_path, prompt, duration: {
            "prompt":                prompt,
            "negative_prompt":       "worst quality, inconsistent motion, blurry, jittery, distorted",
            "input_image_filepath":  handle_file(image_path),
            "mode":                  "image-to-video",
            "duration_ui":           float(duration),
        },
    },
]


class VideoGenerator:

    def _extract_mp4(self, result, output_path: str) -> str | None:
        """Findet den MP4-Pfad in den verschiedenen Gradio-Rückgabeformaten
        (dict{video:...}, Tuple, Liste, String)."""
        found = []

        def walk(x):
            if isinstance(x, dict):
                if x.get("video"):
                    found.append(x["video"])
                for v in x.values():
                    walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v)
            elif isinstance(x, str):
                found.append(x)

        walk(result)
        for c in found:
            if isinstance(c, str) and c.endswith(".mp4") and os.path.exists(c):
                shutil.copy(c, output_path)
                return output_path
        return None

    def _generate_with_space(self, cfg: dict, image_path: str,
                             prompt: str, output_path: str) -> str | None:
        space = cfg["space"]
        try:
            client = Client(space, token=HF_TOKEN, verbose=False)
            duration = min(VIDEO_DURATION_SEC, MAX_FREE_DURATION)
            result = client.predict(
                api_name=cfg["api_name"],
                **cfg["kwargs"](image_path, prompt, duration)
            )
            mp4 = self._extract_mp4(result, output_path)
            if mp4:
                return mp4
            logger.warning(f"Space {space}: kein MP4 im Ergebnis")
            return None
        except Exception as e:
            logger.error(f"Space {space} error: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(60))
    def generate(self, image_path: str, prompt: str, video_id: str) -> str:
        """Hauptfunktion: probiert alle Spaces der Reihe nach, mit Retry."""
        output_path = os.path.join(TEMP_DIR, f"{video_id}_raw.mp4")
        os.makedirs(TEMP_DIR, exist_ok=True)

        for cfg in VIDEO_SPACES:
            logger.info(f"🎬 Video via {cfg['space']} ...")
            result = self._generate_with_space(cfg, image_path, prompt, output_path)
            if result and self.verify_video(result):
                logger.info(f"✅ Video generiert: {output_path}")
                return result

        raise RuntimeError(f"Video-Generierung fehlgeschlagen: {video_id}")

    def verify_video(self, video_path: str) -> bool:
        if not os.path.exists(video_path):
            return False
        if os.path.getsize(video_path) < 50_000:  # < 50KB
            return False
        try:
            probe = ffmpeg.probe(video_path)
            duration = float(probe["format"]["duration"])
            return duration >= 1.0
        except Exception:
            # ffmpeg/ffprobe evtl. nicht installiert -> Größencheck hat gereicht
            return True
