"""
Image Generator — Kling O1 (kostenlos, unbegrenzt).
Fallback: FLUX.1-schnell auf HuggingFace.
"""

from __future__ import annotations

import os
import requests
import time
from PIL import Image
from io import BytesIO
from huggingface_hub import InferenceClient
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import HF_TOKEN, KLING_COOKIES, TEMP_DIR


class ImageGenerator:

    def __init__(self, token: str | None = None):
        # Pro Video rotierbarer HF-Account (siehe run_task). Standard: HF_TOKEN.
        self.token = token or HF_TOKEN
        self.kling_headers = {
            "Cookie":       KLING_COOKIES or "",
            "User-Agent":   "Mozilla/5.0 (compatible; Bot)",
            "Content-Type": "application/json",
            "Origin":       "https://klingai.com",
            "Referer":      "https://klingai.com/"
        }

    def generate_with_kling(self, prompt: str, output_path: str) -> str | None:
        """Generiert Bild via Kling O1 inoffizielle API."""
        try:
            # Submit Generation
            response = requests.post(
                "https://klingai.com/api/works/image-works",
                headers=self.kling_headers,
                json={
                    "prompt":       prompt,
                    "aspect_ratio": "9:16",
                    "image_count":  1,
                    "model_name":   "kolors-v1-5"
                },
                timeout=30
            )
            if response.status_code != 200:
                logger.warning(f"Kling submit failed: {response.status_code}")
                return None

            data    = response.json()
            work_id = data.get("data", {}).get("works", [{}])[0].get("workId")
            if not work_id:
                logger.warning("Kling: Kein work_id erhalten")
                return None

            # Poll bis fertig
            for _ in range(24):  # Max 120 Sekunden
                time.sleep(5)
                status_response = requests.get(
                    f"https://klingai.com/api/works/{work_id}",
                    headers=self.kling_headers
                )
                status_data = status_response.json()
                works = status_data.get("data", {}).get("works", [{}])
                status = works[0].get("status") if works else None

                if status == "succeed":
                    img_url = works[0].get("coverUrl") or \
                              works[0].get("works", [{}])[0].get("resource")
                    if img_url:
                        img_response = requests.get(img_url, timeout=30)
                        with open(output_path, "wb") as f:
                            f.write(img_response.content)
                        logger.info(f"✅ Kling Bild: {output_path}")
                        return output_path
                elif status in ["failed", "error"]:
                    logger.warning("Kling: Generation fehlgeschlagen")
                    return None

            logger.warning("Kling: Timeout")
            return None

        except Exception as e:
            logger.error(f"Kling error: {e}")
            return None

    def generate_with_flux(self, prompt: str, output_path: str) -> str:
        """Fallback: FLUX.1-schnell via HuggingFace."""
        logger.info("Nutze FLUX Fallback...")
        # Client pro Aufruf mit aktuellem (rotierendem) Token erstellen.
        image = InferenceClient(token=self.token).text_to_image(
            prompt,
            model="black-forest-labs/FLUX.1-schnell"
        )
        image.save(output_path)
        logger.info(f"✅ FLUX Bild: {output_path}")
        return output_path

    def verify_image(self, image_path: str) -> bool:
        if not os.path.exists(image_path):
            return False
        if os.path.getsize(image_path) < 10_000:  # < 10KB
            return False
        try:
            img = Image.open(image_path)
            w, h = img.size
            return w >= 256 and h >= 256
        except Exception:
            return False

    def generate(self, prompt: str, video_id: str) -> str:
        """Hauptfunktion mit automatischem Fallback."""
        output_path = os.path.join(TEMP_DIR, f"{video_id}_image.jpg")
        os.makedirs(TEMP_DIR, exist_ok=True)

        # Versuche Kling
        if KLING_COOKIES:
            result = self.generate_with_kling(prompt, output_path)
            if result and self.verify_image(result):
                return result

        # Fallback: FLUX
        result = self.generate_with_flux(prompt, output_path)
        if self.verify_image(result):
            return result

        raise RuntimeError(f"Bild-Generierung fehlgeschlagen für: {video_id}")
