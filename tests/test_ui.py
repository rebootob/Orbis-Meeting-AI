"""
Unit tests for WP-005A & WP-005B Local Desktop UI Shell and Controller Methods
"""

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.audio_intake import AudioJobMetadata
from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment, TranscriptionError
from orbis_meeting.text_cleanup import TextCleanupError
from orbis_meeting.manual_handoff import ManualHandoffError
from orbis_meeting.ui import OrbisMeetingController


class FakeTranscriptionService:
    def __init__(self, raw_text="สวัสดีครับ คินโทน", raise_exception=None):
        self.raw_text = raw_text
        self.raise_exception = raise_exception
        self.transcribe_called = False

    def transcribe(self, metadata: AudioJobMetadata) -> TranscriptionResult:
        self.transcribe_called = True
        if self.raise_exception:
            raise self.raise_exception
        return TranscriptionResult(
            job_id=metadata.job_id,
            language="th",
            full_text=self.raw_text,
            segments=[TranscriptionSegment(start=0.0, end=4.0, text=self.raw_text)],
        )


class FakeCleanupService:
    def __init__(self, cleaned_text="สวัสดีครับ Kintone", raise_exception=None):
        self.cleaned_text = cleaned_text
        self.raise_exception = raise_exception

    def clean_transcript(self, raw_result: TranscriptionResult) -> TranscriptionResult:
        if self.raise_exception:
            raise self.raise_exception
        return TranscriptionResult(
            job_id=raw_result.job_id,
            language=raw_result.language,
            full_text=self.cleaned_text,
            segments=[TranscriptionSegment(start=0.0, end=4.0, text=self.cleaned_text)],
        )


