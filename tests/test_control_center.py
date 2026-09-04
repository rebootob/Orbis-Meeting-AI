"""
Unit Tests for WP-011 Control Center & Job History Module
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.drive_workflow import initialize_workflow_root
from orbis_meeting.job_runner import RunnerState
from orbis_meeting.control_center import (
    RecentCompletedItem,
    RecentErrorItem,
    ControlCenterSnapshot,
    UI_TEXT,
    get_text,
    get_state_display,
    open_folder_in_os,
    get_control_center_snapshot,
)


class TestControlCenter(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name) / "workflow_root"
        self.root_path.mkdir()
        self.paths = initialize_workflow_root(self.root_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_snapshot_unconfigured_paths(self):
        """Test snapshot generation with None or missing workflow paths."""
        snapshot = get_control_center_snapshot(paths=None, controller=None)
        self.assertEqual(snapshot.inbox_count, 0)
        self.assertEqual(snapshot.processing_count, 0)
        self.assertEqual(snapshot.completed_count, 0)
        self.assertEqual(snapshot.error_count, 0)
        self.assertEqual(snapshot.runner_state, "STOPPED")
        self.assertFalse(snapshot.runner_is_running)
        self.assertEqual(len(snapshot.recent_completed), 0)
        self.assertEqual(len(snapshot.recent_errors), 0)

    def test_snapshot_counts_and_sorting(self):
        """Test scanning counts and top-10 limit with newest-first mtime sorting."""
        # 1. Create 3 audio files in Inbox
        (self.paths.inbox / "test1.mp3").write_bytes(b"12345")
        (self.paths.inbox / "test2.wav").write_bytes(b"67890")
        (self.paths.inbox / "test3.m4a").write_bytes(b"abcde")

        # 2. Create 2 job dirs in Processing
        (self.paths.processing / "job1").mkdir()
        (self.paths.processing / "job2").mkdir()

        # 3. Create 12 completed package dirs
        for i in range(12):
            pkg_dir = self.paths.completed / f"2026-09-04_Meeting_{i:02d}"
            pkg_dir.mkdir()
            (pkg_dir / "Summary.md").write_text(f"MEETING TITLE: Strategic Planning {i}\nContent", encoding="utf-8")
            (pkg_dir / "Transcript.txt").write_text("Transcript", encoding="utf-8")
            (pkg_dir / "audio_reference.json").write_text("{}", encoding="utf-8")

        # 4. Create 12 error dirs
        for i in range(12):
            err_dir = self.paths.error / f"2026-09-04_Error_{i:02d}"
            err_dir.mkdir()
            err_info = {
                "job_id": f"job_{i}",
                "audio_filename": f"audio_{i}.mp3",
                "stage": "Transcription Worker",
                "error": f"Failed at test step {i}",
                "failed_at": f"2026-09-04T10:{i:02d}:00",
            }
            (err_dir / "error.json").write_text(json.dumps(err_info), encoding="utf-8")

        snapshot = get_control_center_snapshot(paths=self.paths)

        self.assertEqual(snapshot.inbox_count, 3)
        self.assertEqual(snapshot.processing_count, 2)
        self.assertEqual(snapshot.completed_count, 12)
        self.assertEqual(snapshot.error_count, 12)

        # Max 10 items in recent lists
        self.assertEqual(len(snapshot.recent_completed), 10)
        self.assertEqual(len(snapshot.recent_errors), 10)

        # Check completed item properties
        first_comp = snapshot.recent_completed[0]
        self.assertTrue(first_comp.summary_present)
        self.assertTrue(first_comp.transcript_present)
        self.assertTrue(first_comp.audio_json_present)
        self.assertTrue(first_comp.title.startswith("Strategic Planning"))

        # Check error item properties
        first_err = snapshot.recent_errors[0]
        self.assertTrue(first_err.raw_json_present)
        self.assertTrue(bool(first_err.source_file))

    def test_error_json_fallback(self):
        """Test safe handling of missing or corrupt error.json files."""
        # Corrupt JSON error dir
        corrupt_dir = self.paths.error / "corrupt_err"
        corrupt_dir.mkdir()
        (corrupt_dir / "error.json").write_text("{invalid json", encoding="utf-8")

        # Missing error.json error dir
        missing_dir = self.paths.error / "missing_json_err"
        missing_dir.mkdir()

        snapshot = get_control_center_snapshot(paths=self.paths)
        self.assertEqual(snapshot.error_count, 2)

        for err_item in snapshot.recent_errors:
            self.assertFalse(err_item.raw_json_present)
            self.assertEqual(err_item.failed_stage, "UNKNOWN")
            self.assertEqual(err_item.error_message, "Error metadata unavailable")

    def test_summary_title_extraction_fallback(self):
        """Test extracting meeting title or falling back to folder name."""
        pkg1 = self.paths.completed / "pkg1"
        pkg1.mkdir()
        (pkg1 / "Summary.md").write_text("# Executive Sync\nSummary details...", encoding="utf-8")

        pkg2 = self.paths.completed / "pkg2_no_title"
        pkg2.mkdir()
        (pkg2 / "Summary.md").write_text("No header title here", encoding="utf-8")

        pkg3 = self.paths.completed / "pkg3_no_summary"
        pkg3.mkdir()

        snapshot = get_control_center_snapshot(paths=self.paths)
        titles = {item.title for item in snapshot.recent_completed}

        self.assertIn("Executive Sync", titles)
        self.assertIn("pkg2_no_title", titles)
        self.assertIn("pkg3_no_summary", titles)

    def test_bilingual_translation_and_state_display(self):
        """Test TH/EN string retrieval and runner state translation."""
        self.assertEqual(get_text("th", "title"), "Orbis Meeting AI")
        self.assertEqual(get_text("en", "title"), "Orbis Meeting AI")

        self.assertEqual(get_text("th", "stat_inbox"), "ไฟล์รอประมวลผล (Inbox)")
        self.assertEqual(get_text("en", "stat_inbox"), "Inbox Audio Files")

        # Internal state string remains unmodified
        st = RunnerState.TRANSCRIBING
        self.assertEqual(st.value, "TRANSCRIBING")

        th_display = get_state_display("th", st)
        en_display = get_state_display("en", st)

        self.assertIn("กำลังถอดความเสียง", th_display)
        self.assertEqual(en_display, "Transcribing Audio")

    def test_open_folder_in_os(self):
        """Test safe OS folder opening."""
        # Invalid / missing path
        self.assertFalse(open_folder_in_os(None))
        self.assertFalse(open_folder_in_os(self.root_path / "non_existent_folder"))

        # Valid directory
        with patch("os.startfile", create=True) as mock_startfile:
            success = open_folder_in_os(self.paths.inbox)
            self.assertTrue(success)
            mock_startfile.assert_called_once_with(str(self.paths.inbox.resolve()))

    def test_runner_and_summary_status_in_snapshot(self):
        """Test controller and runner state integration in snapshot."""
        mock_controller = MagicMock()
        mock_controller.workflow_paths = self.paths
        mock_controller.summary_engine_status = "Summary Engine: Local Automatic Ready"

        mock_runner = MagicMock()
        mock_runner.state = RunnerState.COMPLETION_ERROR
        mock_runner.is_running = True
        mock_runner.current_job = "meeting_audio.mp3"
        mock_controller.auto_runner = mock_runner

        snapshot = get_control_center_snapshot(controller=mock_controller)

        self.assertEqual(snapshot.runner_state, "COMPLETION_ERROR")
        self.assertTrue(snapshot.runner_is_running)
        self.assertEqual(snapshot.current_job_name, "meeting_audio.mp3")
        self.assertTrue(snapshot.summary_engine_enabled)
        self.assertEqual(snapshot.summary_engine_provider, "Summary Engine: Local Automatic Ready")


if __name__ == "__main__":
    unittest.main()
