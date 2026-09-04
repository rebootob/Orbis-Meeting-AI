"""
Unit tests for WP-008 Automatic Job Runner Module (src/orbis_meeting/job_runner.py)
"""

import json
import sys
import tempfile
import unittest
import threading
from pathlib import Path
from typing import Optional

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.audio_intake import AudioJobMetadata
from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment, TranscriptionError
from orbis_meeting.text_cleanup import TextCleanupError
from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.drive_workflow import initialize_workflow_root, DriveWorkflowPaths, DriveWorkflowError
from orbis_meeting.ui import OrbisMeetingController
from orbis_meeting.job_runner import AutomaticJobRunner, RunnerState, JobRunnerError


class FakeTranscriptionService:
    def __init__(self, raw_text="สวัสดีครับ การประชุมระบบอัตโนมัติ", raise_exception=None):
        self.raw_text = raw_text
        self.raise_exception = raise_exception
        self.call_count = 0

    def transcribe(self, metadata: AudioJobMetadata) -> TranscriptionResult:
        self.call_count += 1
        if self.raise_exception:
            raise self.raise_exception
        return TranscriptionResult(
            job_id=metadata.job_id,
            language="th",
            full_text=self.raw_text,
            segments=[TranscriptionSegment(start=0.0, end=3.0, text=self.raw_text)],
        )


class FakeCleanupService:
    def __init__(self, cleaned_text="สวัสดีครับ การประชุมระบบอัตโนมัติ (Cleaned)", raise_exception=None):
        self.cleaned_text = cleaned_text
        self.raise_exception = raise_exception
        self.call_count = 0

    def clean_transcript(self, raw_result: TranscriptionResult) -> TranscriptionResult:
        self.call_count += 1
        if self.raise_exception:
            raise self.raise_exception
        return TranscriptionResult(
            job_id=raw_result.job_id,
            language=raw_result.language,
            full_text=self.cleaned_text,
            segments=[TranscriptionSegment(start=0.0, end=3.0, text=self.cleaned_text)],
        )


