"""
Main — Orchestrierung aller Agenten.
Läuft als dauerhafter Prozess auf dem VPS.
"""

import os
import uuid
import schedule
import time
from datetime import datetime
from loguru import logger

from config.settings import (
    VIDEOS_PER_DAY, UPLOAD_TIME_VIDEO_1, UPLOAD_TIME_VIDEO_2,
    PRODUCTION_START_TIME, RESEARCH_INTERVAL_H,
    ANALYTICS_CHECK_TIME, OPTIMIZER_DAY, OPTIMIZER_TIME,
    TEMP_DIR, LOGS_DIR
)
from agents.memory_agent      import MemoryAgent
from agents.researcher_agent  import ResearcherAgent
from agents.strategy_agent    import StrategyAgent
from agents.content_builder   import ContentBuilder
from agents.image_generator   import ImageGenerator
from agents.video_generator   import VideoGenerator
from agents.music_generator   import MusicGenerator
from agents.post_production   import PostProduction
from agents.uploader          import Uploader
from agents.comment_manager   import CommentManager
from agents.analytics_agent   import AnalyticsAgent
from agents.ab_tester         import ABTester
from agents.optimizer_agent   import OptimizerAgent

# Logging einrichten
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
logger.add(
    f"{LOGS_DIR}/bot.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Agenten initialisieren
memory      = MemoryAgent()
researcher  = ResearcherAgent()
strategy    = StrategyAgent()
content_b   = ContentBuilder()
image_gen   = ImageGenerator()
video_gen   = VideoGenerator()
music_gen   = MusicGenerator()
post_prod   = PostProduction()
uploader    = Uploader()
comments    = CommentManager()
analytics   = AnalyticsAgent()
ab_tester   = ABTester()
optimizer   = OptimizerAgent()


def run_production_pipeline() -> None:
    """Generiert und uploaded die täglichen Videos."""
    logger.info("🚀 Produktions-Pipeline gestartet")

    # Strategy holen
    strategy_data = memory.get_strategy()
    if not strategy_data.get("videos"):
        logger.info("Kein Plan vorhanden → Strategy Agent läuft")
        strategy_data = {"videos": strategy.plan_next_videos()}

    videos_to_produce = strategy_data.get("videos", [])
    if not videos_to_produce:
        logger.error("Keine Videos geplant!")
        return

    for video_plan in videos_to_produce:
        video_id = str(uuid.uuid4())[:8]
        animal   = video_plan.get("animal", "golden retriever puppy")

        try:
            logger.info(f"--- Produziere Video {video_id}: {animal} ---")

            # 1. Content generieren
            content = content_b.build_content(video_plan)

            # 2. Bild generieren
            image_path = image_gen.generate(
                content["image_prompt"], video_id
            )

            # 3. Video generieren (dauert 10-45 Min)
            video_path = video_gen.generate(
                image_path, content["video_prompt"], video_id
            )

            # 4. Musik generieren
            music_path = music_gen.generate(
                content["music_mood"], video_id
            )

            # 5. Post-Produktion: 2 Varianten für A/B Test
            final_a = post_prod.produce(
                video_path, music_path, content, video_id, variant="a"
            )
            final_b = post_prod.produce(
                video_path, music_path, content, video_id, variant="b"
            )

            # 6. Upload
            vid_id_a = uploader.upload_video(
                final_a, content, video_plan, variant="a"
            )
            vid_id_b = uploader.upload_video(
                final_b, content, video_plan, variant="b"
            )

            # 7. A/B Test registrieren
            test_id = ab_tester.register_ab_test(
                vid_id_a, vid_id_b,
                content["hook_text_a"], content["hook_text_b"],
                video_plan.get("hook_style", "shock")
            )

            # 8. Comment Manager nach 30 Min starten
            def reply_job():
                comments.reply_to_comments(vid_id_a, animal)
                comments.reply_to_comments(vid_id_b, animal)

            schedule.every(30).minutes.do(reply_job).tag(f"replies_{video_id}")

            # 9. Temp-Dateien aufräumen
            post_prod.cleanup_temp(video_id)

            logger.info(f"✅ Video {video_id} fertig! IDs: {vid_id_a}, {vid_id_b}")

        except Exception as e:
            logger.error(f"❌ Video {video_id} fehlgeschlagen: {e}")
            try:
                post_prod.cleanup_temp(video_id)
            except Exception:
                pass
            continue


def main():
    logger.info("🤖 YouTube Shorts Bot startet")

    # Schedule einrichten
    schedule.every(RESEARCH_INTERVAL_H).hours.do(researcher.run)
    schedule.every().day.at("06:00").do(strategy.plan_next_videos)
    schedule.every().day.at(PRODUCTION_START_TIME).do(run_production_pipeline)
    schedule.every().day.at(ANALYTICS_CHECK_TIME).do(
        analytics.check_and_update_all_videos
    )
    schedule.every().day.at("12:00").do(ab_tester.evaluate_pending_tests)
    getattr(schedule.every(), OPTIMIZER_DAY).at(OPTIMIZER_TIME).do(
        optimizer.run_weekly_optimization
    )

    # Sofort beim Start Researcher ausführen
    researcher.run()

    logger.info("✅ Schedule aktiv — Bot läuft")

    # Haupt-Loop
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
