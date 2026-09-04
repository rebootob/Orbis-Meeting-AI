"""
Automatic Job Runner Module for Orbis Meeting AI (WP-008)

Provides a single-host background automatic job runner that periodically scans
01_Inbox, verifies file stability, claims one audio job into 02_Processing,
executes Whisper transcription and Thai text cleanup automatically, and pauses at WAITING_FOR_SUMMARY.

Enforces single active workflow job policy, thread safety, and failure recovery to 99_Error.
No automatic AI summary generation is performed in WP-008.
"""

import queue
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any

from orbis_meeting.drive_workflow import (
    DriveWorkflowError,
    DriveWorkflowPaths,
    discover_inbox_audio,
    is_file_stable,
    claim_inbox_audio,
    fail_workflow_job,
)
from orbis_meeting.transcription import TranscriptionResult, TranscriptionError
from orbis_meeting.text_cleanup import TextCleanupError


class JobRunnerError(RuntimeError):
    """Raised when job runner execution or configuration fails."""
    pass


class RunnerState(str, Enum):
    """Execution states for AutomaticJobRunner."""
    STOPPED = "STOPPED"
    STOPPING = "STOPPING"
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    CLAIMING = "CLAIMING"
    TRANSCRIBING = "TRANSCRIBING"
    CLEANING = "CLEANING"
    WAITING_FOR_SUMMARY = "WAITING_FOR_SUMMARY"
    ERROR = "ERROR"


