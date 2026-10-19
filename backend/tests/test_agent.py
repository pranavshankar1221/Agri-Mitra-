from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import APITimeoutError
from fastapi.testclient import TestClient

from app.api.v1.endpoints import agent
from app.core.config import settings
from app.main import app


class AgentEndpointTests(unittest.TestCase):
    def test_query_uses_configured_llm_and_conversation(self):
        captured = {}

        class FakeChatOpenAI:
            def __init__(self, **kwargs):
                captured["config"] = kwargs

            def invoke(self, messages):
                captured["messages"] = messages
                return SimpleNamespace(content="Rotate crops to support soil health.")

        with (
            patch.object(settings, "NVIDIA_API_KEY", "test-key"),
            patch.object(
                settings,
                "NVIDIA_MODEL",
                "nvidia/nemotron-3.5-lightning-30b-a3b",
            ),
            patch.object(agent, "ChatOpenAI", FakeChatOpenAI),
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={
                    "query": "What should I consider for crop rotation?",
                    "history": [
                        {"role": "user", "content": "I grow cotton."},
                        {"role": "assistant", "content": "What is your soil type?"},
                    ],
                    "detailed": True,
                    "language": "hi",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["response"],
            "Rotate crops to support soil health.",
        )
        self.assertEqual(
            captured["config"]["model"],
            "nvidia/nemotron-3.5-lightning-30b-a3b",
        )
        self.assertEqual(captured["config"]["base_url"], settings.OPENAI_API_BASE)
        self.assertEqual(captured["config"]["max_tokens"], 1024)
        self.assertEqual(
            captured["config"]["timeout"],
            settings.NVIDIA_REQUEST_TIMEOUT_SECONDS,
        )
        self.assertEqual(captured["config"]["max_retries"], 0)
        self.assertEqual(captured["config"]["temperature"], 0.3)
        self.assertEqual(
            captured["config"]["extra_body"],
            {"chat_template_kwargs": {"enable_thinking": False}},
        )
        self.assertEqual(
            captured["messages"][1:3],
            [
                ("user", "I grow cotton."),
                ("assistant", "What is your soil type?"),
            ],
        )
        self.assertEqual(
            captured["messages"][-1],
            ("human", "What should I consider for crop rotation?"),
        )
        self.assertIn("no live access", captured["messages"][0][1])
        self.assertIn("numbered steps", captured["messages"][0][1])
        self.assertIn("Keep paragraphs brief", captured["messages"][0][1])
        self.assertIn("Hindi (हिन्दी)", captured["messages"][0][1])
        self.assertIn("LANGUAGE REQUIREMENT", captured["messages"][0][1])
        self.assertIn("translate explanations rather than", captured["messages"][0][1])
        self.assertIn("Do not switch to another language", captured["messages"][0][1])
        self.assertIn("more thorough user-facing explanation", captured["messages"][0][1])

    def test_conversation_history_is_bounded_before_llm_request(self):
        captured = {}

        class FakeChatOpenAI:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                captured["messages"] = messages
                return SimpleNamespace(content="A concise answer.")

        history = [
            {"role": "user", "content": f"history-{index}-" + "x" * 2500 + f"-end-{index}"}
            for index in range(12)
        ]
        with (
            patch.object(settings, "NVIDIA_API_KEY", "test-key"),
            patch.object(agent, "ChatOpenAI", FakeChatOpenAI),
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={"query": "Please summarize.", "history": history},
            )

        self.assertEqual(response.status_code, 200)
        history_messages = captured["messages"][1:-1]
        self.assertEqual(len(history_messages), 6)
        self.assertTrue(history_messages[0][1].startswith("[Earlier message truncated]"))
        self.assertEqual(len(history_messages[0][1]), agent.MAX_HISTORY_MESSAGE_CHARS)
        self.assertTrue(history_messages[-1][1].endswith("-end-11"))
        self.assertEqual(captured["messages"][-1], ("human", "Please summarize."))

    def test_unsupported_response_language_is_rejected(self):
        response = TestClient(app).post(
            "/api/v1/agent/query",
            json={"query": "How do I prepare soil?", "language": "fr"},
        )
        self.assertEqual(response.status_code, 422)

    def test_non_english_market_question_uses_market_data_path(self):
        with (
            patch.object(settings, "DATA_GOV_API_KEY", ""),
            patch.object(agent, "ChatOpenAI") as llm,
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={
                    "query": "टमाटर का मंडी भाव क्या है?",
                    "language": "hi",
                },
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("DATA_GOV_API_KEY", response.json()["detail"])
        llm.assert_not_called()

    def test_llm_timeout_returns_gateway_timeout_without_sdk_retries(self):
        class TimeoutChatOpenAI:
            def __init__(self, **kwargs):
                self.max_retries = kwargs["max_retries"]

            def invoke(self, messages):
                raise APITimeoutError(
                    request=httpx.Request("POST", "https://llm.example.test/chat")
                )

        with (
            patch.object(settings, "NVIDIA_API_KEY", "test-key"),
            patch.object(agent, "ChatOpenAI", TimeoutChatOpenAI),
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={"query": "How do I prepare soil?"},
            )
        self.assertEqual(response.status_code, 504)
        self.assertIn("timed out", response.json()["detail"])

    def test_query_reports_missing_api_key_without_calling_llm(self):
        def unexpected_llm_call(**kwargs):
            raise AssertionError("LLM must not be constructed without an API key.")

        with (
            patch.object(settings, "NVIDIA_API_KEY", ""),
            patch.object(agent, "ChatOpenAI", unexpected_llm_call),
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={"query": "How do I improve soil health?"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("NVIDIA API key", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
