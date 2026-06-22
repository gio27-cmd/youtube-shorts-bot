"""
Memory Agent — Das Gehirn des Bots.
Speichert alles in Cloudflare KV.
Liest Muster und gibt dem Strategy Agent Kontext.

Cloudflare KV Free Tier:
- 100.000 Reads/Tag
- 1.000 Writes/Tag
- 1 GB Storage
"""

from __future__ import annotations

import json
import requests
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger
from config.settings import (
    CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_KV_NS_ID, CLOUDFLARE_API_TOKEN,
    KV_PREFIX_VIDEO, KV_KEY_RESEARCH, KV_KEY_STRATEGY,
    KV_KEY_BEST, KV_KEY_WORST, KV_PREFIX_ABTEST,
    KV_KEY_CHANNEL, KV_KEY_WEEKLY,
    VIRAL_THRESHOLD_VIEWS, GOOD_THRESHOLD_VIEWS, BAD_THRESHOLD_VIEWS
)


class MemoryAgent:

    def __init__(self):
        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/"
            f"{CLOUDFLARE_KV_NS_ID}"
        )
        self.headers = {
            "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json"
        }

    # ----------------------------------------------------------
    # CORE KV OPERATIONS
    # ----------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _kv_write(self, key: str, value: dict) -> bool:
        url = f"{self.base_url}/values/{key}"
        response = requests.put(
            url,
            headers=self.headers,
            data=json.dumps(value)
        )
        if response.status_code == 200:
            logger.debug(f"KV write OK: {key}")
            return True
        logger.error(f"KV write FAIL: {key} → {response.text}")
        return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _kv_read(self, key: str) -> dict | None:
        url = f"{self.base_url}/values/{key}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return json.loads(response.text)
        if response.status_code == 404:
            return None
        logger.error(f"KV read FAIL: {key} → {response.text}")
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _kv_list(self, prefix: str) -> list:
        url = f"{self.base_url}/keys?prefix={prefix}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [item["name"] for item in response.json().get("result", [])]
        return []

    # ----------------------------------------------------------
    # VIDEO OPERATIONEN
    # ----------------------------------------------------------

    def save_video(self, video_data: dict) -> None:
        """Speichert Video-Metadaten nach Upload."""
        video_id = video_data.get("video_id")
        if not video_id:
            logger.error("save_video: Kein video_id angegeben")
            return
        video_data["saved_at"] = datetime.now().isoformat()
        self._kv_write(f"{KV_PREFIX_VIDEO}{video_id}", video_data)
        logger.info(f"Video gespeichert: {video_id}")

    def update_video_analytics(self, video_id: str, analytics: dict) -> None:
        """Updated Analytics-Daten eines Videos."""
        key = f"{KV_PREFIX_VIDEO}{video_id}"
        existing = self._kv_read(key) or {}
        existing.update(analytics)
        existing["analytics_updated_at"] = datetime.now().isoformat()

        # Qualität primär an VERWEILDAUER (Retention) + LIKE-RATE festmachen — das
        # sind die echten Erfolgssignale und funktionieren auch bei wenigen Views
        # (neuer Kanal). Views fließen nur als Bonus/Override bei viralem Reach ein.
        views     = existing.get("views", 0)
        likes     = existing.get("likes", 0)
        retention = existing.get("avg_view_percentage", 0)        # 0-100
        like_rate = round(likes / views, 4) if views else 0.0
        existing["like_rate"] = like_rate

        if (retention >= 60 and like_rate >= 0.04) or views >= VIRAL_THRESHOLD_VIEWS:
            existing["performance"] = "viral"
        elif retention >= 40 or views >= GOOD_THRESHOLD_VIEWS:
            existing["performance"] = "good"
        else:
            existing["performance"] = "bad"

        self._kv_write(key, existing)
        self._update_best_patterns()
        logger.info(f"Analytics updated: {video_id} → {existing.get('performance')}")

    def get_all_videos(self) -> list[dict]:
        """Holt alle gespeicherten Videos."""
        keys = self._kv_list(KV_PREFIX_VIDEO)
        videos = []
        for key in keys:
            video = self._kv_read(key)
            if video:
                videos.append(video)
        return sorted(videos, key=lambda x: x.get("saved_at", ""), reverse=True)

    def get_last_n_videos(self, n: int = 10) -> list[dict]:
        return self.get_all_videos()[:n]

    # ----------------------------------------------------------
    # PATTERN ERKENNUNG
    # ----------------------------------------------------------

    def _update_best_patterns(self) -> None:
        """Analysiert alle Videos und extrahiert Muster."""
        videos = self.get_all_videos()
        if not videos:
            return

        viral_videos = [v for v in videos if v.get("performance") == "viral"]
        bad_videos   = [v for v in videos if v.get("performance") == "bad"]

        def most_common(lst):
            lst = [x for x in lst if x]
            if not lst:
                return None
            return max(set(lst), key=lst.count)

        best = {
            "best_animal":       most_common([v.get("animal") for v in viral_videos]),
            "best_hook_style":   most_common([v.get("hook_style") for v in viral_videos]),
            "best_upload_time":  most_common([v.get("upload_time") for v in viral_videos]),
            "best_upload_day":   most_common([v.get("upload_day") for v in viral_videos]),
            "viral_count":       len(viral_videos),
            "total_videos":      len(videos),
            "updated_at":        datetime.now().isoformat()
        }

        worst = {
            "worst_animal":      most_common([v.get("animal") for v in bad_videos]),
            "worst_hook_style":  most_common([v.get("hook_style") for v in bad_videos]),
            "worst_upload_time": most_common([v.get("upload_time") for v in bad_videos]),
            "bad_count":         len(bad_videos),
            "updated_at":        datetime.now().isoformat()
        }

        self._kv_write(KV_KEY_BEST, best)
        self._kv_write(KV_KEY_WORST, worst)
        logger.info(f"Patterns updated: {len(viral_videos)} viral, {len(bad_videos)} bad")

    def get_best_patterns(self)  -> dict: return self._kv_read(KV_KEY_BEST)  or {}
    def get_worst_patterns(self) -> dict: return self._kv_read(KV_KEY_WORST) or {}

    # ----------------------------------------------------------
    # RESEARCH & STRATEGY
    # ----------------------------------------------------------

    def save_research(self, data: dict) -> None:
        data["saved_at"] = datetime.now().isoformat()
        self._kv_write(KV_KEY_RESEARCH, data)

    def get_research(self) -> dict:
        return self._kv_read(KV_KEY_RESEARCH) or {}

    def save_strategy(self, strategy: dict) -> None:
        strategy["saved_at"] = datetime.now().isoformat()
        self._kv_write(KV_KEY_STRATEGY, strategy)

    def get_strategy(self) -> dict:
        return self._kv_read(KV_KEY_STRATEGY) or {}

    # ----------------------------------------------------------
    # A/B TESTS & WEEKLY
    # ----------------------------------------------------------

    def save_ab_result(self, test_id: str, result: dict) -> None:
        result["saved_at"] = datetime.now().isoformat()
        self._kv_write(f"{KV_PREFIX_ABTEST}{test_id}", result)

    def get_all_ab_results(self) -> list[dict]:
        keys = self._kv_list(KV_PREFIX_ABTEST)
        return [self._kv_read(k) for k in keys if self._kv_read(k)]

    def get_channel_stats(self) -> dict:
        return self._kv_read(KV_KEY_CHANNEL) or {}

    def update_channel_stats(self, stats: dict) -> None:
        stats["updated_at"] = datetime.now().isoformat()
        self._kv_write(KV_KEY_CHANNEL, stats)

    def update_weekly_report(self, report: dict) -> None:
        report["created_at"] = datetime.now().isoformat()
        self._kv_write(KV_KEY_WEEKLY, report)

    def get_weekly_report(self) -> dict:
        return self._kv_read(KV_KEY_WEEKLY) or {}