class TestUIController(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

        self.sample_mp3 = self.test_dir / "test_audio.mp3"
        self.sample_mp3.write_bytes(b"dummy mp3 content for UI testing 12345")

        self.status_messages: List[str] = []
        self.error_messages: List[str] = []
        self.displayed_metadata: Optional[AudioJobMetadata] = None
        self.displayed_transcript: Optional[str] = None
        self.completion_flag: bool = False

        self.fake_transcription = FakeTranscriptionService()
        self.fake_cleanup = FakeCleanupService()
        self.event_queue: queue.Queue = queue.Queue()

        self.controller = OrbisMeetingController(
            transcription_service=self.fake_transcription,
            cleanup_service=self.fake_cleanup,
            event_queue=self.event_queue,
            status_callback=lambda msg: self.status_messages.append(msg),
            metadata_callback=lambda meta: setattr(self, "displayed_metadata", meta),
            transcript_callback=lambda text: setattr(self, "displayed_transcript", text),
            error_callback=lambda err: self.error_messages.append(err),
            on_complete_callback=lambda: setattr(self, "completion_flag", True),
        )

        self.valid_ai_json = """
        {
          "title": "การประชุม Kintone",
          "quick_summary": "สรุปสั้น",
          "key_topics": ["Topic 1"],
          "full_summary": "สรุปละเอียด",
          "decisions": ["Decision 1"],
          "action_items": [{"task": "Task 1", "owner": "Owner 1", "due_date": "2026-09-20"}],
          "risks": ["Risk 1"],
          "follow_up": ["Follow up 1"]
        }
        """

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_ready_state(self):
        self.assertEqual(self.controller.state, "READY")
        self.assertFalse(self.controller.is_processing)
        self.assertIsNone(self.controller.current_metadata)
        self.assertTrue(any("READY" in msg for msg in self.status_messages))

    def test_accepted_audio_selection_and_metadata_display(self):
        meta = self.controller.select_audio_file(self.sample_mp3)

        self.assertIsNotNone(meta)
        self.assertEqual(self.controller.state, "AUDIO_SELECTED")
        self.assertEqual(meta.filename, "test_audio.mp3")
        self.assertEqual(meta.extension, ".mp3")
        self.assertGreater(meta.file_size_bytes, 0)
        self.assertEqual(self.displayed_metadata, meta)
        self.assertTrue(any("AUDIO_SELECTED" in msg for msg in self.status_messages))

    def test_cancelled_file_selection_behavior(self):
        self.controller.select_audio_file(self.sample_mp3)
        initial_meta = self.controller.current_metadata

        meta1 = self.controller.select_audio_file(None)
        self.assertEqual(meta1, initial_meta)

        meta2 = self.controller.select_audio_file("")
        self.assertEqual(meta2, initial_meta)

        self.assertEqual(self.controller.state, "AUDIO_SELECTED")

    def test_invalid_unsupported_file_rejection(self):
        invalid_file = self.test_dir / "document.pdf"
        invalid_file.write_bytes(b"dummy pdf content")

        meta = self.controller.select_audio_file(invalid_file)
        self.assertIsNone(meta)
        self.assertEqual(self.controller.state, "ERROR")
        self.assertTrue(len(self.error_messages) > 0)
        self.assertIn("Unsupported audio file extension", self.error_messages[0])

    def test_transcription_execution_and_cleaned_transcript_display(self):
        self.controller.select_audio_file(self.sample_mp3)

        started = self.controller.start_transcription()
        self.assertTrue(started)

        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=2.0)

        self.assertEqual(self.controller.state, "COMPLETED")
        self.assertFalse(self.controller.is_processing)
        self.assertTrue(self.fake_transcription.transcribe_called)
        self.assertEqual(self.displayed_transcript, "สวัสดีครับ Kintone")
        self.assertTrue(self.completion_flag)

    def test_duplicate_transcribe_blocked_during_processing(self):
        self.controller.select_audio_file(self.sample_mp3)

        self.controller.is_processing = True

        started_again = self.controller.start_transcription()
        self.assertFalse(started_again)

    def test_queue_handoff_success_flow(self):
        events_before = []
        while not self.event_queue.empty():
            events_before.append(self.event_queue.get_nowait())

        self.controller.select_audio_file(self.sample_mp3)
        self.controller.start_transcription()

        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=2.0)

        queued_events = []
        while not self.event_queue.empty():
            queued_events.append(self.event_queue.get_nowait())

        event_types = [evt[0] for evt in queued_events]
        self.assertIn("METADATA", event_types)
        self.assertIn("TRANSCRIPT", event_types)
        self.assertIn("STATUS", event_types)
        self.assertIn("COMPLETE", event_types)

        transcript_payload = [evt[1] for evt in queued_events if evt[0] == "TRANSCRIPT"][0]
        self.assertEqual(transcript_payload, "สวัสดีครับ Kintone")

    def test_copy_ai_payload_without_transcript_rejection(self):
        with self.assertRaises(ManualHandoffError) as ctx:
            self.controller.copy_ai_payload()
        self.assertIn("No cleaned transcript available", str(ctx.exception))

    def test_copy_ai_payload_success(self):
        self.controller.select_audio_file(self.sample_mp3)
        self.controller.start_transcription()
        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=2.0)

        payload = self.controller.copy_ai_payload(template_name="Management Meeting")
        self.assertIn("TEMPLATE FOCUS: Management Meeting", payload)
        self.assertIn("สวัสดีครับ Kintone", payload)

    def test_import_ai_result_success(self):
        self.controller.select_audio_file(self.sample_mp3)
        self.controller.start_transcription()
        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=2.0)

        summary_result = self.controller.import_ai_result(self.valid_ai_json)
        self.assertIsNotNone(summary_result)
        self.assertEqual(summary_result.title, "การประชุม Kintone")
        self.assertEqual(self.controller.current_summary_result, summary_result)

    def test_original_audio_file_unmodified(self):
        initial_content = self.sample_mp3.read_bytes()
        initial_stat = self.sample_mp3.stat()

        self.controller.select_audio_file(self.sample_mp3)
        self.controller.start_transcription()

        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=2.0)

        post_content = self.sample_mp3.read_bytes()
        post_stat = self.sample_mp3.stat()

        self.assertEqual(post_content, initial_content)
        self.assertEqual(post_stat.st_size, initial_stat.st_size)


if __name__ == "__main__":
    unittest.main()
