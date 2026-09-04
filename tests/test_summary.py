"""
Unit tests for WP-004 Meeting Summary Foundation
"""

import sys
import unittest
from typing import Dict, Any, Optional
from pathlib import Path

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment
from orbis_meeting.summary import (
    ActionItem,
    MeetingSummaryResult,
    MeetingSummaryService,
    SummaryError,
    SummaryProvider,
    SummaryRequest,
    build_summary_prompt,
    parse_and_validate_summary_response,
)


class FakeSummaryProvider(SummaryProvider):
    """
    Fake summary provider test double for WP-004 testing.
    No network calls or API keys required.
    """

    def __init__(
        self,
        response_dict: Optional[Dict[str, Any]] = None,
        raise_exception: Optional[Exception] = None,
    ):
        self.response_dict = response_dict
        self.raise_exception = raise_exception
        self.last_request: Optional[SummaryRequest] = None

    def summarize(self, request: SummaryRequest) -> Dict[str, Any]:
        self.last_request = request
        if self.raise_exception:
            raise self.raise_exception
        if self.response_dict is not None:
            return self.response_dict
        return {
            "quick_summary": "สรุปสั้น: ทบทวนแผนงาน Kintone และ QA HOLD",
            "full_summary": "สรุปละเอียด: ที่ประชุมหารือเรื่องการพัฒนาระบบ Kintone และเปิดตัว QA HOLD...",
            "decisions": ["อนุมัติกรอบเวลา WP-004"],
            "action_items": [
                {"task": "ส่งเอกสารสรุป", "owner": "สมชาย", "due_date": "2026-09-10"},
                {"task": "ตรวจสอบระบบ", "owner": None, "due_date": None},
            ],
            "risks": ["ความเสี่ยงด้านกรอบเวลา"],
            "follow_up": ["ประชุมติดตามงานสัปดาห์หน้า"],
        }


