"""
Analytics Agent — Holt Performance-Daten von YouTube.
Läuft 24h, 48h, 72h nach jedem Upload.
"""

from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from loguru import logger
from config.settings import (
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN, YOUTUBE_CHANNEL_ID
)
from agents.memory_agent import MemoryAgent


class AnalyticsAgent:

    def __init__(self):
        self.memory = MemoryAgent()

    def _get_analytics_service(self):
        credentials = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token"
        )
        return build("youtubeAnalytics", "v2", credentials=credentials)

    def get_video_analytics(self, video_id: str, upload_date: str) -> dict:
        try:
            analytics = self._get_analytics_service()
            start_date = upload_date[:10]
            end_date   = datetime.now().strftime("%Y-%m-%d")

            response = analytics.reports().query(
                ids=f"channel=={YOUTUBE_CHANNEL_ID}",
                startDate=start_date,
                endDate=end_date,
                metrics=(
                    "views,estimatedMinutesWatched,"
                    "averageViewDuration,averageViewPercentage,"
                    "likes,comments,shares,subscribersGained"
                ),
                dimensions="video",
                filters=f"video=={video_id}"
            ).execute()

            rows = response.get("rows", [])
            if not rows:
                return {"views": 0, "avg_view_percentage": 0}

            row = rows[0]
            return {
                "views":                int(row[1])   if len(row) > 1 else 0,
                "watch_minutes":        float(row[2]) if len(row) > 2 else 0,
                "avg_view_duration":    float(row[3]) if len(row) > 3 else 0,
                "avg_view_percentage":  float(row[4]) if len(row) > 4 else 0,
                "likes":                int(row[5])   if len(row) > 5 else 0,
                "comments":             int(row[6])   if len(row) > 6 else 0,
                "shares":               int(row[7])   if len(row) > 7 else 0,
                "new_subscribers":      int(row[8])   if len(row) > 8 else 0
            }
        except Exception as e:
            logger.error(f"Analytics Fehler für {video_id}: {e}")
            return {}

    def check_and_update_all_videos(self) -> None:
        """Prüft alle Videos und updated Analytics wenn nötig."""
        videos = self.memory.get_all_videos()
        now    = datetime.now()

        for video in videos:
            video_id    = video.get("video_id")
            uploaded_at = video.get("uploaded_at")
            if not video_id or not uploaded_at:
                continue

            upload_time = datetime.fromisoformat(uploaded_at)
            hours_since = (now - upload_time).total_seconds() / 3600

            # Check bei 24h, 48h, 72h
            needs_check = False
            for checkpoint in [24, 48, 72]:
                key = f"analytics_{checkpoint}h"
                if hours_since >= checkpoint and key not in video:
                    needs_check = True
                    break

            if needs_check:
                analytics = self.get_video_analytics(video_id, uploaded_at)
                if analytics:
                    checkpoint_key = (
                        "analytics_72h" if hours_since >= 72 else
                        "analytics_48h" if hours_since >= 48 else
                        "analytics_24h"
                    )
                    self.memory.update_video_analytics(video_id, {
                        checkpoint_key: analytics,
                        "views":              analytics.get("views", 0),
                        "avg_view_percentage": analytics.get("avg_view_percentage", 0)
                    })
                    logger.info(
                        f"Analytics updated: {video_id} | "
                        f"Views: {analytics.get('views', 0)} | "
                        f"Retention: {analytics.get('avg_view_percentage', 0):.1f}%"
                    )