class TestAutomaticJobRunnerModule(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name) / "GoogleDrive_OrbisRoot"
        self.root_dir.mkdir()

        self.fake_transcription = FakeTranscriptionService()
        self.fake_cleanup = FakeCleanupService()

        self.controller = OrbisMeetingController(
            transcription_service=self.fake_transcription,
            cleanup_service=self.fake_cleanup,
        )
        self.paths = self.controller.set_workflow_root(self.root_dir)

        self.runner = AutomaticJobRunner(
            controller=self.controller,
            scan_interval_seconds=0.05,
            stability_interval_seconds=0.0,
            sleep_fn=lambda s: None,
        )

    def tearDown(self):
        if self.runner.is_running:
            self.runner.stop(timeout=1.0)
        self.temp_dir.cleanup()

    def test_runner_initial_state_stopped(self):
        self.assertEqual(self.runner.state, RunnerState.STOPPED)
        self.assertFalse(self.runner.is_running)
        self.assertIsNone(self.runner.current_job)

    def test_start_transitions_and_duplicate_start_safe(self):
        started = self.runner.start()
        self.assertTrue(started)
        self.assertTrue(self.runner.is_running)

        # Duplicate start returns False cleanly
        started_again = self.runner.start()
        self.assertFalse(started_again)
        self.assertTrue(self.runner.is_running)

        self.runner.stop(timeout=1.0)
        self.assertFalse(self.runner.is_running)
        self.assertEqual(self.runner.state, RunnerState.STOPPED)

    def test_stop_works_and_thread_exits_cleanly(self):
        self.runner.start()
        self.assertTrue(self.runner.is_running)
        stopped = self.runner.stop(timeout=1.0)
        self.assertTrue(stopped)
        self.assertFalse(self.runner.is_running)
        self.assertEqual(self.runner.state, RunnerState.STOPPED)

    def test_run_once_with_no_workflow_root_raises_error(self):
        empty_controller = OrbisMeetingController()
        runner = AutomaticJobRunner(controller=empty_controller)
        with self.assertRaises(JobRunnerError):
            runner.run_once()
        self.assertEqual(runner.state, RunnerState.ERROR)

    def test_empty_inbox_transitions_to_idle(self):
        job = self.runner.run_once()
        self.assertIsNone(job)
        self.assertEqual(self.runner.state, RunnerState.IDLE)

    def test_stable_audio_automatically_claimed_transcribed_cleaned_and_pauses_at_waiting_for_summary(self):
        audio = self.paths.inbox / "meeting_auto.mp3"
        audio.write_bytes(b"auto binary audio bytes 123")

        claimed_job = self.runner.run_once()
        self.assertIsNotNone(claimed_job)
        self.assertEqual(claimed_job, "meeting_auto.mp3")

        # Verified transitions & results
        self.assertEqual(self.runner.state, RunnerState.WAITING_FOR_SUMMARY)
        self.assertEqual(self.fake_transcription.call_count, 1)
        self.assertEqual(self.fake_cleanup.call_count, 1)

        self.assertIsNotNone(self.controller.current_transcript_result)
        self.assertIn("Cleaned", self.controller.current_transcript_result.full_text)

        # NO automatic summary generated or completed
        self.assertIsNone(self.controller.current_summary_result)
        self.assertTrue(self.controller.current_workflow_job_dir.exists())
        self.assertEqual(self.controller.current_workflow_job_dir.parent, self.paths.processing)

    def test_unstable_audio_remains_in_inbox_and_not_sent_to_error(self):
        audio = self.paths.inbox / "unstable_auto.mp3"
        audio.write_bytes(b"initial bytes")

        def mutating_sleep(s):
            audio.write_bytes(b"initial bytes growing during sync")

        unstable_runner = AutomaticJobRunner(
            controller=self.controller,
            scan_interval_seconds=0.05,
            stability_interval_seconds=0.1,
            sleep_fn=mutating_sleep,
        )

        job = unstable_runner.run_once()
        self.assertIsNone(job)

        # Audio file remains in 01_Inbox
        self.assertTrue(audio.exists())
        self.assertEqual(audio.parent, self.paths.inbox)

        # 99_Error remains empty
        self.assertEqual(len(list(self.paths.error.iterdir())), 0)
        self.assertEqual(unstable_runner.state, RunnerState.IDLE)

    def test_oldest_stable_audio_selected_and_only_one_job_claimed(self):
        # Create old and new files
        f_old = self.paths.inbox / "01_old_meeting.mp3"
        f_old.write_bytes(b"old meeting audio")

        f_new = self.paths.inbox / "02_new_meeting.mp3"
        f_new.write_bytes(b"new meeting audio")

        claimed_job = self.runner.run_once()
        self.assertEqual(claimed_job, "01_old_meeting.mp3")
        self.assertEqual(self.runner.state, RunnerState.WAITING_FOR_SUMMARY)

        # Second inbox file remains untouched in 01_Inbox while first job is waiting for summary
        self.assertTrue(f_new.exists())
        self.assertEqual(f_new.parent, self.paths.inbox)

        # Subsequent run_once does NOT claim second file while first job is waiting for summary
        second_claim = self.runner.run_once()
        self.assertIsNone(second_claim)
        self.assertTrue(f_new.exists())

    def test_copy_for_ai_manual_flow_available_during_waiting_for_summary(self):
        audio = self.paths.inbox / "handoff_meeting.mp3"
        audio.write_bytes(b"handoff audio content 123")

        self.runner.run_once()
        self.assertEqual(self.runner.state, RunnerState.WAITING_FOR_SUMMARY)

        # Copy for AI works
        payload = self.controller.copy_ai_payload("General Meeting")
        self.assertIn("Cleaned", payload)

        # Import AI result works
        ai_json = json.dumps({
            "title": "การประชุมอัตโนมัติ",
            "quick_summary": "สรุปงานสั้น",
            "key_topics": ["หัวข้อ 1"],
            "full_summary": "สรุปยาว",
            "decisions": [],
            "action_items": [],
            "risks": [],
            "follow_up": []
        })
        imported_summary = self.controller.import_ai_result(ai_json)
        self.assertIsNotNone(imported_summary)

        # Complete Workflow Job works and clears workflow tracking state
        res = self.controller.complete_workflow_job()
        self.assertTrue(res.package_dir.exists())

        # Runner can now process second job on subsequent run_once
        f_next = self.paths.inbox / "next_meeting.mp3"
        f_next.write_bytes(b"next meeting bytes")

        next_claimed = self.runner.run_once()
        self.assertEqual(next_claimed, "next_meeting.mp3")

    def test_transcription_failure_routes_to_error_and_runner_survives(self):
        failing_transcribe = FakeTranscriptionService(raise_exception=TranscriptionError("Whisper engine error"))
        self.controller.transcription_service = failing_transcribe

        audio = self.paths.inbox / "transcription_fail.mp3"
        raw_bytes = b"failing audio binary bytes 123"
        audio.write_bytes(raw_bytes)

        claimed = self.runner.run_once()
        self.assertIsNone(claimed)

        # Error directory contains failed audio & error.json
        err_dirs = list(self.paths.error.iterdir())
        self.assertEqual(len(err_dirs), 1)
        err_dir = err_dirs[0]

        moved_audio = err_dir / "transcription_fail.mp3"
        self.assertTrue(moved_audio.exists())
        self.assertEqual(moved_audio.read_bytes(), raw_bytes)

        err_json = err_dir / "error.json"
        self.assertTrue(err_json.exists())
        err_data = json.loads(err_json.read_text(encoding="utf-8"))
        self.assertIn("Whisper engine error", err_data["error"])

        # Runner state returns to IDLE and can process next job
        self.assertEqual(self.runner.state, RunnerState.IDLE)

        # Next job processable
        audio2 = self.paths.inbox / "subsequent_job.mp3"
        audio2.write_bytes(b"subsequent audio bytes 456")
        self.controller.transcription_service = FakeTranscriptionService()

        job2 = self.runner.run_once()
        self.assertEqual(job2, "subsequent_job.mp3")
        self.assertEqual(self.runner.state, RunnerState.WAITING_FOR_SUMMARY)

    def test_cleanup_failure_routes_to_error_and_runner_survives(self):
        failing_cleanup = FakeCleanupService(raise_exception=TextCleanupError("Company dictionary mapping invalid"))
        self.controller.cleanup_service = failing_cleanup

        audio = self.paths.inbox / "cleanup_fail.mp3"
        audio.write_bytes(b"cleanup fail bytes 123")

        claimed = self.runner.run_once()
        self.assertIsNone(claimed)

        # File routed to 99_Error
        err_dirs = list(self.paths.error.iterdir())
        self.assertEqual(len(err_dirs), 1)
        self.assertEqual(self.runner.state, RunnerState.IDLE)

    def test_manual_browse_rejected_when_runner_active_and_works_when_stopped(self):
        manual_audio = Path(self.temp_dir.name) / "manual_test.mp3"
        manual_audio.write_bytes(b"manual test bytes")

        self.runner.start()
        self.assertTrue(self.runner.is_running)

        # Manual browse rejected while runner is active
        res = self.controller.select_audio_file(manual_audio)
        self.assertIsNone(res)
        self.assertEqual(self.controller.state, "ERROR")

        # Stop runner -> manual browse works
        self.runner.stop(timeout=1.0)
        self.assertFalse(self.runner.is_running)

        meta = self.controller.select_audio_file(manual_audio)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.filename, "manual_test.mp3")
        self.assertEqual(self.controller.job_origin, "MANUAL")

    def test_stop_requested_during_inflight_transcription_drains_safely_and_blocks_manual_browse(self):
        transcribe_started = threading.Event()
        transcribe_allow_finish = threading.Event()

        class BlockingTranscriptionService:
            def transcribe(self, metadata):
                transcribe_started.set()
                transcribe_allow_finish.wait(timeout=5.0)
                return TranscriptionResult(
                    job_id=metadata.job_id,
                    language="th",
                    full_text="ข้อความจากการถอดเสียง",
                    segments=[],
                )

        self.controller.transcription_service = BlockingTranscriptionService()

        audio = self.paths.inbox / "blocking_job.mp3"
        audio.write_bytes(b"blocking audio contents 123")

        self.runner.start()
        self.assertTrue(transcribe_started.wait(timeout=3.0))

        try:
            # Request stop while transcription is actively in-flight
            stopped_immediately = self.runner.stop(timeout=0.05)
            self.assertFalse(stopped_immediately)  # Thread is still running; stop pending/draining
            self.assertTrue(self.runner.is_running)
            self.assertIn(self.runner.state, (RunnerState.STOPPING, RunnerState.TRANSCRIBING))

            # Manual Browse remains rejected while runner is draining
            manual_audio = Path(self.temp_dir.name) / "manual_during_drain.mp3"
            manual_audio.write_bytes(b"manual bytes")
            self.controller.select_audio_file(manual_audio)
            self.assertEqual(self.controller.state, "ERROR")
        finally:
            # Always unblock transcription thread so test tearDown does not deadlock
            transcribe_allow_finish.set()

        if self.runner._thread:
            self.runner._thread.join(timeout=2.0)

        # Runner is now fully STOPPED after thread exit
        self.assertFalse(self.runner.is_running)
        self.assertEqual(self.runner.state, RunnerState.STOPPED)

        # Reset controller state and verify manual Browse works after runner is STOPPED
        self.controller.state = "READY"
        meta = self.controller.select_audio_file(manual_audio)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.filename, "manual_during_drain.mp3")

    def test_no_next_job_claimed_after_stop_request(self):
        f1 = self.paths.inbox / "01_audio.mp3"
        f1.write_bytes(b"audio 1")
        f2 = self.paths.inbox / "02_audio.mp3"
        f2.write_bytes(b"audio 2")

        self.runner._stop_event.set()
        claimed = self.runner.run_once()
        self.assertIsNone(claimed)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertEqual(f1.parent, self.paths.inbox)
        self.assertEqual(f2.parent, self.paths.inbox)

    def test_oldest_file_unstable_second_file_stable_selects_second_file(self):
        f1_unstable = self.paths.inbox / "01_old_unstable.mp3"
        f1_unstable.write_bytes(b"unstable audio bytes")

        f2_stable = self.paths.inbox / "02_ready.mp3"
        f2_stable.write_bytes(b"stable audio 2 bytes")

        f3_stable = self.paths.inbox / "03_ready.mp3"
        f3_stable.write_bytes(b"stable audio 3 bytes")

        def selective_sleep(s):
            # Mutate size of f1 to simulate active sync
            f1_unstable.write_bytes(b"unstable audio bytes growing")

        selective_runner = AutomaticJobRunner(
            controller=self.controller,
            scan_interval_seconds=0.05,
            stability_interval_seconds=0.1,
            sleep_fn=selective_sleep,
        )

        claimed = selective_runner.run_once()
        self.assertEqual(claimed, "02_ready.mp3")

        # 01_old_unstable.mp3 remains in 01_Inbox
        self.assertTrue(f1_unstable.exists())
        self.assertEqual(f1_unstable.parent, self.paths.inbox)

        # 03_ready.mp3 remains in 01_Inbox (only one job claimed)
        self.assertTrue(f3_stable.exists())
        self.assertEqual(f3_stable.parent, self.paths.inbox)

        # 99_Error remains empty
        self.assertEqual(len(list(self.paths.error.iterdir())), 0)

    def test_all_inbox_files_unstable_claims_none_and_returns_idle(self):
        f1 = self.paths.inbox / "01_unstable.mp3"
        f1.write_bytes(b"bytes 1")
        f2 = self.paths.inbox / "02_unstable.mp3"
        f2.write_bytes(b"bytes 2")

        def all_unstable_sleep(s):
            f1.write_bytes(b"bytes 1 growing")
            f2.write_bytes(b"bytes 2 growing")

        unstable_runner = AutomaticJobRunner(
            controller=self.controller,
            scan_interval_seconds=0.05,
            stability_interval_seconds=0.1,
            sleep_fn=all_unstable_sleep,
        )

        claimed = unstable_runner.run_once()
        self.assertIsNone(claimed)
        self.assertEqual(unstable_runner.state, RunnerState.IDLE)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertEqual(len(list(self.paths.error.iterdir())), 0)


    def test_auto_summary_service_success_automatically_completes_job_and_returns_idle(self):
        from test_auto_summary import FakeProvider, create_valid_summary_json_dict
        from orbis_meeting.auto_summary import AutomaticSummaryService

        valid_json = json.dumps(create_valid_summary_json_dict())
        self.controller.auto_summary_service = AutomaticSummaryService(
            provider=FakeProvider(response_text=valid_json),
            template_name="General Meeting",
        )

        audio_bytes = b"auto summary audio bytes 123"
        audio = self.paths.inbox / "auto_summary_job.mp3"
        audio.write_bytes(audio_bytes)

        claimed = self.runner.run_once()
        self.assertEqual(claimed, "auto_summary_job.mp3")

        # Runner state returns to IDLE after automatic completion
        self.assertEqual(self.runner.state, RunnerState.IDLE)

        # Verified completed package created under 03_Completed
        completed_pkgs = list(self.paths.completed.iterdir())
        self.assertEqual(len(completed_pkgs), 1)
        pkg_dir = completed_pkgs[0]

        # Verified required files exist in Completed package
        self.assertTrue((pkg_dir / "Summary.md").exists())
        self.assertTrue((pkg_dir / "Transcript.txt").exists())
        self.assertTrue((pkg_dir / "AI_SUMMARY_READY.md").exists())
        self.assertTrue((pkg_dir / "audio_reference.json").exists())

        # Verified original audio file finalized in package with bytes preserved
        pkg_audio = pkg_dir / "auto_summary_job.mp3"
        self.assertTrue(pkg_audio.exists())
        self.assertEqual(pkg_audio.read_bytes(), audio_bytes)

        # Active workflow job tracking state cleared
        self.assertIsNone(self.controller.current_workflow_job_dir)
        self.assertEqual(self.controller.job_origin, "MANUAL")

    def test_queue_continuation_processes_second_inbox_file_on_next_scan(self):
        from test_auto_summary import FakeProvider, create_valid_summary_json_dict
        from orbis_meeting.auto_summary import AutomaticSummaryService

        valid_json = json.dumps(create_valid_summary_json_dict())
        self.controller.auto_summary_service = AutomaticSummaryService(
            provider=FakeProvider(response_text=valid_json),
        )

        f1 = self.paths.inbox / "01_first.mp3"
        f1.write_bytes(b"first meeting audio")

        f2 = self.paths.inbox / "02_second.mp3"
        f2.write_bytes(b"second meeting audio")

        # First run_once processes and completes 01_first.mp3
        job1 = self.runner.run_once()
        self.assertEqual(job1, "01_first.mp3")
        self.assertEqual(self.runner.state, RunnerState.IDLE)
        self.assertIsNone(self.controller.current_workflow_job_dir)

        # Second run_once processes and completes 02_second.mp3
        job2 = self.runner.run_once()
        self.assertEqual(job2, "02_second.mp3")
        self.assertEqual(self.runner.state, RunnerState.IDLE)

        # Both packages completed under 03_Completed
        completed_pkgs = list(self.paths.completed.iterdir())
        self.assertEqual(len(completed_pkgs), 2)

    def test_auto_summary_service_failure_preserves_job_in_processing_for_manual_fallback(self):
        from test_auto_summary import FakeProvider
        from orbis_meeting.auto_summary import AutomaticSummaryService

        self.controller.auto_summary_service = AutomaticSummaryService(
            provider=FakeProvider(response_text="{invalid json}"),
            template_name="General Meeting",
        )

        audio = self.paths.inbox / "summary_fail_job.mp3"
        audio.write_bytes(b"summary fail audio bytes")

        claimed = self.runner.run_once()
        self.assertEqual(claimed, "summary_fail_job.mp3")

        # Runner transitions to SUMMARY_ERROR (no auto completion)
        self.assertEqual(self.runner.state, RunnerState.SUMMARY_ERROR)

        # current_summary_result is None, but current_transcript_result is preserved
        self.assertIsNone(self.controller.current_summary_result)
        self.assertIsNotNone(self.controller.current_transcript_result)

        # Job is NOT sent to 99_Error; stays in 02_Processing
        self.assertEqual(len(list(self.paths.error.iterdir())), 0)
        self.assertTrue(self.controller.current_workflow_job_dir.exists())
        self.assertEqual(self.controller.current_workflow_job_dir.parent, self.paths.processing)

        # No package created in 03_Completed
        self.assertEqual(len(list(self.paths.completed.iterdir())), 0)

        # Manual Copy for AI and Manual Import AI result still work as fallback
        payload = self.controller.copy_ai_payload()
        self.assertIn("Cleaned", payload)

    def test_completion_export_failure_transitions_to_completion_error_and_preserves_data(self):
        from test_auto_summary import FakeProvider, create_valid_summary_json_dict
        from orbis_meeting.auto_summary import AutomaticSummaryService

        valid_json = json.dumps(create_valid_summary_json_dict())
        self.controller.auto_summary_service = AutomaticSummaryService(
            provider=FakeProvider(response_text=valid_json),
        )

        audio = self.paths.inbox / "completion_fail.mp3"
        audio.write_bytes(b"completion fail audio")

        # Mock complete_workflow_job to fail
        def failing_complete(*args, **kwargs):
            raise DriveWorkflowError("Disk full during export")

        self.controller.complete_workflow_job = failing_complete

        claimed = self.runner.run_once()
        self.assertEqual(claimed, "completion_fail.mp3")

        # Runner state becomes COMPLETION_ERROR
        self.assertEqual(self.runner.state, RunnerState.COMPLETION_ERROR)

        # Data preserved in controller and 02_Processing (NOT moved to 99_Error)
        self.assertIsNotNone(self.controller.current_summary_result)
        self.assertIsNotNone(self.controller.current_transcript_result)
        self.assertIsNotNone(self.controller.current_workflow_job_dir)
        self.assertTrue(self.controller.current_workflow_job_dir.exists())
        self.assertEqual(len(list(self.paths.error.iterdir())), 0)

        # Subsequent run_once does NOT claim new job
        f2 = self.paths.inbox / "next_job.mp3"
        f2.write_bytes(b"next audio")

        next_claimed = self.runner.run_once()
        self.assertIsNone(next_claimed)
        self.assertEqual(self.runner.state, RunnerState.COMPLETION_ERROR)

    def test_manual_origin_meeting_never_auto_completed(self):
        manual_audio = Path(self.temp_dir.name) / "manual_only.mp3"
        manual_audio.write_bytes(b"manual bytes")

        self.controller.select_audio_file(manual_audio)
        self.assertEqual(self.controller.job_origin, "MANUAL")

        # run_once returns None and does not complete manual meeting
        job = self.runner.run_once()
        self.assertIsNone(job)
        self.assertEqual(len(list(self.paths.completed.iterdir())), 0)

    def test_retry_current_completion_recovers_from_completion_error(self):
        from test_auto_summary import FakeProvider, create_valid_summary_json_dict
        from orbis_meeting.auto_summary import AutomaticSummaryService

        valid_json = json.dumps(create_valid_summary_json_dict())
        self.controller.auto_summary_service = AutomaticSummaryService(
            provider=FakeProvider(response_text=valid_json),
        )

        audio = self.paths.inbox / "retry_comp.mp3"
        audio.write_bytes(b"retry comp audio")

        orig_complete = self.controller.complete_workflow_job
        call_counter = [0]

        def flaky_complete(*args, **kwargs):
            call_counter[0] += 1
            if call_counter[0] == 1:
                raise DriveWorkflowError("Temporary filesystem lock")
            return orig_complete(*args, **kwargs)

        self.controller.complete_workflow_job = flaky_complete

        # First run fails at completion step -> state COMPLETION_ERROR
        claimed = self.runner.run_once()
        self.assertEqual(claimed, "retry_comp.mp3")
        self.assertEqual(self.runner.state, RunnerState.COMPLETION_ERROR)

        # Call retry_current_completion() -> succeeds on second attempt
        res = self.runner.retry_current_completion()
        self.assertTrue(res.package_dir.exists())
        self.assertEqual(self.runner.state, RunnerState.IDLE)


if __name__ == "__main__":
    unittest.main()