class TestSummary(unittest.TestCase):

    def setUp(self):
        self.sample_transcript = TranscriptionResult(
            job_id="test_job_summary_001",
            language="th",
            full_text="สวัสดีครับ การประชุมทบทวนแผนงาน Kintone และ QA HOLD อนุมัติกรอบเวลา WP-004",
            segments=[
                TranscriptionSegment(start=0.0, end=4.0, text="สวัสดีครับ การประชุมทบทวนแผนงาน Kintone และ QA HOLD"),
                TranscriptionSegment(start=4.0, end=8.0, text="อนุมัติกรอบเวลา WP-004"),
            ],
        )

    def test_thai_summary_response_mapping(self):
        provider = FakeSummaryProvider()
        service = MeetingSummaryService(provider=provider)

        result = service.summarize(self.sample_transcript)
        self.assertIsInstance(result, MeetingSummaryResult)
        self.assertEqual(result.job_id, "test_job_summary_001")
        self.assertEqual(result.language, "th")
        self.assertIn("Kintone", result.quick_summary)
        self.assertEqual(len(result.decisions), 1)
        self.assertEqual(result.decisions[0], "อนุมัติกรอบเวลา WP-004")

    def test_english_summary_response_mapping(self):
        en_transcript = TranscriptionResult(
            job_id="test_job_en",
            language="en",
            full_text="Welcome to the meeting. We decided to adopt Kintone.",
            segments=[TranscriptionSegment(start=0.0, end=5.0, text="Welcome to the meeting. We decided to adopt Kintone.")],
        )
        en_response = {
            "quick_summary": "Quick Summary: Adopted Kintone.",
            "full_summary": "Full Summary: Detailed discussion on adopting Kintone.",
            "decisions": ["Adopt Kintone"],
            "action_items": [{"task": "Deploy Kintone", "owner": "John", "due_date": "2026-09-15"}],
            "risks": ["Migration risk"],
            "follow_up": ["Sync with IT next Tuesday"],
        }
        provider = FakeSummaryProvider(response_dict=en_response)
        service = MeetingSummaryService(provider=provider)

        result = service.summarize(en_transcript)
        self.assertEqual(result.language, "en")
        self.assertEqual(result.quick_summary, "Quick Summary: Adopted Kintone.")
        self.assertEqual(result.action_items[0].owner, "John")

    def test_action_item_owner_and_due_date_nullability(self):
        fake_response = {
            "quick_summary": "Quick summary test",
            "full_summary": "Full summary test",
            "decisions": [],
            "action_items": [
                {"task": "Task with owner and date", "owner": "Alice", "due_date": "2026-10-01"},
                {"task": "Task without owner", "owner": None, "due_date": "2026-10-02"},
                {"task": "Task without date", "owner": "Bob", "due_date": None},
                {"task": "Task with neither", "owner": None, "due_date": None},
            ],
            "risks": [],
            "follow_up": [],
        }
        provider = FakeSummaryProvider(response_dict=fake_response)
        service = MeetingSummaryService(provider=provider)
        result = service.summarize(self.sample_transcript)

        items = result.action_items
        self.assertEqual(len(items), 4)

        self.assertEqual(items[0].owner, "Alice")
        self.assertEqual(items[0].due_date, "2026-10-01")

        self.assertIsNone(items[1].owner)
        self.assertEqual(items[1].due_date, "2026-10-02")

        self.assertEqual(items[2].owner, "Bob")
        self.assertIsNone(items[2].due_date)

        self.assertIsNone(items[3].owner)
        self.assertIsNone(items[3].due_date)

    def test_privacy_and_payload_isolation(self):
        provider = FakeSummaryProvider()
        service = MeetingSummaryService(provider=provider)
        service.summarize(self.sample_transcript)

        last_req = provider.last_request
        self.assertIsNotNone(last_req)
        self.assertEqual(last_req.job_id, self.sample_transcript.job_id)
        self.assertEqual(last_req.transcript_text, self.sample_transcript.full_text)

        req_dict = last_req.to_dict()
        self.assertNotIn("audio", req_dict)
        self.assertNotIn("original_path", req_dict)
        self.assertNotIn("file_path", req_dict)

    def test_prompt_rules_verification(self):
        prompt = build_summary_prompt("th")

        # Confirm rules required by AC-19, AC-20, AC-21, AC-22
        self.assertIn("Do not fabricate", prompt)
        self.assertIn("set owner to null", prompt)
        self.assertIn("set due_date to null", prompt)
        self.assertIn("JSON schema", prompt)
        self.assertNotIn("think step by step", prompt.lower())

    def test_input_transcription_result_unmutated(self):
        initial_full_text = self.sample_transcript.full_text
        initial_job_id = self.sample_transcript.job_id

        provider = FakeSummaryProvider()
        service = MeetingSummaryService(provider=provider)
        service.summarize(self.sample_transcript)

        self.assertEqual(self.sample_transcript.full_text, initial_full_text)
        self.assertEqual(self.sample_transcript.job_id, initial_job_id)

    def test_missing_required_field_rejection(self):
        invalid_responses = [
            {"full_summary": "text", "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"quick_summary": "text", "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"quick_summary": "text", "full_summary": "text", "action_items": [], "risks": [], "follow_up": []},
            {"quick_summary": "text", "full_summary": "text", "decisions": [], "risks": [], "follow_up": []},
        ]

        for bad_resp in invalid_responses:
            provider = FakeSummaryProvider(response_dict=bad_resp)
            service = MeetingSummaryService(provider=provider)
            with self.assertRaises(SummaryError):
                service.summarize(self.sample_transcript)

    def test_wrong_type_rejection(self):
        bad_types = [
            {"quick_summary": 123, "full_summary": "text", "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"quick_summary": "text", "full_summary": "text", "decisions": "not a list", "action_items": [], "risks": [], "follow_up": []},
            {"quick_summary": "text", "full_summary": "text", "decisions": [], "action_items": "not a list", "risks": [], "follow_up": []},
            {"quick_summary": "text", "full_summary": "text", "decisions": [], "action_items": [{"task": 123}], "risks": [], "follow_up": []},
        ]

        for bad_resp in bad_types:
            provider = FakeSummaryProvider(response_dict=bad_resp)
            service = MeetingSummaryService(provider=provider)
            with self.assertRaises(SummaryError):
                service.summarize(self.sample_transcript)

    def test_empty_summary_text_rejection(self):
        bad_resp = {
            "quick_summary": "   ",
            "full_summary": "Full summary",
            "decisions": [],
            "action_items": [],
            "risks": [],
            "follow_up": [],
        }
        provider = FakeSummaryProvider(response_dict=bad_resp)
        service = MeetingSummaryService(provider=provider)
        with self.assertRaises(SummaryError) as ctx:
            service.summarize(self.sample_transcript)
        self.assertIn("quick_summary", str(ctx.exception))

    def test_provider_exception_handling(self):
        provider = FakeSummaryProvider(raise_exception=RuntimeError("Simulated provider outage"))
        service = MeetingSummaryService(provider=provider)
        with self.assertRaises(SummaryError) as ctx:
            service.summarize(self.sample_transcript)
        self.assertIn("provider execution failed", str(ctx.exception))

    def test_empty_input_transcript_rejection(self):
        empty_transcript = TranscriptionResult(
            job_id="empty_job",
            language="th",
            full_text="  ",
            segments=[],
        )
        provider = FakeSummaryProvider()
        service = MeetingSummaryService(provider=provider)
        with self.assertRaises(SummaryError) as ctx:
            service.summarize(empty_transcript)
        self.assertIn("empty transcript", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
