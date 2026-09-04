"""
Unit tests for WP-007 Google Drive Multi-Device Workflow Module
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.audio_intake import validate_and_intake_audio
from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment, TranscriptionError
from orbis_meeting.summary import MeetingSummaryResult, ActionItem
from orbis_meeting.export_package import ExportPackageResult
from orbis_meeting.drive_workflow import (
    DriveWorkflowError,
    DriveWorkflowPaths,
    initialize_workflow_root,
    discover_inbox_audio,
    is_file_stable,
    claim_inbox_audio,
    complete_workflow_job,
    fail_workflow_job,
)
from orbis_meeting.ui import OrbisMeetingController


class TestDriveWorkflowModule(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name) / "GoogleDrive_OrbisRoot"
        self.root_dir.mkdir()

        self.paths = initialize_workflow_root(self.root_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialize_workflow_root_creates_four_folders(self):
        self.assertTrue(self.paths.inbox.exists())
        self.assertTrue(self.paths.processing.exists())
        self.assertTrue(self.paths.completed.exists())
        self.assertTrue(self.paths.error.exists())

        self.assertEqual(self.paths.inbox.name, "01_Inbox")
        self.assertEqual(self.paths.processing.name, "02_Processing")
        self.assertEqual(self.paths.completed.name, "03_Completed")
        self.assertEqual(self.paths.error.name, "99_Error")

    def test_initialize_workflow_root_rejections(self):
        # Empty root
        with self.assertRaises(DriveWorkflowError):
            initialize_workflow_root("")

        # Non-existent root
        with self.assertRaises(DriveWorkflowError):
            initialize_workflow_root(self.root_dir / "non_existent")

        # Root is a file
        file_root = self.root_dir / "file.txt"
        file_root.write_text("hello")
        with self.assertRaises(DriveWorkflowError):
            initialize_workflow_root(file_root)

    def test_discover_inbox_audio_filtering_and_ordering(self):
        # Create audio files with different extensions and timestamps
        f1 = self.paths.inbox / "file1_old.mp3"
        f1.write_bytes(b"dummy mp3 data 1")

        f2 = self.paths.inbox / "file2_new.WAV"
        f2.write_bytes(b"dummy wav data 2")

        f3 = self.paths.inbox / "file3_m4a.M4A"
        f3.write_bytes(b"dummy m4a data 3")

        # Create ignored files
        (self.paths.inbox / "notes.txt").write_text("some notes")
        (self.paths.inbox / ".hidden.mp3").write_bytes(b"hidden")
        (self.paths.inbox / "zero_byte.mp3").write_bytes(b"")
        (self.paths.inbox / "subfolder").mkdir()

        discovered = discover_inbox_audio(self.paths)
        self.assertEqual(len(discovered), 3)

        filenames = [p.name for p in discovered]
        self.assertIn("file1_old.mp3", filenames)
        self.assertIn("file2_new.WAV", filenames)
        self.assertIn("file3_m4a.M4A", filenames)
        self.assertNotIn("notes.txt", filenames)
        self.assertNotIn(".hidden.mp3", filenames)
        self.assertNotIn("zero_byte.mp3", filenames)

    def test_is_file_stable(self):
        audio = self.paths.inbox / "sample.mp3"
        audio.write_bytes(b"sample audio data")

        # Stable with check_interval_seconds = 0
        self.assertTrue(is_file_stable(audio, check_interval_seconds=0.0))

        # Zero byte file unstable
        zero_file = self.paths.inbox / "zero.mp3"
        zero_file.write_bytes(b"")
        self.assertFalse(is_file_stable(zero_file, check_interval_seconds=0.0))

        # Non-existent file unstable
        self.assertFalse(is_file_stable(self.paths.inbox / "missing.mp3", check_interval_seconds=0.0))

    def test_is_file_stable_with_size_and_mtime_changes(self):
        audio = self.paths.inbox / "sample.mp3"
        audio.write_bytes(b"sample audio data 12345")

        # Stable file
        self.assertTrue(is_file_stable(audio, check_interval_seconds=0.1, sleep_fn=lambda s: None))

        # Size change during sleep_fn
        def change_size(s):
            audio.write_bytes(b"sample audio data 12345 appended bytes")

        self.assertFalse(is_file_stable(audio, check_interval_seconds=0.1, sleep_fn=change_size))

        # Mtime change during sleep_fn
        audio.write_bytes(b"sample audio data 12345")
        stat = audio.stat()

        def change_mtime(s):
            import os
            os.utime(str(audio), (stat.st_atime + 10, stat.st_mtime + 10))

        self.assertFalse(is_file_stable(audio, check_interval_seconds=0.1, sleep_fn=change_mtime))

    def test_claim_inbox_audio_unstable_file_remains_in_inbox(self):
        audio = self.paths.inbox / "unstable.mp3"
        audio.write_bytes(b"initial bytes")

        def change_size(s):
            audio.write_bytes(b"initial bytes growing")

        with self.assertRaises(DriveWorkflowError) as ctx:
            claim_inbox_audio(audio, self.paths, check_interval_seconds=0.1, sleep_fn=change_size)

        self.assertIn("not stable or still syncing", str(ctx.exception))
        self.assertTrue(audio.exists())
        self.assertEqual(audio.parent, self.paths.inbox)

    def test_claim_inbox_audio_rejects_file_outside_inbox(self):
        outside_file = Path(self.temp_dir.name) / "outside.mp3"
        outside_file.write_bytes(b"outside audio content 123")

        with self.assertRaises(DriveWorkflowError) as ctx:
            claim_inbox_audio(outside_file, self.paths, check_interval_seconds=0.0)

        self.assertIn("is not located directly inside 01_Inbox", str(ctx.exception))
        self.assertTrue(outside_file.exists())
    def test_completion_audio_move_failure_raises_drive_workflow_error_and_preserves_processing_dir(self):
        import unittest.mock as mock
        audio = self.paths.inbox / "workflow_meeting.mp3"
        audio.write_bytes(b"workflow audio content 123")

        job_dir, target_audio, metadata = claim_inbox_audio(audio, self.paths, check_interval_seconds=0.0)

        transcript_result = TranscriptionResult(
            job_id=metadata.job_id,
            language="th",
            full_text="สรุปการประชุม",
            segments=[],
        )

        summary_result = MeetingSummaryResult(
            job_id=metadata.job_id,
            language="th",
            title="หัวข้อประชุม",
            quick_summary="สรุป",
            key_topics=[],
            full_summary="รายละเอียด",
            decisions=[],
            action_items=[],
            risks=[],
            follow_up=[],
        )

        with mock.patch("orbis_meeting.drive_workflow.shutil.move", side_effect=OSError("Move failed")):
            with self.assertRaises(DriveWorkflowError):
                complete_workflow_job(
                    job_dir=job_dir,
                    target_audio_path=target_audio,
                    metadata=metadata,
                    transcript_result=transcript_result,
                    summary_result=summary_result,
                    paths=self.paths,
                )

        # 02_Processing job_dir remains preserved so data is recoverable
        self.assertTrue(job_dir.exists())


class TestUIControllerDriveWorkflowIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name) / "OrbisDriveRoot"
        self.root_dir.mkdir()

        self.controller = OrbisMeetingController()
        self.paths = self.controller.set_workflow_root(self.root_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_set_workflow_root(self):
        self.assertIsNotNone(self.controller.workflow_paths)
        self.assertEqual(self.controller.workflow_paths.root, self.root_dir.resolve())

    def test_load_next_inbox_audio_claims_and_sets_origin(self):
        audio = self.paths.inbox / "inbox_job.mp3"
        audio.write_bytes(b"dummy audio binary 123")

        meta = self.controller.load_next_inbox_audio(check_interval_seconds=0.0)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.filename, "inbox_job.mp3")
        self.assertEqual(self.controller.job_origin, "WORKFLOW")
        self.assertIsNotNone(self.controller.current_workflow_job_dir)
        self.assertIsNotNone(self.controller.current_workflow_audio_path)

    def test_manual_browse_resets_origin_to_manual(self):
        # 1. Claim workflow job
        audio = self.paths.inbox / "inbox_job.mp3"
        audio.write_bytes(b"dummy audio binary 123")
        self.controller.load_next_inbox_audio(check_interval_seconds=0.0)
        self.assertEqual(self.controller.job_origin, "WORKFLOW")

        # 2. Select manual audio file
        manual_audio = Path(self.temp_dir.name) / "manual.mp3"
        manual_audio.write_bytes(b"manual bytes")
        self.controller.select_audio_file(manual_audio)

        self.assertEqual(self.controller.job_origin, "MANUAL")
        self.assertIsNone(self.controller.current_workflow_job_dir)

    def test_manual_origin_cannot_call_complete_workflow_job(self):
        manual_audio = Path(self.temp_dir.name) / "manual.mp3"
        manual_audio.write_bytes(b"manual bytes")
        self.controller.select_audio_file(manual_audio)

        with self.assertRaises(DriveWorkflowError) as ctx:
            self.controller.complete_workflow_job()
        self.assertIn("Current job is not a Google Drive workflow job", str(ctx.exception))

    def test_workflow_transcription_failure_routes_to_error_and_clears_state(self):
        import unittest.mock as mock
        mock_transcribe = mock.MagicMock(side_effect=TranscriptionError("Whisper hardware error"))
        self.controller.transcription_service.transcribe = mock_transcribe

        audio = self.paths.inbox / "failing_job.mp3"
        raw_bytes = b"failing audio binary 123"
        audio.write_bytes(raw_bytes)

        self.controller.load_next_inbox_audio(check_interval_seconds=0.0)
        self.assertEqual(self.controller.job_origin, "WORKFLOW")

        started = self.controller.start_transcription()
        self.assertTrue(started)
        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=5.0)

        # Verify job state cleared in controller
        self.assertEqual(self.controller.job_origin, "MANUAL")
        self.assertIsNone(self.controller.current_workflow_job_dir)
        self.assertIsNone(self.controller.current_workflow_audio_path)

        # Verify audio moved to 99_Error folder and error.json created
        error_subdirs = list(self.paths.error.iterdir())
        self.assertEqual(len(error_subdirs), 1)
        err_dir = error_subdirs[0]

        moved_audio = err_dir / "failing_job.mp3"
        self.assertTrue(moved_audio.exists())
        self.assertEqual(moved_audio.read_bytes(), raw_bytes)

        err_json = err_dir / "error.json"
        self.assertTrue(err_json.exists())
        err_data = json.loads(err_json.read_text(encoding="utf-8"))
        self.assertEqual(err_data["audio_filename"], "failing_job.mp3")
        self.assertEqual(err_data["stage"], "Transcription/Cleanup")
        self.assertIn("Whisper hardware error", err_data["error"])

    def test_manual_transcription_failure_does_not_touch_manual_audio(self):
        import unittest.mock as mock
        mock_transcribe = mock.MagicMock(side_effect=TranscriptionError("Whisper hardware error"))
        self.controller.transcription_service.transcribe = mock_transcribe

        manual_audio = Path(self.temp_dir.name) / "manual_failing.mp3"
        raw_bytes = b"manual audio binary bytes 456"
        manual_audio.write_bytes(raw_bytes)

        self.controller.select_audio_file(manual_audio)
        self.assertEqual(self.controller.job_origin, "MANUAL")

        started = self.controller.start_transcription()
        self.assertTrue(started)
        if self.controller.worker_thread:
            self.controller.worker_thread.join(timeout=5.0)

        # Manual audio file remains completely untouched
        self.assertTrue(manual_audio.exists())
        self.assertEqual(manual_audio.read_bytes(), raw_bytes)
        self.assertEqual(len(list(self.paths.error.iterdir())), 0)


    def test_successful_completion_clears_workflow_state_and_rejects_second_call(self):
        audio = self.paths.inbox / "completing_job.mp3"
        audio.write_bytes(b"completing audio binary 789")

        self.controller.load_next_inbox_audio(check_interval_seconds=0.0)
        self.assertEqual(self.controller.job_origin, "WORKFLOW")

        self.controller.current_transcript_result = TranscriptionResult(
            job_id="test_job",
            language="th",
            full_text="ข้อความประชุม",
            segments=[],
        )
        self.controller.current_summary_result = MeetingSummaryResult(
            job_id="test_job",
            language="th",
            title="การประชุม",
            quick_summary="สรุป",
            key_topics=[],
            full_summary="รายละเอียด",
            decisions=[],
            action_items=[],
            risks=[],
            follow_up=[],
        )

        res = self.controller.complete_workflow_job()
        self.assertTrue(res.package_dir.exists())

        # State cleared
        self.assertEqual(self.controller.job_origin, "MANUAL")
        self.assertIsNone(self.controller.current_workflow_job_dir)
        self.assertIsNone(self.controller.current_workflow_audio_path)

        # Second complete call is rejected
        with self.assertRaises(DriveWorkflowError) as ctx:
            self.controller.complete_workflow_job()
        self.assertIn("Current job is not a Google Drive workflow job", str(ctx.exception))