class AutomaticJobRunner:
    """
    Single-host automatic job runner monitoring 01_Inbox.

    Automates: Inbox scan -> Stability check -> Claim -> Transcribe -> Cleanup -> WAITING_FOR_SUMMARY.
    """

    def __init__(
        self,
        controller: Any,
        scan_interval_seconds: float = 5.0,
        stability_interval_seconds: float = 1.0,
        event_queue: Optional[queue.Queue] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        self.controller = controller
        if hasattr(controller, "auto_runner") and getattr(controller, "auto_runner", None) is None:
            controller.auto_runner = self
        self.scan_interval_seconds = scan_interval_seconds
        self.stability_interval_seconds = stability_interval_seconds
        self.event_queue = event_queue or getattr(controller, "event_queue", queue.Queue())
        self.sleep_fn = sleep_fn

        self.state: RunnerState = RunnerState.STOPPED
        self.current_job: Optional[str] = None
        self._is_running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        """True while the worker thread loop is actively running (not fully STOPPED)."""
        return self._is_running

    @property
    def is_stopping(self) -> bool:
        """True if a stop request has been signaled but in-flight work is still draining."""
        return self._stop_event.is_set() and self._is_running

    def _set_state(self, new_state: RunnerState, current_job: Optional[str] = None):
        """Update state and emit bounded event if state or current_job changed."""
        with self._lock:
            state_changed = (self.state != new_state or self.current_job != current_job)
            self.state = new_state
            self.current_job = current_job

        if state_changed:
            payload = {
                "state": new_state.value,
                "current_job": current_job,
                "is_running": self._is_running,
            }
            if self.event_queue:
                self.event_queue.put(("RUNNER_STATE", payload))

    def start(self) -> bool:
        """
        Start background job runner thread.
        Idempotent: Returns False if runner is already active or stopping.
        """
        with self._lock:
            if self._is_running:
                return False

            if not self.controller.workflow_paths:
                raise JobRunnerError("Cannot start automatic runner: Workflow root directory is not configured.")

            self._is_running = True
            self._stop_event.clear()
            self.state = RunnerState.IDLE
            self.current_job = None

            self._thread = threading.Thread(
                target=self._runner_loop,
                daemon=True,
                name="OrbisAutomaticJobRunner",
            )
            self._thread.start()

        if self.event_queue:
            self.event_queue.put(("RUNNER_STARTED", {"state": RunnerState.IDLE.value}))
        return True

    def stop(self, timeout: float = 5.0) -> bool:
        """
        Stop background job runner thread cleanly.
        Signals stop event without interrupting in-flight operations.
        Drains in-flight work before transitioning to STOPPED.
        """
        with self._lock:
            if not self._is_running:
                return False
            self._stop_event.set()
            thread = self._thread
            if self.state not in (RunnerState.STOPPED, RunnerState.STOPPING):
                self._set_state(RunnerState.STOPPING, self.current_job)

        if thread and thread.is_alive() and threading.current_thread() != thread:
            thread.join(timeout=timeout)

        # Check if thread actually finished
        with self._lock:
            if thread and thread.is_alive():
                # Thread is still draining in-flight work after timeout.
                # Keep _is_running = True, manual mode remains blocked.
                return False

        # Thread finished cleanly. _runner_loop's finally block handles STOPPED state transition.
        return True

    def _runner_loop(self):
        """Background thread execution loop with non-busy polling wait."""
        try:
            while not self._stop_event.is_set():
                try:
                    self.run_once()
                except Exception as e:
                    # Log unexpected loop error without crashing loop thread unless unrecoverable
                    self._set_state(RunnerState.ERROR, self.current_job)
                    if self.event_queue:
                        self.event_queue.put(("RUNNER_ERROR", str(e)))

                if self._stop_event.is_set():
                    break

                # Non-busy wait using Event.wait
                self._stop_event.wait(self.scan_interval_seconds)
        finally:
            with self._lock:
                self._is_running = False
                self.state = RunnerState.STOPPED
                self.current_job = None
            if self.event_queue:
                self.event_queue.put(("RUNNER_STOPPED", {"state": RunnerState.STOPPED.value}))

    def run_once(self) -> Optional[str]:
        """
        Execute one deterministic iteration of Inbox discovery, stability check, claim,
        transcription, text cleanup, and transition to WAITING_FOR_SUMMARY.

        Returns claimed filename/job_id if a job was processed, else None.
        """
        if self._stop_event.is_set():
            return None

        paths: Optional[DriveWorkflowPaths] = self.controller.workflow_paths
        if not paths:
            self._set_state(RunnerState.ERROR, None)
            raise JobRunnerError("Workflow root is not configured.")

        # Check Single-Job Policy:
        # If there is already an active workflow job in processing or waiting for summary, pause scanning.
        if self.controller.job_origin == "WORKFLOW" and self.controller.current_workflow_job_dir is not None:
            if self.controller.current_transcript_result is not None:
                new_state = RunnerState.STOPPING if self._stop_event.is_set() else RunnerState.WAITING_FOR_SUMMARY
                self._set_state(new_state, self.controller.current_metadata.filename if self.controller.current_metadata else None)
            return None

        # If controller is busy with manual processing, do not claim workflow audio
        if self.controller.is_processing:
            return None

        # Step 1: Scan 01_Inbox
        scan_state = RunnerState.STOPPING if self._stop_event.is_set() else RunnerState.SCANNING
        self._set_state(scan_state, None)
        inbox_files = discover_inbox_audio(paths)

        if not inbox_files:
            idle_state = RunnerState.STOPPING if self._stop_event.is_set() else RunnerState.IDLE
            self._set_state(idle_state, None)
            return None

        # Step 2 & 3: Iterate deterministic oldest-first list and find the FIRST STABLE audio file
        candidate_audio = None
        for file_path in inbox_files:
            if is_file_stable(
                file_path,
                check_interval_seconds=self.stability_interval_seconds,
                sleep_fn=self.sleep_fn,
            ):
                candidate_audio = file_path
                break

        if candidate_audio is None:
            # None of the inbox files are stable yet; leave all in 01_Inbox
            idle_state = RunnerState.STOPPING if self._stop_event.is_set() else RunnerState.IDLE
            self._set_state(idle_state, None)
            return None

        if self._stop_event.is_set():
            return None

        # Step 4: Claim audio file into 02_Processing
        self._set_state(RunnerState.CLAIMING, candidate_audio.name)
        try:
            job_dir, target_audio, metadata = claim_inbox_audio(
                candidate_audio,
                paths,
                check_interval_seconds=self.stability_interval_seconds,
                sleep_fn=self.sleep_fn,
            )

            # Update controller state for claimed WORKFLOW job
            self.controller.job_origin = "WORKFLOW"
            self.controller.current_workflow_job_dir = job_dir
            self.controller.current_workflow_audio_path = target_audio
            self.controller.current_metadata = metadata
            self.controller.current_transcript_result = None
            self.controller.current_summary_result = None
            self.controller.state = "AUDIO_SELECTED"

            if self.event_queue:
                self.event_queue.put(("METADATA", metadata))
                self.event_queue.put(("SUMMARY_IMPORTED", None))
                self.event_queue.put(("STATUS", f"WORKFLOW AUTO: Claimed {metadata.filename} into 02_Processing."))

            # Step 5: Transcribe Audio
            self._set_state(RunnerState.TRANSCRIBING, metadata.filename)
            self.controller.is_processing = True
            self.controller.state = "PROCESSING"
            if self.event_queue:
                self.event_queue.put(("STATUS", f"WORKFLOW AUTO: Transcribing {metadata.filename}..."))

            raw_result = self.controller.transcription_service.transcribe(metadata)

            # Step 6: Thai Text Cleanup & Company Dictionary
            self._set_state(RunnerState.CLEANING, metadata.filename)
            if self.event_queue:
                self.event_queue.put(("STATUS", f"WORKFLOW AUTO: Cleaning Thai transcript for {metadata.filename}..."))

            cleaned_result = self.controller.cleanup_service.clean_transcript(raw_result)

            # Step 7: Store Transcript Result & Pause at WAITING_FOR_SUMMARY
            self.controller.current_transcript_result = cleaned_result
            self.controller.state = "COMPLETED"
            self.controller.is_processing = False

            if self.event_queue:
                self.event_queue.put(("TRANSCRIPT", cleaned_result.full_text))
                self.event_queue.put(("STATUS", f"WORKFLOW AUTO: Cleaned transcript ready. WAITING_FOR_SUMMARY."))
                self.event_queue.put(("COMPLETE", None))

            final_state = RunnerState.STOPPING if self._stop_event.is_set() else RunnerState.WAITING_FOR_SUMMARY
            self._set_state(final_state, metadata.filename)
            return metadata.filename

        except Exception as e:
            # Per-Job Failure Routing to 99_Error
            self.controller.is_processing = False
            if self.controller.job_origin == "WORKFLOW" and paths:
                fail_workflow_job(
                    paths=paths,
                    job_id=metadata.job_id if 'metadata' in locals() and metadata else candidate_audio.stem,
                    audio_filename=candidate_audio.name,
                    audio_path=target_audio if 'target_audio' in locals() and target_audio and target_audio.exists() else candidate_audio,
                    job_dir=job_dir if 'job_dir' in locals() else None,
                    stage="AutoRunner Processing",
                    error_message=str(e),
                )

            # Reset controller active workflow state so runner survives failure and can process next job
            self.controller.current_workflow_job_dir = None
            self.controller.current_workflow_audio_path = None
            self.controller.job_origin = "MANUAL"
            self.controller.state = "ERROR"

            if self.event_queue:
                self.event_queue.put(("ERROR", f"Auto Runner Job Failure: {e}"))
                self.event_queue.put(("STATUS", f"WORKFLOW AUTO ERROR: Job failed and moved to 99_Error. {e}"))

            err_state = RunnerState.STOPPING if self._stop_event.is_set() else RunnerState.IDLE
            self._set_state(err_state, None)
            return None

