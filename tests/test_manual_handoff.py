"""
Unit tests for WP-005B Manual AI Handoff
"""

import sys
import unittest
from pathlib import Path

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment
from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.manual_handoff import (
    SUMMARY_TEMPLATES,
    ManualHandoffError,
    build_manual_ai_payload,
    extract_json_payload,
    import_manual_ai_result,
)


class TestManualHandoff(unittest.TestCase):

    def setUp(self):
        self.sample_transcript = TranscriptionResult(
            job_id="test_job_manual_001",
            language="th",
            full_text="สวัสดีครับ การประชุมทบทวนแผนงาน Kintone และ QA HOLD อนุมัติกรอบเวลา WP-005B",
            segments=[
                TranscriptionSegment(start=0.0, end=4.0, text="สวัสดีครับ การประชุมทบทวนแผนงาน Kintone และ QA HOLD"),
                TranscriptionSegment(start=4.0, end=8.0, text="อนุมัติกรอบเวลา WP-005B"),
            ],
        )

        self.valid_json_response = """{
  "title": "การประชุมแผนงาน Kintone และ QA HOLD",
  "quick_summary": "สรุปสั้น: ทบทวนแผนงานและอนุมัติ WP-005B",
  "key_topics": ["การพัฒนาระบบ Kintone", "การเปิดตัว QA HOLD", "กรอบเวลา WP-005B"],
  "full_summary": "สรุปรายละเอียด: ที่ประชุมทบทวนแผนงาน Kintone และ QA HOLD โดยผู้เข้าร่วมเห็นชอบร่วมกัน...",
  "decisions": ["อนุมัติกรอบเวลา WP-005B"],
  "action_items": [
    {"task": "ส่งสรุปผลงาน", "owner": "สมชาย", "due_date": "2026-09-15"},
    {"task": "ตรวจสอบความถูกต้อง", "owner": null, "due_date": null}
  ],
  "risks": ["ความล่าช้าในการทดสอบ"],
  "follow_up": ["นัดประชุมติดตามสัปดาห์หน้า"]
}"""

    def test_build_payload_all_templates(self):
        for template_name in SUMMARY_TEMPLATES.keys():
            payload = build_manual_ai_payload(self.sample_transcript, template_name=template_name)
            self.assertIn("ORBIS MEETING AI — MANUAL SUMMARY REQUEST", payload)
            self.assertIn(f"Selected Template: {template_name}", payload)
            self.assertIn(SUMMARY_TEMPLATES[template_name], payload)
            self.assertIn(self.sample_transcript.full_text, payload)

    def test_unknown_template_rejected(self):
        unknown_names = ["Invalid Template", "Custom Template", "Executive Summary", "12345"]
        for bad_name in unknown_names:
            with self.assertRaises(ManualHandoffError) as ctx:
                build_manual_ai_payload(self.sample_transcript, template_name=bad_name)
            self.assertIn(f"Unsupported summary template: {bad_name}", str(ctx.exception))

    def test_build_payload_empty_transcript_rejection(self):
        empty_transcript = TranscriptionResult(
            job_id="empty_job",
            language="th",
            full_text="   ",
            segments=[],
        )
        with self.assertRaises(ManualHandoffError) as ctx:
            build_manual_ai_payload(empty_transcript)
        self.assertIn("empty transcript text", str(ctx.exception))

    def test_extract_json_raw_object_success(self):
        extracted = extract_json_payload(self.valid_json_response)
        self.assertTrue(extracted.startswith("{"))
        self.assertTrue(extracted.endswith("}"))

    def test_extract_json_single_fenced_code_block_success(self):
        fenced_json = f"```json\n{self.valid_json_response}\n```"
        extracted = extract_json_payload(fenced_json)
        self.assertTrue(extracted.startswith("{"))
        self.assertTrue(extracted.endswith("}"))

        fenced_plain = f"```\n{self.valid_json_response}\n```"
        extracted_plain = extract_json_payload(fenced_plain)
        self.assertTrue(extracted_plain.startswith("{"))

    def test_extract_json_arbitrary_prose_rejection(self):
        prose_with_json = f"Here is the summary response:\n{self.valid_json_response}\nHope this helps!"
        with self.assertRaises(ManualHandoffError) as ctx1:
            extract_json_payload(prose_with_json)
        self.assertIn("Invalid AI result format", str(ctx1.exception))

        prose_with_fenced = f"Here is the result:\n```json\n{self.valid_json_response}\n```"
        with self.assertRaises(ManualHandoffError) as ctx2:
            extract_json_payload(prose_with_fenced)
        self.assertIn("Invalid AI result format", str(ctx2.exception))

    def test_extract_json_empty_rejection(self):
        with self.assertRaises(ManualHandoffError):
            extract_json_payload("   ")
        with self.assertRaises(ManualHandoffError):
            extract_json_payload(None)

    def test_import_manual_ai_result_success(self):
        result = import_manual_ai_result(
            raw_input_text=self.valid_json_response,
            job_id="test_job_manual_001",
            language="th",
        )
        self.assertIsInstance(result, MeetingSummaryResult)
        self.assertEqual(result.job_id, "test_job_manual_001")
        self.assertEqual(result.title, "การประชุมแผนงาน Kintone และ QA HOLD")
        self.assertEqual(len(result.key_topics), 3)

    def test_import_manual_ai_result_malformed_json_rejection(self):
        malformed = "```json\n{ \"invalid_json\": syntax_error }\n```"
        with self.assertRaises(ManualHandoffError) as ctx:
            import_manual_ai_result(malformed)
        self.assertIn("Invalid JSON format", str(ctx.exception))

    def test_import_manual_ai_result_schema_validation_rejection(self):
        missing_title_json = """{
  "quick_summary": "Missing title test",
  "key_topics": [],
  "full_summary": "Full summary",
  "decisions": [],
  "action_items": [],
  "risks": [],
  "follow_up": []
}"""
        with self.assertRaises(ManualHandoffError) as ctx:
            import_manual_ai_result(missing_title_json)
        self.assertIn("Schema Validation Failure", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
