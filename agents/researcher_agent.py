"""
Researcher Agent — Findet 6-24h im Voraus was viral wird.
Quellen: YouTube API + Reddit + Google Trends + Gemini Analyse.
Läuft alle 6 Stunden.
"""

import praw
import google.generativeai as genai
from pytrends.request import TrendReq
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from datetime import datetime, timedelta
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import (
    GEMINI_API_KEY, GEMINI_MODEL,
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN,
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS, ANIMAL_CATEGORIES
)
from agents.memory_agent import MemoryAgent


class ResearcherAgent:

    def __init__(self):
        self.memory = MemoryAgent()
        genai.configure(api_key=GEMINI_API_KEY)
        self.gemini = genai.GenerativeModel(GEMINI_MODEL)

    # ----------------------------------------------------------
    # YOUTUBE TRENDING
    # ----------------------------------------------------------

    def search_youtube_trending(self, hours_back: int = 6) -> list[dict]:
        try:
            credentials = Credentials(
                token=None,
                refresh_token=YOUTUBE_REFRESH_TOKEN,
                client_id=YOUTUBE_CLIENT_ID,
                client_secret=YOUTUBE_CLIENT_SECRET,
                token_uri="https://oauth2.googleapis.com/token"
            )
            youtube = build("youtube", "v3", credentials=credentials)
            published_after = (
                datetime.utcnow() - timedelta(hours=hours_back)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

            response = youtube.search().list(
                q="animals cute funny",
                type="video",
                videoDuration="short",
                order="viewCount",
                publishedAfter=published_after,
                maxResults=10,
                part="snippet"
            ).execute()

            results = []
            for item in response.get("items", []):
                title = item["snippet"]["title"].lower()
                animal = self._extract_animal_from_title(title)
                results.append({
                    "title": item["snippet"]["title"],
                    "video_id": item["id"]["videoId"],
                    "animal": animal
                })
            logger.info(f"YouTube: {len(results)} trending videos gefunden")
            return results
        except Exception as e:
            logger.error(f"YouTube trending error: {e}")
            return []

    def _extract_animal_from_title(self, title: str) -> str:
        for animal in ANIMAL_CATEGORIES:
            if any(word in title for word in animal.split()):
                return animal
        keywords = {
            "cat": "baby cat kitten", "dog": "golden retriever puppy",
            "panda": "baby panda", "otter": "otter playing",
            "fox": "fox in nature", "bear": "baby bear cub",
            "elephant": "baby elephant", "penguin": "penguin walking",
            "rabbit": "bunny rabbit", "capybara": "capybara"
        }
        for kw, animal in keywords.items():
            if kw in title:
                return animal
        return "golden retriever puppy"  # Sicherer Default

    # ----------------------------------------------------------
    # REDDIT HOT POSTS
    # ----------------------------------------------------------

    def search_reddit_hot(self) -> list[dict]:
        try:
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT
            )
            results = []
            for subreddit_name in REDDIT_SUBREDDITS:
                subreddit = reddit.subreddit(subreddit_name)
                for post in subreddit.hot(limit=5):
                    animal = self._extract_animal_from_title(post.title.lower())
                    results.append({
                        "title": post.title,
                        "score": post.score,
                        "animal": animal,
                        "subreddit": subreddit_name
                    })
            results.sort(key=lambda x: x["score"], reverse=True)
            logger.info(f"Reddit: {len(results)} hot posts gefunden")
            return results[:15]
        except Exception as e:
            logger.error(f"Reddit error: {e}")
            return []

    # ----------------------------------------------------------
    # GOOGLE TRENDS
    # ----------------------------------------------------------

    def get_google_trends(self) -> dict:
        try:
            pytrends = TrendReq(hl="de-DE", tz=60)
            keywords = [
                "cute cat video", "funny dog", "baby panda",
                "capybara", "red panda"
            ]
            pytrends.build_payload(keywords, timeframe="now 1-d")
            data = pytrends.interest_over_time()
            if data.empty:
                return {}
            trends = {}
            for kw in keywords:
                if kw in data.columns:
                    trends[kw] = int(data[kw].mean())
            logger.info(f"Google Trends: {trends}")
            return trends
        except Exception as e:
            logger.error(f"Google Trends error: {e}")
            return {}

    # ----------------------------------------------------------
    # GEMINI ANALYSE
    # ----------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    def analyze_with_gemini(
        self,
        youtube_data: list,
        reddit_data: list,
        trends: dict
    ) -> dict:
        prompt = f"""
Du bist ein YouTube Shorts Stratege.
Analysiere diese Trending-Daten und identifiziere Viral-Potential.

YOUTUBE TRENDING (letzte 6h):
{youtube_data[:5]}

REDDIT HOT POSTS:
{reddit_data[:5]}

GOOGLE TRENDS (Score 0-100):
{trends}

Gib mir die TOP 3 Tier-Content-Ideen mit höchstem viralen Potential
für die nächsten 12 Stunden.

Antworte NUR als JSON:
{{
  "top_animals": ["tier1", "tier2", "tier3"],
  "trending_hooks": ["hook1", "hook2"],
  "emerging_trend": "Was gerade aufkommt",
  "avoid": "Was zu vermeiden ist",
  "confidence": 0.85
}}
"""
        response = self.gemini.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        import json
        return json.loads(text)

    # ----------------------------------------------------------
    # HAUPTFUNKTION
    # ----------------------------------------------------------

    def run(self) -> dict:
        logger.info("🔍 Researcher Agent gestartet")

        youtube_data = self.search_youtube_trending()
        reddit_data  = self.search_reddit_hot()
        trends       = self.get_google_trends()

        # Mindestens 2 von 3 Quellen müssen funktionieren
        sources_ok = sum([
            len(youtube_data) > 0,
            len(reddit_data) > 0,
            len(trends) > 0
        ])
        if sources_ok < 2:
            logger.error("Researcher: Zu wenige Datenquellen verfügbar")
            return {}

        try:
            analysis = self.analyze_with_gemini(youtube_data, reddit_data, trends)
        except Exception as e:
            logger.error(f"Gemini Analyse fehlgeschlagen: {e}")
            # Fallback: Einfache Aggregation
            all_animals = [v["animal"] for v in youtube_data + reddit_data]
            most_common = max(set(all_animals), key=all_animals.count)
            analysis = {
                "top_animals": [most_common, "baby panda", "capybara"],
                "trending_hooks": ["You won't believe this 😱"],
                "emerging_trend": "Unbekannt",
                "avoid": "",
                "confidence": 0.5
            }

        research_data = {
            "top_animals":     analysis.get("top_animals", []),
            "trending_hooks":  analysis.get("trending_hooks", []),
            "emerging_trend":  analysis.get("emerging_trend", ""),
            "avoid":           analysis.get("avoid", ""),
            "confidence":      analysis.get("confidence", 0.5),
            "youtube_count":   len(youtube_data),
            "reddit_count":    len(reddit_data),
            "trends_data":     trends
        }

        self.memory.save_research(research_data)
        logger.info(f"✅ Research gespeichert: Top Animals = {analysis.get('top_animals', [])}")
        return research_data
