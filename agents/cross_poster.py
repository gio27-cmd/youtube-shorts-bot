"""
Cross Poster — Instagram Reels via Instagram Graph API.

Postet die fertigen Tier-Shorts zusätzlich als Instagram Reel.
Mehr Reichweite, gleiche Inhalte, €0.

WICHTIG — wie die Instagram Graph API funktioniert:
- Die API lädt KEINE lokale Datei hoch. Sie braucht eine ÖFFENTLICH
  erreichbare HTTPS-URL zum fertigen MP4 (video_url).
  → Das Video muss vorher irgendwo öffentlich liegen (z.B. das
    bereits hochgeladene YouTube-Short reicht NICHT, YouTube blockt
    direkten Datei-Zugriff; nutze stattdessen einen eigenen
    öffentlichen Bucket / Cloudflare R2 / einen statischen Host).
- Flow (3 Schritte):
    1. Media-Container erstellen   (POST /{ig_user_id}/media)
    2. Status pollen bis FINISHED  (GET  /{container_id}?fields=status_code)
    3. Container publishen         (POST /{ig_user_id}/media_publish)

Benötigt in .env:
- INSTAGRAM_ACCESS_TOKEN  (Long-Lived Token mit instagram_content_publish)
- INSTAGRAM_USER_ID       (Instagram Business/Creator Account ID)

Docs: https://developers.facebook.com/docs/instagram-platform/content-publishing
"""

from __future__ import annotations

import time
import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID


GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class CrossPoster:

    def __init__(self):
        self.access_token = INSTAGRAM_ACCESS_TOKEN
        self.ig_user_id   = INSTAGRAM_USER_ID

    def _is_configured(self) -> bool:
        if not self.access_token or not self.ig_user_id:
            logger.warning(
                "CrossPoster: INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_USER_ID "
                "nicht gesetzt — Instagram-Cross-Post übersprungen."
            )
            return False
        return True

    # ----------------------------------------------------------
    # SCHRITT 1: Media-Container erstellen
    # ----------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _create_container(self, video_url: str, caption: str) -> str | None:
        url = f"{GRAPH_BASE}/{self.ig_user_id}/media"
        params = {
            "media_type":   "REELS",
            "video_url":    video_url,
            "caption":      caption,
            "share_to_feed": "true",
            "access_token": self.access_token
        }
        response = requests.post(url, params=params, timeout=60)
        data = response.json()
        if response.status_code != 200 or "id" not in data:
            logger.error(f"IG Container-Erstellung fehlgeschlagen: {data}")
            return None
        container_id = data["id"]
        logger.info(f"IG Container erstellt: {container_id}")
        return container_id

    # ----------------------------------------------------------
    # SCHRITT 2: Status pollen
    # ----------------------------------------------------------

    def _wait_until_ready(self, container_id: str, max_wait_sec: int = 300) -> bool:
        url = f"{GRAPH_BASE}/{container_id}"
        params = {"fields": "status_code", "access_token": self.access_token}
        waited = 0
        interval = 10
        while waited < max_wait_sec:
            response = requests.get(url, params=params, timeout=30)
            status = response.json().get("status_code")
            if status == "FINISHED":
                logger.info("IG Container bereit (FINISHED)")
                return True
            if status == "ERROR":
                logger.error("IG Container-Verarbeitung fehlgeschlagen (ERROR)")
                return False
            logger.debug(f"IG Container Status: {status} ({waited}s)")
            time.sleep(interval)
            waited += interval
        logger.warning("IG Container Timeout — nicht rechtzeitig FINISHED")
        return False

    # ----------------------------------------------------------
    # SCHRITT 3: Publishen
    # ----------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _publish_container(self, container_id: str) -> str | None:
        url = f"{GRAPH_BASE}/{self.ig_user_id}/media_publish"
        params = {
            "creation_id":  container_id,
            "access_token": self.access_token
        }
        response = requests.post(url, params=params, timeout=60)
        data = response.json()
        if response.status_code != 200 or "id" not in data:
            logger.error(f"IG Publish fehlgeschlagen: {data}")
            return None
        media_id = data["id"]
        logger.info(f"✅ Instagram Reel veröffentlicht: {media_id}")
        return media_id

    # ----------------------------------------------------------
    # HAUPTFUNKTION
    # ----------------------------------------------------------

    def post_reel(self, video_url: str, content: dict, variant: str = "a") -> str | None:
        """
        Postet ein fertiges Video als Instagram Reel.

        video_url: ÖFFENTLICH erreichbare HTTPS-URL zur MP4-Datei.
        content:   Das content-dict aus dem ContentBuilder (für Caption/Hashtags).
        Gibt die Instagram media_id zurück (oder None bei Fehler/nicht konfiguriert).
        """
        if not self._is_configured():
            return None

        # Caption aus Titel + Beschreibung + Hashtags zusammenbauen
        title       = content.get("title", "")
        description = content.get("description", "")
        hashtags    = content.get("hashtags", [])
        caption = f"{title}\n\n{description}\n\n{' '.join(hashtags)}".strip()

        logger.info(f"📲 Instagram Cross-Post (Variante {variant})")

        container_id = self._create_container(video_url, caption)
        if not container_id:
            return None

        if not self._wait_until_ready(container_id):
            return None

        return self._publish_container(container_id)
