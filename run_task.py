"""
One-Shot Task-Runner für GitHub Actions (ephemere Runner).

Der Bot läuft NICHT als Dauerprozess, sondern jeder Cron-Workflow ruft genau
eine Aufgabe auf und beendet sich. Der gesamte Zustand (Videos, Muster, A/B-Tests)
liegt in Cloudflare KV — die Runner brauchen also keinen persistenten Speicher.

Aufruf:
    python run_task.py <task>

Tasks:
    research     Trends sammeln + analysieren        (alle 6h)
    produce      Strategie planen + 2 Videos bauen & hochladen (täglich)
    analytics    Performance der Videos aktualisieren (täglich)
    ab_evaluate  Fertige A/B-Tests auswerten          (täglich)
    comments     Kommentare der letzten Videos beantworten (mehrmals/Tag)
    optimize     Wöchentliche Strategie-Optimierung   (wöchentlich)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from loguru import logger

from config.settings import TEMP_DIR, LOGS_DIR


def _setup_logging() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    logger.add(
        f"{LOGS_DIR}/bot.log",
        rotation="1 day", retention="14 days", level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )


# ----------------------------------------------------------------------
# TASKS
# ----------------------------------------------------------------------

def task_research() -> None:
    from agents.researcher_agent import ResearcherAgent
    ResearcherAgent().run()


def task_produce() -> None:
    """Plant frisch und produziert + uploaded die 2 Tagesvideos."""
    from agents.strategy_agent import StrategyAgent
    from agents.content_builder import ContentBuilder
    from agents.image_generator import ImageGenerator
    from agents.video_generator import VideoGenerator
    from agents.music_generator import MusicGenerator
    from agents.post_production import PostProduction
    from agents.uploader import Uploader
    from agents.ab_tester import ABTester

    strategy   = StrategyAgent()
    content_b  = ContentBuilder()
    image_gen  = ImageGenerator()
    video_gen  = VideoGenerator()
    music_gen  = MusicGenerator()
    post_prod  = PostProduction()
    uploader   = Uploader()
    ab_tester  = ABTester()

    videos_to_produce = strategy.plan_next_videos()
    if not videos_to_produce:
        logger.error("Keine Videos geplant!")
        return

    for video_plan in videos_to_produce:
        video_id = str(uuid.uuid4())[:8]
        animal   = video_plan.get("animal", "golden retriever puppy")
        try:
            logger.info(f"--- Produziere Video {video_id}: {animal} ---")

            content    = content_b.build_content(video_plan)
            image_path = image_gen.generate(content["image_prompt"], video_id)
            video_path = video_gen.generate(image_path, content["video_prompt"], video_id)
            music_path = music_gen.generate(content["music_mood"], video_id)

            final_a = post_prod.produce(video_path, music_path, content, video_id, variant="a")
            final_b = post_prod.produce(video_path, music_path, content, video_id, variant="b")

            vid_id_a = uploader.upload_video(final_a, content, video_plan, variant="a")
            vid_id_b = uploader.upload_video(final_b, content, video_plan, variant="b")

            ab_tester.register_ab_test(
                vid_id_a, vid_id_b,
                content["hook_text_a"], content["hook_text_b"],
                video_plan.get("hook_style", "shock")
            )

            post_prod.cleanup_temp(video_id)
            logger.info(f"✅ Video {video_id} fertig! IDs: {vid_id_a}, {vid_id_b}")
        except Exception as e:
            logger.error(f"❌ Video {video_id} fehlgeschlagen: {e}")
            try:
                post_prod.cleanup_temp(video_id)
            except Exception:
                pass
            continue


def task_analytics() -> None:
    from agents.analytics_agent import AnalyticsAgent
    AnalyticsAgent().check_and_update_all_videos()


def task_ab_evaluate() -> None:
    from agents.ab_tester import ABTester
    ABTester().evaluate_pending_tests()


def task_comments() -> None:
    """Beantwortet Kommentare aller Videos der letzten 48h."""
    from agents.memory_agent import MemoryAgent
    from agents.comment_manager import CommentManager
    memory   = MemoryAgent()
    comments = CommentManager()
    now      = datetime.now()
    handled  = 0
    for video in memory.get_last_n_videos(20):
        vid = video.get("video_id")
        uploaded_at = video.get("uploaded_at")
        if not vid or not uploaded_at:
            continue
        try:
            hours = (now - datetime.fromisoformat(uploaded_at)).total_seconds() / 3600
        except Exception:
            continue
        if hours <= 48:
            comments.reply_to_comments(vid, video.get("animal", "animal"))
            handled += 1
    logger.info(f"Comments-Task: {handled} Videos bearbeitet")


def task_optimize() -> None:
    from agents.optimizer_agent import OptimizerAgent
    OptimizerAgent().run_weekly_optimization()


DISPATCH = {
    "research":    task_research,
    "produce":     task_produce,
    "analytics":   task_analytics,
    "ab_evaluate": task_ab_evaluate,
    "comments":    task_comments,
    "optimize":    task_optimize,
}


def main() -> int:
    _setup_logging()
    task = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = DISPATCH.get(task)
    if not fn:
        logger.error(f"Unbekannter Task: '{task}'. Verfügbar: {', '.join(DISPATCH)}")
        return 2
    logger.info(f"▶️  Task gestartet: {task}")
    fn()
    logger.info(f"⏹️  Task beendet: {task}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
