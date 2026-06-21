"""
Uploader — YouTube Data API v3.

KRITISCH: YOUTUBE_MADE_FOR_KIDS = False IMMER!
Sonst: Keine personalisierten Anzeigen → 90% weniger Einnahmen.
"""

import os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from loguru import logger
from config.settings import (
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN,
    YOUTUBE_CHANNEL_ID, YOUTUBE_CATEGORY_ID, YOUTUBE_PRIVACY,
    YOUTUBE_MADE_FOR_KIDS, YOUTUBE_LANGUAGE
)
from agents.memory_agent import MemoryAgent


class Uploader:

    def __init__(self):
        self.memory = MemoryAgent()

    def _get_youtube_service(self):
        credentials = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token"
        )
        return build("youtube", "v3", credentials=credentials)

    def upload_video(
        self,
        video_path:  str,
        content:     dict,
        video_plan:  dict,
        variant:     str = "a"
    ) -> str:
        """
        Lädt Video auf YouTube hoch.
        Gibt video_id zurück.
        """
        youtube = self._get_youtube_service()

        hook_text = content.get(f"hook_text_{variant}", "")
        title     = content.get("title", f"{video_plan.get('animal', 'Tier')} Video")
        hashtags  = content.get("hashtags", [])
        description = (
            content.get("description", "") +
            "\n\n" +
            " ".join(hashtags)
        )

        # Tags ohne # Zeichen
        tags = [tag.replace("#", "") for tag in hashtags]

        body = {
            "snippet": {
                "title":                title,
                "description":          description,
                "tags":                 tags,
                "categoryId":           YOUTUBE_CATEGORY_ID,
                "defaultLanguage":      YOUTUBE_LANGUAGE,
                "defaultAudioLanguage": YOUTUBE_LANGUAGE
            },
            "status": {
                "privacyStatus":           YOUTUBE_PRIVACY,
                "selfDeclaredMadeForKids": False,   # ← KRITISCH!
                "madeForKids":             False    # ← KRITISCH!
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024  # 1MB Chunks
        )

        logger.info(f"📤 Upload: {title}")
        request  = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.debug(f"Upload {int(status.progress() * 100)}%")

        video_id = response["id"]

        # In Memory speichern
        now = datetime.now()
        self.memory.save_video({
            "video_id":    video_id,
            "animal":      video_plan.get("animal"),
            "hook_style":  video_plan.get("hook_style"),
            "hook_text":   hook_text,
            "upload_time": video_plan.get("upload_time"),
            "upload_day":  now.strftime("%A").lower(),
            "variant":     variant,
            "title":       title,
            "uploaded_at": now.isoformat()
        })

        logger.info(f"✅ Upload fertig: https://youtube.com/shorts/{video_id}")
        return video_id
