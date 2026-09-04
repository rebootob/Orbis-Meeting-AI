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
from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment
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

    def test_claim_inbox_audio_moves_file_and_preserves_bytes(self):
        audio = self.paths.inbox / "meeting_record.mp3"
        raw_bytes = b"important meeting binary audio contents 12345"
        audio.write_bytes(raw_bytes)

        job_dir, target_audio, metadata = claim_inbox_audio(audio, self.paths, check_interval_seconds=0.0)

        # Original audio removed from 01_Inbox
        self.assertFalse(audio.exists())

        # Claimed audio exists under 02_Processing inside job_dir
        self.assertTrue(job_dir.exists())
        self.assertTrue(job_dir.is_relative_to(self.paths.processing))
        self.assertTrue(target_audio.exists())
        self.assertEqual(target_audio.name, "meeting_record.mp3")

        # Audio bytes strictly preserved (not transcoded or modified)
        self.assertEqual(target_audio.read_bytes(), raw_bytes)
        self.assertGreater(metadata.file_size_bytes, 0)

    def test_claim_inbox_audio_collision_safety(self):
        audio1 = self.paths.inbox / "meeting.mp3"
        raw_bytes = b"same content audio 1"
        audio1.write_bytes(raw_bytes)

        job_dir1, target1, meta1 = claim_inbox_audio(audio1, self.paths, check_interval_seconds=0.0)

        # Re-create same filename in Inbox
        audio2 = self.paths.inbox / "meeting.mp3"
        audio2.write_bytes(raw_bytes)

        job_dir2, target2, meta2 = claim_inbox_audio(audio2, self.paths, check_interval_seconds=0.0)

        self.assertNotEqual(job_dir1, job_dir2)
        self.assertTrue(job_dir2.name.endswith("_2"))
        self.assertTrue(target1.exists())
        self.assertTrue(target2.exists())

    def test_fail_workflow_job_preserves_audio_and_writes_error_json(self):
        audio = self.paths.inbox / "failed_meeting.mp3"
        raw_bytes = b"failed audio bytes"
        audio.write_bytes(raw_bytes)

        job_dir, target_audio, metadata = claim_inbox_audio(audio, self.paths, check_interval_seconds=0.0)

        err_dir = fail_workflow_job(
            paths=self.paths,
            job_id=metadata.job_id,
            audio_filename="failed_meeting.mp3",
            audio_path=target_audio,
            job_dir=job_dir,
            stage="Transcription",
            error_message="Whisper engine error",
        )

        self.assertTrue(err_dir.exists())
        self.assertTrue(err_dir.is_relative_to(self.paths.error))

        # Failed audio file is preserved (not deleted)
        preserved_audio = err_dir / "failed_meeting.mp3"
        self.assertTrue(preserved_audio.exists())
        self.assertEqual(preserved_audio.read_bytes(), raw_bytes)

        # error.json created
        err_json_file = err_dir / "error.json"
        self.assertTrue(err_json_file.exists())
        err_data = json.loads(err_json_file.read_text(encoding="utf-8"))
        self.assertEqual(err_data["job_id"], metadata.job_id)
        self.assertEqual(err_data["audio_filename"], "failed_meeting.mp3")
        self.assertEqual(err_data["stage"], "Transcription")
        self.assertIn("Whisper engine error", err_data["error"])
        self.assertIn("failed_at", err_data)

    def test_complete_workflow_job_success(self):
        audio = self.paths.inbox / "workflow_meeting.mp3"
        raw_bytes = b"workflow audio bytes 999"
        audio.write_bytes(raw_bytes)

        job_dir, target_audio, metadata = claim_inbox_audio(audio, self.paths, check_interval_seconds=0.0)

        transcript_result = TranscriptionResult(
            job_id=metadata.job_id,
            language="th",
            full_text="สรุปการประชุมงาน PLAUD และ Google Drive",
            segments=[],
        )

        summary_result = MeetingSummaryResult(
            job_id=metadata.job_id,
            language="th",
            title="การประชุม Drive Workflow",
            quick_summary="สรุปสั้นการเชื่อมต่อ workflow",
            key_topics=["Drive Sync"],
            full_summary="รายละเอียดสรุปยาว...",
            decisions=["อนุมัติ workflow"],
            action_items=[ActionItem(task="ทดสอบระบบ", owner="สมชาย", due_date="2026-09-30")],
            risks=[],
            follow_up=[],
        )

        res = complete_workflow_job(
            job_dir=job_dir,
            target_audio_path=target_audio,
            metadata=metadata,
            transcript_result=transcript_result,
            summary_result=summary_result,
            paths=self.paths,
            template_name="Management Meeting",
        )

        self.assertTrue(res.package_dir.exists())
        self.assertTrue(res.package_dir.is_relative_to(self.paths.completed))
        self.assertTrue(res.summary_path.exists())
        self.assertTrue(res.transcript_path.exists())
        self.assertTrue(res.ai_ready_path.exists())
        self.assertTrue(res.audio_reference_path.exists())

        # Audio file moved into completed package folder
        completed_audio = res.package_dir / "workflow_meeting.mp3"
        self.assertTrue(completed_audio.exists())
        self.assertEqual(completed_audio.read_bytes(), raw_bytes)

        # 02_Processing job_dir cleaned up
        self.assertFalse(job_dir.exists())


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

        meta = self.controller.load_next_inbox_audio()
        self.assertIsNotNone(meta)
        self.assertEqual(meta.filename, "inbox_job.mp3")
        self.assertEqual(self.controller.job_origin, "WORKFLOW")
        self.assertIsNotNone(self.controller.current_workflow_job_dir)
        self.assertIsNotNone(self.controller.current_workflow_audio_path)

    def test_manual_browse_resets_origin_to_manual(self):
        # 1. Claim workflow job
        audio = self.paths.inbox / "inbox_job.mp3"
        audio.write_bytes(b"dummy audio binary 123")
        self.controller.load_next_inbox_audio()
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


if __name__ == "__main__":
    unittest.main()
