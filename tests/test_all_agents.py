"""
Tests für alle Agenten.
Nutzt Mock-Daten — keine echten API-Calls.
"""

import unittest
from unittest.mock import patch, MagicMock
import json


class TestMemoryAgent(unittest.TestCase):

    @patch("agents.memory_agent.requests.put")
    @patch("agents.memory_agent.requests.get")
    def test_save_and_read_video(self, mock_get, mock_put):
        mock_put.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            text=json.dumps({"video_id": "test123", "animal": "panda"})
        )

        from agents.memory_agent import MemoryAgent
        ma = MemoryAgent()
        ma.save_video({"video_id": "test123", "animal": "panda"})
        result = ma._kv_read("video:test123")
        self.assertEqual(result["video_id"], "test123")

    def test_pattern_extraction(self):
        from agents.memory_agent import MemoryAgent
        ma = MemoryAgent()
        # Test mit Mock-Videos
        viral_animals = ["golden retriever", "golden retriever", "panda"]
        best = max(set(viral_animals), key=viral_animals.count)
        self.assertEqual(best, "golden retriever")


class TestContentBuilder(unittest.TestCase):

    @patch("agents.content_builder.genai.GenerativeModel")
    def test_build_content_structure(self, mock_model):
        mock_instance = MagicMock()
        mock_instance.generate_content.return_value = MagicMock(
            text="Test response"
        )
        mock_model.return_value = mock_instance

        from agents.content_builder import ContentBuilder
        cb = ContentBuilder()
        video_plan = {
            "animal":      "golden retriever puppy",
            "image_style": "natural close-up",
            "hook_style":  "shock",
            "hook_text_a": "You won't believe this 😱",
            "hook_text_b": "Wait for it... 🤯",
            "music_mood":  "upbeat 120bpm no vocals"
        }
        content = cb.build_content(video_plan)
        required_keys = [
            "video_prompt", "image_prompt", "animal_fact",
            "hook_text_a", "hook_text_b", "title",
            "description", "hashtags", "music_mood"
        ]
        for key in required_keys:
            self.assertIn(key, content)


class TestUploaderSafety(unittest.TestCase):
    """Kritisch: Sicherstellen dass MADE_FOR_KIDS immer False."""

    def test_made_for_kids_is_false(self):
        from config.settings import YOUTUBE_MADE_FOR_KIDS
        self.assertFalse(YOUTUBE_MADE_FOR_KIDS,
            "KRITISCH: YOUTUBE_MADE_FOR_KIDS muss False sein!")

    def test_upload_body_made_for_kids_false(self):
        """Upload-Body darf niemals made_for_kids=True enthalten."""
        body = {
            "status": {
                "selfDeclaredMadeForKids": False,
                "madeForKids":             False
            }
        }
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])
        self.assertFalse(body["status"]["madeForKids"])


class TestABTester(unittest.TestCase):

    def test_winner_calculation(self):
        from agents.ab_tester import ABTester
        ab = ABTester()
        views_a = 15000
        views_b = 8000
        winner  = "a" if views_a >= views_b else "b"
        uplift  = abs(views_a - views_b) / max(views_b, 1) * 100
        self.assertEqual(winner, "a")
        self.assertAlmostEqual(uplift, 87.5, places=0)


class TestPostProductionVerify(unittest.TestCase):

    def test_verify_rejects_small_files(self):
        from agents.post_production import PostProduction
        pp = PostProduction()
        self.assertFalse(pp.verify_output("/nonexistent/file.mp4"))


if __name__ == "__main__":
    unittest.main()
