"""
Unit Tests for WP-013 Ollama Structured Local Summary Adapter
"""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.ollama_structured_adapter import (
    ORBIS_SUMMARY_JSON_SCHEMA,
    query_ollama_structured_api,
    main as adapter_main,
)
from orbis_meeting.auto_summary import (
    LocalCommandSummaryProvider,
    AutomaticSummaryService,
    parse_automatic_summary_response,
)
from orbis_meeting.summary import MeetingSummaryResult


class TestOllamaStructuredAdapter(unittest.TestCase):

    def setUp(self):
        self.sample_thai_prompt = "กรุณาสรุปการประชุมเรื่อง Kintone Workflow ระบบใหม่"
        self.valid_ollama_model_response = json.dumps({
            "title": "การประชุม Kintone Workflow",
            "quick_summary": "สรุปการปรับปรุง workflow ระบบ Kintone",
            "key_topics": ["ระบบ Kintone", "การทดสอบ Workflow"],
            "full_summary": "ทีมงานได้หารือเรื่องการพัฒนาระบบ Kintone Workflow และกำหนดวันเปิดใช้งาน",
            "decisions": ["อนุมัติแผนการปรับปรุงระบบ"],
            "action_items": [
                {
                    "task": "ทดสอบระบบขั้นสุดท้าย",
                    "owner": "คุณสมชาย",
                    "due_date": "2026-09-15",
                }
            ],
            "risks": ["ความล่าช้าในการทดสอบ"],
            "follow_up": ["ประชุมติดตามผลสัปดาห์หน้า"],
        }, ensure_ascii=False)

        self.valid_ollama_envelope = json.dumps({
            "model": "qwen3:4b",
            "created_at": "2026-09-05T08:00:00Z",
            "response": self.valid_ollama_model_response,
            "done": True,
        }, ensure_ascii=False)

    def test_query_ollama_structured_api_payload_and_utf8(self):
        """Test query_ollama_structured_api builds correct payload with think=false, stream=false, temp=0, schema, and UTF-8."""
        mock_response = MagicMock()
        mock_response.read.return_value = self.valid_ollama_envelope.encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            resp_text = query_ollama_structured_api(
                prompt=self.sample_thai_prompt,
                model="qwen3:4b",
                endpoint="http://127.0.0.1:11434/api/generate",
                timeout=120.0,
            )

            self.assertEqual(resp_text, self.valid_ollama_model_response)

            # Inspect request sent to urlopen
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/generate")
            self.assertEqual(req.headers["Content-type"], "application/json; charset=utf-8")

            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "qwen3:4b")
            self.assertEqual(payload["prompt"], self.sample_thai_prompt)
            self.assertFalse(payload["stream"])
            self.assertFalse(payload["think"])
            self.assertEqual(payload["options"]["temperature"], 0)
            self.assertEqual(payload["format"], ORBIS_SUMMARY_JSON_SCHEMA)

    def test_json_schema_contains_required_orbis_fields(self):
        """Test that ORBIS_SUMMARY_JSON_SCHEMA represents exact V1 summary contract."""
        props = ORBIS_SUMMARY_JSON_SCHEMA["properties"]
        required_fields = ORBIS_SUMMARY_JSON_SCHEMA["required"]

        for field in ["title", "quick_summary", "key_topics", "full_summary", "decisions", "action_items", "risks", "follow_up"]:
            self.assertIn(field, props)
            self.assertIn(field, required_fields)

        action_props = props["action_items"]["items"]["properties"]
        self.assertIn("task", action_props)
        self.assertIn("owner", action_props)
        self.assertIn("due_date", action_props)

    def test_main_cli_stdout_raw_response_only(self):
        """Test main CLI reads stdin and outputs raw model response string to stdout without logs or fences."""
        mock_response = MagicMock()
        mock_response.read.return_value = self.valid_ollama_envelope.encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("sys.stdin", io.StringIO(self.sample_thai_prompt)):
                out_capture = io.StringIO()
                err_capture = io.StringIO()
                with patch("sys.stdout", out_capture), patch("sys.stderr", err_capture):
                    exit_code = adapter_main(["--model", "qwen3:4b"])

                self.assertEqual(exit_code, 0)
                self.assertEqual(err_capture.getvalue(), "")
                stdout_text = out_capture.getvalue()
                self.assertEqual(stdout_text, self.valid_ollama_model_response)
                # Verify raw JSON format without markdown fences or surrounding prose
                self.assertTrue(stdout_text.startswith("{"))
                self.assertTrue(stdout_text.endswith("}"))

    def test_empty_stdin_prompt_fails_safely(self):
        """Test that empty prompt in stdin returns exit code 1 and writes error to stderr."""
        with patch("sys.stdin", io.StringIO("   ")):
            out_capture = io.StringIO()
            err_capture = io.StringIO()
            with patch("sys.stdout", out_capture), patch("sys.stderr", err_capture):
                exit_code = adapter_main([])

            self.assertEqual(exit_code, 1)
            self.assertEqual(out_capture.getvalue(), "")
            self.assertIn("Prompt read from stdin is empty", err_capture.getvalue())

    def test_http_error_fails_safely(self):
        """Test handling of HTTP error from Ollama endpoint."""
        import urllib.error
        err = urllib.error.HTTPError(
            url="http://127.0.0.1:11434/api/generate",
            code=500,
            msg="Internal Error",
            hdrs={},
            fp=io.BytesIO(b"Model failed to load"),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with patch("sys.stdin", io.StringIO(self.sample_thai_prompt)):
                err_capture = io.StringIO()
                with patch("sys.stderr", err_capture):
                    exit_code = adapter_main([])

                self.assertEqual(exit_code, 1)
                self.assertIn("HTTP 500", err_capture.getvalue())

    def test_connection_error_fails_safely(self):
        """Test handling of connection error when local Ollama API is not running."""
        import urllib.error
        err = urllib.error.URLError(reason="Connection refused")
        with patch("urllib.request.urlopen", side_effect=err):
            with patch("sys.stdin", io.StringIO(self.sample_thai_prompt)):
                err_capture = io.StringIO()
                with patch("sys.stderr", err_capture):
                    exit_code = adapter_main([])

                self.assertEqual(exit_code, 1)
                self.assertIn("Failed to connect to local Ollama API", err_capture.getvalue())

    def test_malformed_envelope_fails_safely(self):
        """Test handling of malformed envelope JSON or missing response field."""
        bad_envelope = json.dumps({"status": "ok"}).encode("utf-8")
        mock_response = MagicMock()
        mock_response.read.return_value = bad_envelope
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("sys.stdin", io.StringIO(self.sample_thai_prompt)):
                err_capture = io.StringIO()
                with patch("sys.stderr", err_capture):
                    exit_code = adapter_main([])

                self.assertEqual(exit_code, 1)
                self.assertIn("response field is missing or empty", err_capture.getvalue())

    def test_end_to_end_integration_with_local_command_provider(self):
        """Test end-to-end integration via LocalCommandSummaryProvider & AutomaticSummaryService."""
        mock_response = MagicMock()
        mock_response.read.return_value = self.valid_ollama_envelope.encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        command = [sys.executable, "-m", "orbis_meeting.ollama_structured_adapter", "--model", "qwen3:4b"]

        def fake_subprocess_run(cmd, input, capture_output, text, timeout, shell, encoding, errors):
            out_cap = io.StringIO()
            err_cap = io.StringIO()
            with patch("sys.stdin", io.StringIO(input)), patch("sys.stdout", out_cap), patch("sys.stderr", err_cap):
                with patch("urllib.request.urlopen", return_value=mock_response):
                    ret_code = adapter_main(cmd[3:])
            res = MagicMock()
            res.returncode = ret_code
            res.stdout = out_cap.getvalue()
            res.stderr = err_cap.getvalue()
            return res

        with patch("subprocess.run", side_effect=fake_subprocess_run):
            provider = LocalCommandSummaryProvider(command=command)
            service = AutomaticSummaryService(provider=provider)

            transcript = "สวัสดีครับ ขอเปิดการประชุมเพื่อหารือเรื่อง Kintone Workflow ระบบใหม่"
            summary_result = service.summarize(transcript_text=transcript, job_id="test_job_01", language="th")

            self.assertIsInstance(summary_result, MeetingSummaryResult)
            self.assertEqual(summary_result.job_id, "test_job_01")
            self.assertEqual(summary_result.title, "การประชุม Kintone Workflow")
            self.assertEqual(len(summary_result.action_items), 1)
            self.assertEqual(summary_result.action_items[0].task, "ทดสอบระบบขั้นสุดท้าย")


if __name__ == "__main__":
    unittest.main()
