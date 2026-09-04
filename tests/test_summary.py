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
            "title": "การประชุมพัฒนาระบบ Kintone และ QA HOLD",
            "quick_summary": "สรุปสั้น: ทบทวนแผนงาน Kintone และ QA HOLD",
            "key_topics": ["การพัฒนาระบบ Kintone", "การเปิดตัว QA HOLD", "กรอบเวลา WP-004"],
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
        self.assertEqual(result.title, "การประชุมพัฒนาระบบ Kintone และ QA HOLD")
        self.assertIn("Kintone", result.quick_summary)
        self.assertEqual(len(result.key_topics), 3)
        self.assertIn("การพัฒนาระบบ Kintone", result.key_topics)
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
            "title": "Kintone Adoption Planning",
            "quick_summary": "Quick Summary: Adopted Kintone.",
            "key_topics": ["Kintone Adoption", "Deployment Timeline"],
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
        self.assertEqual(result.title, "Kintone Adoption Planning")
        self.assertEqual(result.quick_summary, "Quick Summary: Adopted Kintone.")
        self.assertEqual(len(result.key_topics), 2)
        self.assertEqual(result.action_items[0].owner, "John")

    def test_action_item_owner_and_due_date_nullability(self):
        fake_response = {
            "title": "Project Task Review",
            "quick_summary": "Quick summary test",
            "key_topics": ["Task Distribution"],
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

    def test_title_mapping_and_no_external_metadata(self):
        provider = FakeSummaryProvider()
        service = MeetingSummaryService(provider=provider)
        result = service.summarize(self.sample_transcript)

        self.assertIsInstance(result.title, str)
        self.assertTrue(len(result.title.strip()) > 0)
        # Title is derived purely from transcript content via SummaryRequest
        last_req = provider.last_request
        self.assertIsNotNone(last_req)
        self.assertEqual(last_req.transcript_text, self.sample_transcript.full_text)

    def test_empty_title_rejection(self):
        bad_resp = {
            "title": "   ",
            "quick_summary": "Quick summary",
            "key_topics": ["Topic 1"],
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
        self.assertIn("title", str(ctx.exception))

    def test_wrong_title_type_rejection(self):
        bad_resp = {
            "title": 12345,  # wrong type
            "quick_summary": "Quick summary",
            "key_topics": ["Topic 1"],
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
        self.assertIn("title", str(ctx.exception))

    def test_key_topics_mapping(self):
        provider = FakeSummaryProvider()
        service = MeetingSummaryService(provider=provider)
        result = service.summarize(self.sample_transcript)

        self.assertIsInstance(result.key_topics, list)
        self.assertEqual(len(result.key_topics), 3)
        self.assertEqual(result.key_topics[0], "การพัฒนาระบบ Kintone")

    def test_wrong_key_topics_type_rejection(self):
        bad_resp = {
            "title": "Valid Title",
            "quick_summary": "Quick summary",
            "key_topics": "not a list",  # wrong type
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
        self.assertIn("key_topics", str(ctx.exception))

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

        self.assertIn("descriptive meeting title", prompt)
        self.assertIn("key topics", prompt)
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
            {"title": "t", "full_summary": "text", "key_topics": [], "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"title": "t", "quick_summary": "text", "key_topics": [], "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"quick_summary": "text", "key_topics": [], "full_summary": "text", "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"title": "t", "quick_summary": "text", "full_summary": "text", "decisions": [], "action_items": [], "risks": [], "follow_up": []},
        ]

        for bad_resp in invalid_responses:
            provider = FakeSummaryProvider(response_dict=bad_resp)
            service = MeetingSummaryService(provider=provider)
            with self.assertRaises(SummaryError):
                service.summarize(self.sample_transcript)

    def test_wrong_type_rejection(self):
        bad_types = [
            {"title": "t", "quick_summary": 123, "key_topics": [], "full_summary": "text", "decisions": [], "action_items": [], "risks": [], "follow_up": []},
            {"title": "t", "quick_summary": "text", "key_topics": [], "full_summary": "text", "decisions": "not a list", "action_items": [], "risks": [], "follow_up": []},
            {"title": "t", "quick_summary": "text", "key_topics": [], "full_summary": "text", "decisions": [], "action_items": "not a list", "risks": [], "follow_up": []},
            {"title": "t", "quick_summary": "text", "key_topics": [], "full_summary": "text", "decisions": [], "action_items": [{"task": 123}], "risks": [], "follow_up": []},
        ]

        for bad_resp in bad_types:
            provider = FakeSummaryProvider(response_dict=bad_resp)
            service = MeetingSummaryService(provider=provider)
            with self.assertRaises(SummaryError):
                service.summarize(self.sample_transcript)

    def test_empty_summary_text_rejection(self):
        bad_resp = {
            "title": "Title",
            "quick_summary": "   ",
            "key_topics": [],
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
