"""Offline regression checks for the Groq-only AI adapter."""
import unittest
from unittest.mock import Mock, patch

from agents import ai_client, subtask_ai, groq_vision


class GroqClientTests(unittest.TestCase):
    @patch("agents.ai_client.get_api_key", return_value="")
    @patch("agents.ai_client.requests.post")
    def test_missing_key_fails_without_ollama_fallback(self, post, _key):
        with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY"):
            ai_client.call_ai([{"role": "user", "content": "Bonjour"}])
        post.assert_not_called()

    @patch("agents.ai_client.get_api_key", return_value="example-test-key")
    @patch("agents.ai_client.requests.post")
    def test_text_routes_to_groq(self, post, _key):
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Bonjour !"}}]
        }
        result = ai_client.call_ai([{"role": "user", "content": "Bonjour"}])
        self.assertEqual(result, "Bonjour !")
        self.assertEqual(post.call_args.kwargs["json"]["model"],
                         ai_client.model_name())
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"],
                         "Bearer example-test-key")

    @patch("agents.ai_client.get_api_key", return_value="example-test-key")
    @patch("agents.ai_client.requests.post")
    def test_vision_selects_vision_model(self, post, _key):
        post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Image analysee"}}]
        }
        ai_client.call_ai([{"role": "user", "content": []}], vision=True)
        self.assertEqual(post.call_args.kwargs["json"]["model"],
                         ai_client.model_name(vision=True))

    @patch("agents.ai_client.get_api_key", return_value="example-test-key")
    @patch("agents.ai_client.requests.post")
    def test_invalid_response_is_explicit_error(self, post, _key):
        post.return_value.json.return_value = {"choices": []}
        with self.assertRaisesRegex(RuntimeError, "invalide"):
            ai_client.call_ai([{"role": "user", "content": "Bonjour"}])


class QuickMindAITests(unittest.TestCase):
    @patch("agents.subtask_ai.call_ai",
           return_value='{"subtasks": ["Analyser", "Planifier"]}')
    def test_subtask_generation_uses_groq(self, call):
        self.assertEqual(
            subtask_ai.generate_subtasks("Projet", max_subtasks=2),
            ["Analyser", "Planifier"]
        )
        call.assert_called_once()

    @patch("agents.groq_vision.call_ai",
           return_value='{"analysis": "OK", "tasks": []}')
    def test_vision_workflow_calls_shared_client(self, call):
        result = groq_vision.analyze_and_generate_tasks(
            "Analyser une image", image_b64="aGVsbG8=", image_mime="image/png"
        )
        self.assertEqual(result["tasks"], [])
        self.assertTrue(call.call_args.kwargs["vision"])


if __name__ == "__main__":
    unittest.main()
