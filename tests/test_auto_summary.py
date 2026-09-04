"""
Unit tests for Automatic Local Summary Engine (WP-009)
"""

import sys
import unittest
import json
from typing import Dict, Any

from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.auto_summary import (
    AutomaticSummaryError,
    LocalCommandSummaryProvider,
    AutomaticSummaryService,
)


class FakeProvider:
    """Test double provider returning predefined output or raising an exception."""

    def __init__(self, response_text: str = "", raise_error: bool = False):
        self.response_text = response_text
        self.raise_error = raise_error
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.raise_error:
            raise AutomaticSummaryError("Fake provider execution failure.")
        return self.response_text


def create_valid_summary_json_dict() -> Dict[str, Any]:
    return {
        "title": "Project Sync Meeting",
        "quick_summary": "Discussed Q3 milestone progress and database migration plan.",
        "key_topics": ["Q3 Milestones", "Database Migration"],
        "full_summary": "The team reviewed Q3 objectives. The database migration is scheduled for next Friday.",
        "decisions": ["Proceed with postgresql upgrade"],
        "action_items": [
            {
                "task": "Prepare migration scripts",
                "owner": "Dev Team",
                "due_date": "2026-09-10",
            }
        ],
        "risks": ["Downtime during migration"],
        "follow_up": ["Check backup integrity"],
    }


class TestLocalCommandSummaryProvider(unittest.TestCase):

    def test_empty_command_raises_value_error(self):
        with self.assertRaises(ValueError):
            LocalCommandSummaryProvider([])

    def test_generate_success(self):
        # Execute Python code that returns valid JSON via stdout
        json_str = json.dumps(create_valid_summary_json_dict())
        script = f"import sys; sys.stdout.write({repr(json_str)})"
        provider = LocalCommandSummaryProvider([sys.executable, "-c", script])
        result = provider.generate("test prompt")
        self.assertIn("Project Sync Meeting", result)

    def test_generate_max_input_chars_exceeded(self):
        provider = LocalCommandSummaryProvider(
            [sys.executable, "-c", "print('ok')"],
            max_input_chars=10,
        )
        with self.assertRaises(AutomaticSummaryError) as ctx:
            provider.generate("This prompt is way longer than ten characters!")
        self.assertIn("max_input_chars", str(ctx.exception))

    def test_generate_non_zero_exit(self):
        provider = LocalCommandSummaryProvider(
            [sys.executable, "-c", "import sys; sys.stderr.write('fatal'); sys.exit(1)"]
        )
        with self.assertRaises(AutomaticSummaryError) as ctx:
            provider.generate("hello")
        self.assertIn("non-zero exit code 1", str(ctx.exception))
        self.assertIn("fatal", str(ctx.exception))

    def test_generate_command_timeout(self):
        script = "import time; time.sleep(2.0)"
        provider = LocalCommandSummaryProvider(
            [sys.executable, "-c", script],
            timeout_seconds=0.1,
        )
        with self.assertRaises(AutomaticSummaryError) as ctx:
            provider.generate("hello")
        self.assertIn("timed out", str(ctx.exception))

    def test_generate_executable_not_found(self):
        provider = LocalCommandSummaryProvider(["non_existent_executable_123456789"])
        with self.assertRaises(AutomaticSummaryError) as ctx:
            provider.generate("hello")
        self.assertIn("not found", str(ctx.exception))

    def test_generate_empty_output(self):
        provider = LocalCommandSummaryProvider([sys.executable, "-c", "pass"])
        with self.assertRaises(AutomaticSummaryError) as ctx:
            provider.generate("hello")
        self.assertIn("empty output", str(ctx.exception))


class TestAutomaticSummaryService(unittest.TestCase):

    def test_summarize_no_provider_raises(self):
        service = AutomaticSummaryService(provider=None)
        with self.assertRaises(AutomaticSummaryError) as ctx:
            service.summarize("Transcript text here")
        self.assertIn("No summary provider configured", str(ctx.exception))

    def test_summarize_success_raw_json(self):
        json_dict = create_valid_summary_json_dict()
        json_str = json.dumps(json_dict)
        provider = FakeProvider(response_text=json_str)
        service = AutomaticSummaryService(provider=provider, template_name="General Meeting")

        result = service.summarize(transcript_text="Cleaned meeting text", job_id="job_001")
        self.assertIsInstance(result, MeetingSummaryResult)
        self.assertEqual(result.title, "Project Sync Meeting")
        self.assertEqual(len(result.key_topics), 2)
        self.assertEqual(len(result.action_items), 1)

    def test_summarize_success_fenced_json(self):
        json_dict = create_valid_summary_json_dict()
        fenced_json = f"```json\n{json.dumps(json_dict)}\n```"
        provider = FakeProvider(response_text=fenced_json)
        service = AutomaticSummaryService(provider=provider, template_name="Project Meeting")

        result = service.summarize(transcript_text="Project transcript", job_id="job_002")
        self.assertIsInstance(result, MeetingSummaryResult)
        self.assertEqual(result.title, "Project Sync Meeting")
        self.assertIn("TEMPLATE FOCUS: Project Meeting", provider.last_prompt)

    def test_summarize_invalid_template(self):
        provider = FakeProvider(response_text="{}")
        service = AutomaticSummaryService(provider=provider, template_name="Invalid Template Name")
        with self.assertRaises(AutomaticSummaryError) as ctx:
            service.summarize("Transcript")
        self.assertIn("Failed to build summary prompt", str(ctx.exception))

    def test_summarize_invalid_json(self):
        provider = FakeProvider(response_text="This is plain text without JSON object.")
        service = AutomaticSummaryService(provider=provider)
        with self.assertRaises(AutomaticSummaryError) as ctx:
            service.summarize("Transcript")
        self.assertIn("Failed to parse/validate AI summary result", str(ctx.exception))

    def test_summarize_schema_validation_failure(self):
        incomplete_json = json.dumps({"title": "Incomplete Summary"})
        provider = FakeProvider(response_text=incomplete_json)
        service = AutomaticSummaryService(provider=provider)
        with self.assertRaises(AutomaticSummaryError) as ctx:
            service.summarize("Transcript")
        self.assertIn("Schema Validation Failure", str(ctx.exception))

    def test_summarize_provider_error(self):
        provider = FakeProvider(raise_error=True)
        service = AutomaticSummaryService(provider=provider)
        with self.assertRaises(AutomaticSummaryError) as ctx:
            service.summarize("Transcript")
        self.assertIn("Fake provider execution failure", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
