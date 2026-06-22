"""
Comment Manager — Antwortet auf Kommentare.
+15-20% Reichweite durch Engagement in ersten 2 Stunden.
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from loguru import logger
from config.settings import (
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
)
from config.llm import LLMClient


class CommentManager:

    def __init__(self):
        # LLMClient: Google-Modelle (neuestes zuerst) → OpenRouter (siehe config/llm.py)
        self.gemini = LLMClient()

    def _get_youtube_service(self):
        credentials = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token"
        )
        return build("youtube", "v3", credentials=credentials)

    def get_unanswered_comments(self, video_id: str) -> list[dict]:
        try:
            youtube  = self._get_youtube_service()
            response = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=10,
                order="time"
            ).execute()

            unanswered = []
            for item in response.get("items", []):
                top    = item["snippet"]["topLevelComment"]["snippet"]
                has_reply = item["snippet"].get("totalReplyCount", 0) > 0
                if not has_reply:
                    unanswered.append({
                        "comment_id": item["snippet"]["topLevelComment"]["id"],
                        "text":       top["textDisplay"],
                        "author":     top["authorDisplayName"]
                    })
            return unanswered
        except Exception as e:
            logger.error(f"Kommentare abrufen fehlgeschlagen: {e}")
            return []

    def generate_reply(self, comment_text: str, animal: str) -> str:
        try:
            response = self.gemini.generate_content(f"""
Du betreibst einen YouTube-Kanal über Tier-Videos.
Antworte auf diesen Kommentar zu einem {animal} Video:
"{comment_text}"

Regeln:
- Max 100 Zeichen
- Herzlich und authentisch
- Auf Deutsch
- 1 passendes Emoji
- Kein Spam, keine Links
- Kein "Als KI..."

NUR die Antwort, kein anderer Text.
""")
            return response.text.strip()[:100]
        except Exception as e:
            logger.error(f"Reply Generierung fehlgeschlagen: {e}")
            return "Danke für deinen Kommentar! 🐾"

    def reply_to_comments(self, video_id: str, animal: str) -> int:
        youtube  = self._get_youtube_service()
        comments = self.get_unanswered_comments(video_id)
        count    = 0

        for comment in comments[:10]:
            reply = self.generate_reply(comment["text"], animal)
            try:
                youtube.comments().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "parentId":   comment["comment_id"],
                            "textOriginal": reply
                        }
                    }
                ).execute()
                count += 1
                logger.debug(f"Replied: {comment['author']} → {reply}")
            except Exception as e:
                logger.error(f"Reply fehlgeschlagen: {e}")

        logger.info(f"Kommentare beantwortet: {count}/{len(comments)}")
        return count
