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

from config.settings import TEMP_DIR, LOGS_DIR, HF_TOKENS, VIDEOS_GENERATED_PER_DAY


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
    from agents.selector import Selector

    strategy   = StrategyAgent()
    content_b  = ContentBuilder()
    image_gen  = ImageGenerator()
    video_gen  = VideoGenerator()
    music_gen  = MusicGenerator()
    post_prod  = PostProduction()
    uploader   = Uploader()
    selector   = Selector()

    videos_to_produce = strategy.plan_next_videos(VIDEOS_GENERATED_PER_DAY)
    if not videos_to_produce:
        logger.error("Keine Videos geplant!")
        return

    n_tokens = len(HF_TOKENS)

    # ---- Phase 1: ALLE Kandidaten bauen (noch KEIN Upload), HF-Accounts rotieren ----
    built = []
    for i, video_plan in enumerate(videos_to_produce):
        video_id = str(uuid.uuid4())[:8]
        animal   = video_plan.get("animal", "golden retriever puppy")

        # HF-Account pro Video rotieren → ZeroGPU-Quota auf alle Accounts verteilen.
        if n_tokens:
            token = HF_TOKENS[i % n_tokens]
            image_gen.token = token
            video_gen.token = token
            music_gen.token = token
            logger.info(f"🔑 HF-Account {i % n_tokens + 1}/{n_tokens} für dieses Video")

        try:
            logger.info(f"--- Baue Kandidat {video_id}: {animal} ---")
            content    = content_b.build_content(video_plan)
            image_path = image_gen.generate(content["image_prompt"], video_id)
            video_path = video_gen.generate(image_path, content["video_prompt"], video_id)
            music_path = music_gen.generate(content["music_mood"], video_id)
            final      = post_prod.produce(video_path, music_path, content, video_id, variant="a")

            built.append({
                "video_id":    video_id,
                "final":       final,
                "content":     content,
                "plan":        video_plan,
                # Felder für den Selector:
                "animal":      animal,
                "angle":       video_plan.get("angle"),
                "setting":     video_plan.get("setting"),
                "hook_style":  video_plan.get("hook_style"),
                "hook_text_a": content.get("hook_text_a"),
                "title":       content.get("title"),
                "hashtags":    content.get("hashtags"),
            })
            logger.info(f"🧱 Kandidat gebaut: {video_id} ({animal})")
        except Exception as e:
            logger.error(f"❌ Bau von {video_id} fehlgeschlagen: {e}")
            try:
                post_prod.cleanup_temp(video_id)
            except Exception:
                pass

    if not built:
        logger.error("Kein Kandidat erfolgreich gebaut.")
        return

    # ---- Phase 2: Potenzial bewerten (Verweildauer + Likes) + die besten wählen ----
    scored = selector.evaluate(built)
    chosen = selector.select(scored)
    chosen_ids = {c["video_id"] for c in chosen}

    # ---- Phase 3: nur die besten hochladen, Rest verwerfen, alles aufräumen ----
    uploaded = 0
    for c in built:
        vid = c["video_id"]
        if vid in chosen_ids:
            try:
                plan = c["plan"]
                plan["predicted_potential"] = round(c.get("potential", 0))
                yt_id = uploader.upload_video(c["final"], c["content"], plan, variant="a")
                uploaded += 1
                logger.info(
                    f"⬆️  Hochgeladen ({c['animal']}, Potenzial {c.get('potential', 0):.0f}): "
                    f"https://youtube.com/shorts/{yt_id}"
                )
            except Exception as e:
                logger.error(f"Upload fehlgeschlagen {vid}: {e}")
        else:
            logger.info(f"🗑️  Verworfen (Potenzial {c.get('potential', 0):.0f}): {c['animal']}")
        try:
            post_prod.cleanup_temp(vid)
        except Exception:
            pass

    logger.info(f"✅ Produce fertig: {uploaded} von {len(built)} Kandidaten hochgeladen.")


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
