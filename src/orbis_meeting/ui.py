"""
Local Desktop UI Shell for Orbis Meeting AI (WP-005A, WP-005B, WP-007, WP-011)

Provides a local desktop GUI using Python standard library Tkinter/ttk.
Supports audio file browsing, WP-001 intake validation, metadata display,
non-blocking background transcription execution (WP-002), WP-003 text cleanup,
read-only transcript rendering, WP-005B Manual AI Handoff, WP-007 Google Drive workflow,
WP-008 Automatic Job Runner, and WP-011 Control Center / Job History with bilingual TH/EN UI.

Uses thread-safe queue.Queue() handoff for all Tkinter GUI widget updates.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any

from orbis_meeting.audio_intake import validate_and_intake_audio, AudioJobMetadata, AudioIntakeError
from orbis_meeting.transcription import (
    WhisperTranscriptionService,
    TranscriptionResult,
    TranscriptionError,
    build_transcription_service_from_environment,
    format_whisper_runtime_status,
)
from orbis_meeting.text_cleanup import TextCleanupService, TextCleanupError
from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.manual_handoff import (
    SUMMARY_TEMPLATES,
    ManualHandoffError,
    build_manual_ai_payload,
    import_manual_ai_result,
)
from orbis_meeting.export_package import (
    ExportPackageError,
    ExportPackageResult,
    export_meeting_package,
)
from orbis_meeting.drive_workflow import (
    DriveWorkflowError,
    DriveWorkflowPaths,
    initialize_workflow_root,
    discover_inbox_audio,
    claim_inbox_audio,
    complete_workflow_job,
    fail_workflow_job,
)
from orbis_meeting.job_runner import AutomaticJobRunner, RunnerState, JobRunnerError
from orbis_meeting.auto_summary import build_auto_summary_service_from_environment, AutomaticSummaryService
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


def format_summary_text(summary: Optional[MeetingSummaryResult]) -> str:
    """
    Format a MeetingSummaryResult object into a clear, human-readable text document
    matching PLAUD-like information hierarchy.

    Returns empty string if summary is None.
    """
    if summary is None:
        return ""

    lines = []
    lines.append(f"MEETING TITLE: {summary.title}")
    lines.append("=" * 60)
    lines.append("")

    lines.append("QUICK SUMMARY")
    lines.append("-" * 30)
    lines.append(summary.quick_summary)
    lines.append("")

    lines.append("KEY TOPICS")
    lines.append("-" * 30)
    if summary.key_topics:
        for topic in summary.key_topics:
            lines.append(f"• {topic}")
    else:
        lines.append("No key topics identified.")
    lines.append("")

    lines.append("FULL SUMMARY")
    lines.append("-" * 30)
    lines.append(summary.full_summary)
    lines.append("")

    lines.append("DECISIONS")
    lines.append("-" * 30)
    if summary.decisions:
        for decision in summary.decisions:
            lines.append(f"• {decision}")
    else:
        lines.append("No explicit decisions recorded.")
    lines.append("")

    lines.append("ACTION ITEMS")
    lines.append("-" * 30)
    if summary.action_items:
        for idx, item in enumerate(summary.action_items, 1):
            owner = item.owner if item.owner and item.owner.strip() else "-"
            due_date = item.due_date if item.due_date and item.due_date.strip() else "-"
            lines.append(f"{idx}. Task: {item.task}")
            lines.append(f"   Owner: {owner} | Due Date: {due_date}")
    else:
        lines.append("No action items recorded.")
    lines.append("")

    lines.append("RISKS / ISSUES")
    lines.append("-" * 30)
    if summary.risks:
        for risk in summary.risks:
            lines.append(f"• {risk}")
    else:
        lines.append("No risks/issues identified.")
    lines.append("")

    lines.append("FOLLOW-UP")
    lines.append("-" * 30)
    if summary.follow_up:
        for item in summary.follow_up:
            lines.append(f"• {item}")
    else:
        lines.append("No follow-up items recorded.")

    return "\n".join(lines)


class OrbisMeetingController:
    """
    Testable application controller managing desktop UI state transitions,
    audio validation, background worker threading, cleanup integration,
    and WP-005B Manual AI Handoff payload creation and JSON importing.
    """

    def __init__(
        self,
        transcription_service: Optional[Any] = None,
        cleanup_service: Optional[Any] = None,
        auto_summary_service: Optional[Any] = None,
        event_queue: Optional[queue.Queue] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        metadata_callback: Optional[Callable[[Optional[AudioJobMetadata]], None]] = None,
        transcript_callback: Optional[Callable[[str], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None,
        on_complete_callback: Optional[Callable[[], None]] = None,
    ):
        if transcription_service is not None:
            self.transcription_service = transcription_service
        else:
            self.transcription_service = build_transcription_service_from_environment()
        self.cleanup_service = cleanup_service or TextCleanupService()
        if auto_summary_service is not None:
            self.auto_summary_service = auto_summary_service
            self.summary_engine_status = "Summary Engine: Local Automatic Ready"
        else:
            service, status = build_auto_summary_service_from_environment()
            self.auto_summary_service = service
            self.summary_engine_status = status
        self.summary_template: str = "General Meeting"
        self.event_queue = event_queue if event_queue is not None else queue.Queue()

        self.status_callback = status_callback
        self.metadata_callback = metadata_callback
        self.transcript_callback = transcript_callback
        self.error_callback = error_callback
        self.on_complete_callback = on_complete_callback

        self.current_metadata: Optional[AudioJobMetadata] = None
        self.current_transcript_result: Optional[TranscriptionResult] = None
        self.current_summary_result: Optional[MeetingSummaryResult] = None

        self.workflow_paths: Optional[DriveWorkflowPaths] = None
        self.job_origin: str = "MANUAL"  # "MANUAL" or "WORKFLOW"
        self.current_workflow_job_dir: Optional[Path] = None
        self.current_workflow_audio_path: Optional[Path] = None

        self.state: str = "READY"
        self.is_processing: bool = False
        self.worker_thread: Optional[threading.Thread] = None
        self.auto_runner: Optional[AutomaticJobRunner] = None

        self._emit_event("STATUS", "READY: Please select an audio file.")

    def _emit_event(self, event_type: str, payload: Any = None):
        """Put event into thread-safe queue and call any registered direct callbacks."""
        self.event_queue.put((event_type, payload))

        if event_type == "STATUS" and self.status_callback:
            self.status_callback(payload)
        elif event_type == "METADATA" and self.metadata_callback:
            self.metadata_callback(payload)
        elif event_type == "TRANSCRIPT" and self.transcript_callback:
            self.transcript_callback(payload)
        elif event_type == "ERROR" and self.error_callback:
            self.error_callback(payload)
        elif event_type == "COMPLETE" and self.on_complete_callback:
            self.on_complete_callback()

    def start_auto_runner(self, scan_interval_seconds: float = 5.0, stability_interval_seconds: float = 1.0) -> bool:
        """Start the background automatic job runner for 01_Inbox."""
        if not self.workflow_paths:
            raise DriveWorkflowError("Cannot start automatic runner: Workflow root directory is not configured.")
        if self.auto_runner is None:
            self.auto_runner = AutomaticJobRunner(
                controller=self,
                scan_interval_seconds=scan_interval_seconds,
                stability_interval_seconds=stability_interval_seconds,
                event_queue=self.event_queue,
            )
        return self.auto_runner.start()

    def stop_auto_runner(self) -> bool:
        """Stop the background automatic job runner cleanly."""
        if self.auto_runner:
            return self.auto_runner.stop()
        return False

    def select_audio_file(self, file_path: Optional[Union[str, Path]]) -> Optional[AudioJobMetadata]:
        """
        Handle user selecting an audio file manually.
        Sets job_origin = "MANUAL".
        """
        if file_path is None or (isinstance(file_path, str) and not file_path.strip()):
            return self.current_metadata

        if self.auto_runner and self.auto_runner.is_running:
            self._set_error("Cannot browse manual audio file while automatic job runner is active.")
            return self.current_metadata

        if self.is_processing:
            self._set_error("Cannot select audio file while transcription is in progress.")
            return self.current_metadata

        try:
            metadata = validate_and_intake_audio(file_path)
            self.job_origin = "MANUAL"
            self.current_workflow_job_dir = None
            self.current_workflow_audio_path = None
            self.current_metadata = metadata
            self.current_transcript_result = None
            self.current_summary_result = None
            self.state = "AUDIO_SELECTED"
            self._emit_event("METADATA", metadata)
            self._emit_event("SUMMARY_IMPORTED", None)
            self._emit_event("STATUS", f"AUDIO_SELECTED: {metadata.filename}")
            return metadata
        except AudioIntakeError as e:
            self.job_origin = "MANUAL"
            self.current_workflow_job_dir = None
            self.current_workflow_audio_path = None
            self.current_metadata = None
            self.current_transcript_result = None
            self.current_summary_result = None
            self._emit_event("METADATA", None)
            self._emit_event("SUMMARY_IMPORTED", None)
            self._set_error(f"Audio Intake Error: {e}")
            return None
        except Exception as e:
            self.job_origin = "MANUAL"
            self.current_workflow_job_dir = None
            self.current_workflow_audio_path = None
            self.current_metadata = None
            self.current_transcript_result = None
            self.current_summary_result = None
            self._emit_event("METADATA", None)
            self._emit_event("SUMMARY_IMPORTED", None)
            self._set_error(f"Validation Error: {e}")
            return None

    def set_workflow_root(self, root_path: Union[str, Path]) -> DriveWorkflowPaths:
        """Configure and initialize local Google Drive workflow root directory."""
        paths = initialize_workflow_root(root_path)
        self.workflow_paths = paths
        self._emit_event("WORKFLOW_INITIALIZED", paths)
        self._emit_event("STATUS", f"WORKFLOW: Initialized at {paths.root.name}")
        return paths

    def load_next_inbox_audio(
        self,
        check_interval_seconds: float = 1.0,
        sleep_fn: Optional[Any] = None,
    ) -> Optional[AudioJobMetadata]:
        """
        Discover, claim, and intake the next stable audio file from 01_Inbox.
        Sets job_origin = "WORKFLOW".
        Raises DriveWorkflowError if no workflow root or no stable inbox audio.
        """
        if not self.workflow_paths:
            raise DriveWorkflowError("Workflow root is not initialized. Please select a workflow root first.")

        if self.is_processing:
            raise DriveWorkflowError("Cannot load next Inbox audio while processing is active.")

        inbox_files = discover_inbox_audio(self.workflow_paths)
        if not inbox_files:
            raise DriveWorkflowError("No supported audio files found in 01_Inbox.")

        next_audio = inbox_files[0]
        try:
            job_dir, target_audio, metadata = claim_inbox_audio(
                next_audio,
                self.workflow_paths,
                check_interval_seconds=check_interval_seconds,
                sleep_fn=sleep_fn,
            )
            self.job_origin = "WORKFLOW"
            self.current_workflow_job_dir = job_dir
            self.current_workflow_audio_path = target_audio
            self.current_metadata = metadata
            self.current_transcript_result = None
            self.current_summary_result = None
            self.state = "AUDIO_SELECTED"

            self._emit_event("METADATA", metadata)
            self._emit_event("SUMMARY_IMPORTED", None)
            self._emit_event("STATUS", f"WORKFLOW: Claimed {metadata.filename} into 02_Processing.")
            return metadata
        except Exception as e:
            # If claim failed after file was partially touched or on error, fail safely if created
            if 'job_dir' in locals() and job_dir and job_dir.exists():
                fail_workflow_job(
                    paths=self.workflow_paths,
                    job_id=next_audio.stem,
                    audio_filename=next_audio.name,
                    audio_path=target_audio if 'target_audio' in locals() else next_audio,
                    job_dir=job_dir,
                    stage="Claim/Intake",
                    error_message=str(e),
                )
            raise DriveWorkflowError(f"Failed to claim inbox audio '{next_audio.name}': {e}") from e

    def complete_workflow_job(
        self,
        template_name: str = "General Meeting",
        clear_state: bool = True,
    ) -> ExportPackageResult:
        """
        Complete current WORKFLOW job, exporting package to 03_Completed.
        If clear_state is True, validates completion invariants and clears workflow state.
        If clear_state is False, returns export result without clearing workflow state yet.
        Raises DriveWorkflowError if job_origin is MANUAL, data missing, or validation fails.
        """
        if self.job_origin != "WORKFLOW" or not self.workflow_paths:
            raise DriveWorkflowError("Current job is not a Google Drive workflow job.")

        if not self.current_metadata or not self.current_transcript_result or not self.current_summary_result:
            raise DriveWorkflowError("Cannot complete workflow job: metadata, transcript, and summary required.")

        audio_filename = self.current_metadata.filename if self.current_metadata else None

        result = complete_workflow_job(
            job_dir=self.current_workflow_job_dir,
            target_audio_path=self.current_workflow_audio_path,
            metadata=self.current_metadata,
            transcript_result=self.current_transcript_result,
            summary_result=self.current_summary_result,
            paths=self.workflow_paths,
            template_name=template_name,
        )

        from orbis_meeting.job_runner import validate_completion_result

        if not validate_completion_result(result, self.workflow_paths, audio_filename):
            raise DriveWorkflowError("Exported meeting package failed post-completion invariant validation.")

        if clear_state:
            self.clear_completed_workflow_state()
            self._emit_event("WORKFLOW_COMPLETED", result)
            self._emit_event("STATUS", "WORKFLOW: Saved to local Google Drive sync folder (03_Completed).")

        return result

    def clear_completed_workflow_state(self):
        """Clear active workflow job tracking state after validated completion."""
        self.current_workflow_job_dir = None
        self.current_workflow_audio_path = None
        self.job_origin = "MANUAL"

        if self.auto_runner and self.auto_runner.state in (
            RunnerState.SUMMARY_READY,
            RunnerState.COMPLETING,
            RunnerState.COMPLETION_ERROR,
            RunnerState.WAITING_FOR_SUMMARY,
            RunnerState.SUMMARY_ERROR,
        ):
            new_state = RunnerState.STOPPING if self.auto_runner.is_stopping else RunnerState.IDLE
            self.auto_runner.state = new_state
            self.auto_runner.current_job = None
            if self.event_queue:
                self.event_queue.put(("RUNNER_STATE", {
                    "state": new_state.value,
                    "current_job": None,
                    "is_running": self.auto_runner.is_running,
                }))

    def start_transcription(self) -> bool:
        """
        Initiate non-blocking background transcription if a valid audio file is selected.
        """
        if self.is_processing:
            return False

        if self.auto_runner and self.auto_runner.is_running and self.job_origin == "WORKFLOW":
            self._set_error("Cannot start manual transcription while automatic job runner is active on workflow job.")
            return False

        if not self.current_metadata:
            self._set_error("No valid audio file selected. Please select a .mp3, .wav, or .m4a file.")
            return False

        self.is_processing = True
        self.state = "PROCESSING"
        self._emit_event("STATUS", "PROCESSING: Transcribing audio locally...")

        self.worker_thread = threading.Thread(
            target=self._run_transcription_worker,
            args=(self.current_metadata,),
            daemon=True,
        )
        self.worker_thread.start()
        return True

    def _run_transcription_worker(self, metadata: AudioJobMetadata):
        """
        Worker thread executing WP-002 transcription and WP-003 cleanup.
        Places results/events into queue.Queue() without touching Tkinter widgets.
        """
        try:
            raw_result = self.transcription_service.transcribe(metadata)
            cleaned_result = self.cleanup_service.clean_transcript(raw_result)

            self.current_transcript_result = cleaned_result
            self.state = "COMPLETED"
            self.is_processing = False

            self._emit_event("TRANSCRIPT", cleaned_result.full_text)
            self._emit_event("STATUS", "COMPLETED: Cleaned transcript ready.")
            self._emit_event("COMPLETE", None)
        except (TranscriptionError, TextCleanupError) as e:
            self.is_processing = False
            if self.job_origin == "WORKFLOW" and self.workflow_paths:
                fail_workflow_job(
                    paths=self.workflow_paths,
                    job_id=metadata.job_id,
                    audio_filename=metadata.filename,
                    audio_path=self.current_workflow_audio_path,
                    job_dir=self.current_workflow_job_dir,
                    stage="Transcription/Cleanup",
                    error_message=str(e),
                )
                self.current_workflow_job_dir = None
                self.current_workflow_audio_path = None
                self.job_origin = "MANUAL"
            self._set_error(f"Processing Error: {e}")
            self._emit_event("COMPLETE", None)
        except Exception as e:
            self.is_processing = False
            if self.job_origin == "WORKFLOW" and self.workflow_paths:
                fail_workflow_job(
                    paths=self.workflow_paths,
                    job_id=metadata.job_id if metadata else "unknown",
                    audio_filename=metadata.filename if metadata else "unknown",
                    audio_path=self.current_workflow_audio_path,
                    job_dir=self.current_workflow_job_dir,
                    stage="Unexpected Error",
                    error_message=str(e),
                )
                self.current_workflow_job_dir = None
                self.current_workflow_audio_path = None
                self.job_origin = "MANUAL"
            self._set_error(f"Unexpected Error: {e}")
            self._emit_event("COMPLETE", None)

    def copy_ai_payload(self, template_name: str = "General Meeting") -> str:
        """
        Generate AI-ready payload string for the current cleaned transcript.
        Raises ManualHandoffError if no cleaned transcript is available.
        """
        if not self.current_transcript_result:
            raise ManualHandoffError("No cleaned transcript available. Please transcribe an audio file first.")

        payload = build_manual_ai_payload(self.current_transcript_result, template_name=template_name)
        self._emit_event("PAYLOAD_COPIED", payload)
        return payload

    def import_ai_result(self, raw_json_text: str) -> MeetingSummaryResult:
        """
        Parse and validate manually pasted AI JSON result using WP-004 contract.
        Stores result in current session upon success.
        """
        job_id = self.current_transcript_result.job_id if self.current_transcript_result else "manual_job"
        language = self.current_transcript_result.language if self.current_transcript_result else "th"

        summary_result = import_manual_ai_result(raw_json_text, job_id=job_id, language=language)
        self.current_summary_result = summary_result
        self._emit_event("SUMMARY_IMPORTED", summary_result)
        return summary_result

    def export_meeting_package(
        self,
        output_parent: Union[str, Path],
        template_name: str = "General Meeting",
    ) -> ExportPackageResult:
        """
        Export the current meeting package (Summary.md, Transcript.txt, AI_SUMMARY_READY.md, audio_reference.json)
        to the specified output parent directory.

        Raises ExportPackageError if required session data is missing or export fails.
        """
        if not self.current_metadata or not self.current_transcript_result or not self.current_summary_result:
            raise ExportPackageError(
                "Cannot export meeting package: metadata, transcript, and summary must all be completed first."
            )

        result = export_meeting_package(
            output_parent=output_parent,
            metadata=self.current_metadata,
            transcript_result=self.current_transcript_result,
            summary_result=self.current_summary_result,
            template_name=template_name,
        )
        self._emit_event("PACKAGE_EXPORTED", result)
        return result

    def _set_error(self, message: str):
        self.state = "ERROR"
        self._emit_event("ERROR", message)
        self._emit_event("STATUS", f"ERROR: {message}")


class OrbisMeetingWindow:
    """
    Tkinter Graphical Desktop Window interface.
    Drains event_queue on the main Tkinter thread for all widget updates.
    Includes WP-005A audio/transcription UI, WP-005B Manual AI Handoff UI, WP-005C Summary Viewer,
    WP-007 Google Drive workflow, WP-008 Auto Job Runner, and WP-011 Control Center & Job History.
    """

    def __init__(self, root: tk.Tk, controller: Optional[OrbisMeetingController] = None):
        self.root = root
        self.current_lang: str = "th"  # Default bilingual language: Thai ('th') or English ('en')
        self.root.title("Orbis Meeting AI — Control Center & Workflow Shell")
        self.root.geometry("900x850")
        self.root.minsize(700, 600)

        self.ui_queue: queue.Queue = queue.Queue()

        self.controller = controller or OrbisMeetingController(
            event_queue=self.ui_queue,
        )

        self._build_widgets()
        self._schedule_queue_poll()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            self.controller.stop_auto_runner()
        except Exception:
            pass
        self.root.destroy()

    def _schedule_queue_poll(self):
        """Schedule periodic queue polling strictly on the main Tkinter thread."""
        self._poll_ui_queue()
        self.root.after(50, self._schedule_queue_poll)

    def _poll_ui_queue(self):
        """Drain events from ui_queue and apply updates to widgets on the main thread."""
        while not self.ui_queue.empty():
            try:
                event_type, payload = self.ui_queue.get_nowait()
                self._handle_ui_event(event_type, payload)
            except queue.Empty:
                break

    def _handle_ui_event(self, event_type: str, payload: Any):
        """
        Widget update handler executed EXCLUSIVELY on the main Tkinter thread.
        """
        if event_type == "STATUS":
            self.status_label.config(text=f"Status: {payload}")
        elif event_type == "WORKFLOW_INITIALIZED":
            self.workflow_root_label.config(text=f"Workflow Root: {payload.root}", font=("Helvetica", 9, "bold"))
            self.load_inbox_button.config(state=tk.NORMAL)
            if hasattr(self, "start_runner_button"):
                is_running = self.controller.auto_runner.is_running if self.controller.auto_runner else False
                if not is_running:
                    self.start_runner_button.config(state=tk.NORMAL)
        elif event_type in ("RUNNER_STATE", "RUNNER_STARTED", "RUNNER_STOPPED"):
            state_val = payload.get("state", "STOPPED") if isinstance(payload, dict) else "STOPPED"
            job_val = payload.get("current_job") if isinstance(payload, dict) else None
            if hasattr(self, "runner_status_label"):
                if state_val == "STOPPING":
                    self.runner_status_label.config(text="Runner Status: STOPPING (Finishing in-flight job)")
                else:
                    display_st = get_state_display(self.current_lang, state_val)
                    self.runner_status_label.config(text=f"Runner Status: {display_st}")
                self.runner_job_label.config(text=f"Current Job: {job_val or 'N/A'}")

            is_running = self.controller.auto_runner.is_running if self.controller.auto_runner else False
            if hasattr(self, "start_runner_button"):
                if is_running:
                    self.start_runner_button.config(state=tk.DISABLED)
                    self.stop_runner_button.config(state=tk.DISABLED if state_val == "STOPPING" else tk.NORMAL)
                    self.browse_button.config(state=tk.DISABLED)
                else:
                    self.start_runner_button.config(state=tk.NORMAL if self.controller.workflow_paths else tk.DISABLED)
                    self.stop_runner_button.config(state=tk.DISABLED)
                    self.browse_button.config(state=tk.NORMAL)
        elif event_type == "METADATA":
            if payload:
                self.selected_file_label.config(text=payload.filename, font=("Helvetica", 10, "bold"))
                self.lbl_filename.config(text=f"Filename: {payload.filename}")
                self.lbl_extension.config(text=f"Extension: {payload.extension}")
                self.lbl_size.config(text=f"File Size: {payload.file_size_bytes:,} bytes")
                self.transcribe_button.config(state=tk.NORMAL)
            else:
                self.selected_file_label.config(text="No audio file selected", font=("Helvetica", 10, "italic"))
                self.lbl_filename.config(text="Filename: N/A")
                self.lbl_extension.config(text="Extension: N/A")
                self.lbl_size.config(text="File Size: N/A")
                self.transcribe_button.config(state=tk.DISABLED)
                self.copy_ai_button.config(state=tk.DISABLED)
            self.export_button.config(state=tk.DISABLED)
            self.complete_workflow_button.config(state=tk.DISABLED)
        elif event_type == "TRANSCRIPT":
            self.transcript_text.config(state=tk.NORMAL)
            self.transcript_text.delete("1.0", tk.END)
            self.transcript_text.insert(tk.END, payload)
            self.transcript_text.config(state=tk.DISABLED)
            self.copy_ai_button.config(state=tk.NORMAL)
        elif event_type == "SUMMARY_IMPORTED":
            self.summary_text.config(state=tk.NORMAL)
            self.summary_text.delete("1.0", tk.END)
            if payload is not None:
                formatted = format_summary_text(payload)
                self.summary_text.insert(tk.END, formatted)
                self.export_button.config(state=tk.NORMAL)
                if self.controller.job_origin == "WORKFLOW":
                    self.complete_workflow_button.config(state=tk.NORMAL)
            else:
                self.export_button.config(state=tk.DISABLED)
                self.complete_workflow_button.config(state=tk.DISABLED)
            self.summary_text.config(state=tk.DISABLED)
        elif event_type == "ERROR":
            messagebox.showerror("Orbis Meeting AI Error", payload)
        elif event_type == "COMPLETE":
            self.browse_button.config(state=tk.NORMAL)
            if self.controller.current_metadata:
                self.transcribe_button.config(state=tk.NORMAL)
            if self.controller.current_transcript_result:
                self.copy_ai_button.config(state=tk.NORMAL)

        # Live refresh Control Center tab on all UI events
        self.refresh_control_center()

    def _build_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header Bar: App Title & Bilingual Language Toggle
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        self.title_label = ttk.Label(
            header_frame,
            text=get_text(self.current_lang, "title"),
            font=("Helvetica", 16, "bold"),
        )
        self.title_label.pack(side=tk.LEFT)

        lang_frame = ttk.Frame(header_frame)
        lang_frame.pack(side=tk.RIGHT)

        self.lbl_lang_toggle = ttk.Label(
            lang_frame,
            text=get_text(self.current_lang, "language_label"),
            font=("Helvetica", 9),
        )
        self.lbl_lang_toggle.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_lang_th = ttk.Button(
            lang_frame,
            text="TH (ไทย)",
            width=8,
            command=lambda: self._set_language("th"),
        )
        self.btn_lang_th.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_lang_en = ttk.Button(
            lang_frame,
            text="EN (English)",
            width=10,
            command=lambda: self._set_language("en"),
        )
        self.btn_lang_en.pack(side=tk.LEFT)

        # Tabbed Notebook Interface
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_workflow = ttk.Frame(self.notebook, padding="10")
        self.tab_control_center = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.tab_workflow, text=get_text(self.current_lang, "tab_workflow"))
        self.notebook.add(self.tab_control_center, text=get_text(self.current_lang, "tab_control_center"))

        self._build_workflow_tab(self.tab_workflow)
        self._build_control_center_tab(self.tab_control_center)

        self._apply_language()

    def _build_workflow_tab(self, parent: ttk.Frame):
        """Build the main meeting workflow tab interface."""
        # WP-007 Google Drive Workflow Section
        self.workflow_group_frame = ttk.LabelFrame(
            parent, text=get_text(self.current_lang, "workflow_section"), padding="10"
        )
        self.workflow_group_frame.pack(fill=tk.X, pady=(0, 10))

        wf_row1 = ttk.Frame(self.workflow_group_frame)
        wf_row1.pack(fill=tk.X, pady=(0, 5))

        self.select_workflow_root_button = ttk.Button(
            wf_row1,
            text=get_text(self.current_lang, "select_root_btn"),
            command=self._on_select_workflow_root_clicked,
        )
        self.select_workflow_root_button.pack(side=tk.LEFT, padx=(0, 10))

        self.workflow_root_label = ttk.Label(
            wf_row1,
            text="Workflow Root: Not Configured",
            font=("Helvetica", 9, "italic"),
        )
        self.workflow_root_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        wf_row2 = ttk.Frame(self.workflow_group_frame)
        wf_row2.pack(fill=tk.X)

        self.load_inbox_button = ttk.Button(
            wf_row2,
            text=get_text(self.current_lang, "load_inbox_btn"),
            command=self._on_load_inbox_clicked,
            state=tk.DISABLED,
        )
        self.load_inbox_button.pack(side=tk.LEFT, padx=(0, 10))

        self.start_runner_button = ttk.Button(
            wf_row2,
            text=get_text(self.current_lang, "start_runner_btn"),
            command=self._on_start_runner_clicked,
            state=tk.DISABLED,
        )
        self.start_runner_button.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_runner_button = ttk.Button(
            wf_row2,
            text=get_text(self.current_lang, "stop_runner_btn"),
            command=self._on_stop_runner_clicked,
            state=tk.DISABLED,
        )
        self.stop_runner_button.pack(side=tk.LEFT, padx=(0, 15))

        self.runner_status_label = ttk.Label(
            wf_row2,
            text="Runner Status: STOPPED",
            font=("Helvetica", 9, "bold"),
        )
        self.runner_status_label.pack(side=tk.LEFT, padx=(0, 10))

        self.runner_job_label = ttk.Label(
            wf_row2,
            text="Current Job: N/A",
            font=("Helvetica", 9, "italic"),
        )
        self.runner_job_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Audio Selection Frame
        selection_frame = ttk.LabelFrame(parent, text="Audio Input (Manual Browse)", padding="10")
        selection_frame.pack(fill=tk.X, pady=(0, 10))

        self.browse_button = ttk.Button(
            selection_frame,
            text="Browse Audio...",
            command=self._on_browse_clicked,
        )
        self.browse_button.pack(side=tk.LEFT, padx=(0, 10))

        self.selected_file_label = ttk.Label(
            selection_frame,
            text="No audio file selected",
            font=("Helvetica", 10, "italic"),
        )
        self.selected_file_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Audio Information Frame
        info_frame = ttk.LabelFrame(parent, text="Audio Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_filename = ttk.Label(info_frame, text="Filename: N/A")
        self.lbl_filename.pack(anchor=tk.W)

        self.lbl_extension = ttk.Label(info_frame, text="Extension: N/A")
        self.lbl_extension.pack(anchor=tk.W)

        self.lbl_size = ttk.Label(info_frame, text="File Size: N/A")
        self.lbl_size.pack(anchor=tk.W)

        # Actions & Status Frame
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill=tk.X, pady=(0, 10))

        self.transcribe_button = ttk.Button(
            action_frame,
            text="Transcribe Audio",
            command=self._on_transcribe_clicked,
            state=tk.DISABLED,
        )
        self.transcribe_button.pack(side=tk.LEFT, padx=(0, 15))

        self.status_label = ttk.Label(
            action_frame,
            text="Status: Ready",
            font=("Helvetica", 10, "bold"),
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Transcript Display Area (Read-Only)
        transcript_frame = ttk.LabelFrame(parent, text="Cleaned Transcript", padding="10")
        transcript_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(transcript_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.transcript_text = tk.Text(
            transcript_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 10),
            height=5,
        )
        self.transcript_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.transcript_text.yview)
        self.transcript_text.config(state=tk.DISABLED)

        # WP-005B Manual AI Handoff Section
        handoff_frame = ttk.LabelFrame(parent, text="Summary Engine & Manual Handoff", padding="10")
        handoff_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        engine_row = ttk.Frame(handoff_frame)
        engine_row.pack(fill=tk.X, pady=(0, 5))

        whisper_text = f"{get_text(self.current_lang, 'whisper_engine_status')} {format_whisper_runtime_status(self.controller.transcription_service)}"
        self.whisper_engine_status_label = ttk.Label(
            engine_row,
            text=whisper_text,
            font=("Helvetica", 9, "bold"),
        )
        self.whisper_engine_status_label.pack(side=tk.LEFT, padx=(0, 15))

        self.summary_engine_status_label = ttk.Label(
            engine_row,
            text=self.controller.summary_engine_status,
            font=("Helvetica", 9, "bold" if "Ready" in self.controller.summary_engine_status else "italic"),
        )
        self.summary_engine_status_label.pack(side=tk.LEFT)

        template_row = ttk.Frame(handoff_frame)
        template_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(template_row, text="Summary Template:").pack(side=tk.LEFT, padx=(0, 5))

        self.template_var = tk.StringVar(value="General Meeting")
        self.template_combo = ttk.Combobox(
            template_row,
            textvariable=self.template_var,
            values=list(SUMMARY_TEMPLATES.keys()),
            state="readonly",
            width=22,
        )
        self.template_combo.pack(side=tk.LEFT, padx=(0, 15))

        self.copy_ai_button = ttk.Button(
            template_row,
            text="Copy for AI",
            command=self._on_copy_ai_clicked,
            state=tk.DISABLED,
        )
        self.copy_ai_button.pack(side=tk.LEFT)

        import_label = ttk.Label(
            handoff_frame,
            text="AI Result — Paste JSON Response Below:",
            font=("Helvetica", 9, "bold"),
        )
        import_label.pack(anchor=tk.W, pady=(5, 5))

        import_scroll = ttk.Scrollbar(handoff_frame)
        import_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.ai_result_text = tk.Text(
            handoff_frame,
            wrap=tk.WORD,
            yscrollcommand=import_scroll.set,
            font=("Consolas", 9),
            height=4,
        )
        self.ai_result_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        import_scroll.config(command=self.ai_result_text.yview)

        btn_row = ttk.Frame(handoff_frame)
        btn_row.pack(fill=tk.X)

        self.import_button = ttk.Button(
            btn_row,
            text="Import AI Result",
            command=self._on_import_ai_clicked,
        )
        self.import_button.pack(side=tk.LEFT, padx=(0, 10))

        self.import_status_label = ttk.Label(
            btn_row,
            text="Import Status: No result imported",
            font=("Helvetica", 9, "italic"),
        )
        self.import_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # WP-005C Summary Viewer Section & WP-006 / WP-007 Actions
        summary_viewer_frame = ttk.LabelFrame(parent, text="Meeting Summary Viewer (PLAUD-like)", padding="10")
        summary_viewer_frame.pack(fill=tk.BOTH, expand=True)

        summary_scroll = ttk.Scrollbar(summary_viewer_frame)
        summary_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.summary_text = tk.Text(
            summary_viewer_frame,
            wrap=tk.WORD,
            yscrollcommand=summary_scroll.set,
            font=("Consolas", 10),
            height=6,
        )
        self.summary_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        summary_scroll.config(command=self.summary_text.yview)
        self.summary_text.config(state=tk.DISABLED)

        export_row = ttk.Frame(summary_viewer_frame)
        export_row.pack(fill=tk.X, pady=(5, 0))

        self.export_button = ttk.Button(
            export_row,
            text="Save Meeting Package...",
            command=self._on_export_package_clicked,
            state=tk.DISABLED,
        )
        self.export_button.pack(side=tk.LEFT, padx=(0, 10))

        self.complete_workflow_button = ttk.Button(
            export_row,
            text="Complete Workflow Job",
            command=self._on_complete_workflow_clicked,
            state=tk.DISABLED,
        )
        self.complete_workflow_button.pack(side=tk.LEFT)

    def _build_control_center_tab(self, parent: ttk.Frame):
        """Build the read-only Control Center & Job History tab interface."""
        # Top Stat Dashboard Frame
        stats_frame = ttk.Frame(parent)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        # 4 Stat Cards
        self.cc_stat_inbox_frame = ttk.LabelFrame(
            stats_frame, text=get_text(self.current_lang, "stat_inbox"), padding="8"
        )
        self.cc_stat_inbox_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.lbl_stat_inbox = ttk.Label(self.cc_stat_inbox_frame, text="0", font=("Helvetica", 14, "bold"))
        self.lbl_stat_inbox.pack(anchor=tk.CENTER)

        self.cc_stat_proc_frame = ttk.LabelFrame(
            stats_frame, text=get_text(self.current_lang, "stat_processing"), padding="8"
        )
        self.cc_stat_proc_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.lbl_stat_processing = ttk.Label(self.cc_stat_proc_frame, text="0", font=("Helvetica", 14, "bold"))
        self.lbl_stat_processing.pack(anchor=tk.CENTER)

        self.cc_stat_comp_frame = ttk.LabelFrame(
            stats_frame, text=get_text(self.current_lang, "stat_completed"), padding="8"
        )
        self.cc_stat_comp_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.lbl_stat_completed = ttk.Label(self.cc_stat_comp_frame, text="0", font=("Helvetica", 14, "bold"))
        self.lbl_stat_completed.pack(anchor=tk.CENTER)

        self.cc_stat_err_frame = ttk.LabelFrame(
            stats_frame, text=get_text(self.current_lang, "stat_error"), padding="8"
        )
        self.cc_stat_err_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.lbl_stat_error = ttk.Label(self.cc_stat_err_frame, text="0", font=("Helvetica", 14, "bold"))
        self.lbl_stat_error.pack(anchor=tk.CENTER)

        # System Status Bar
        sys_status_frame = ttk.Frame(parent)
        sys_status_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_cc_runner_status = ttk.Label(
            sys_status_frame, text="Runner Status: STOPPED", font=("Helvetica", 9, "bold")
        )
        self.lbl_cc_runner_status.pack(side=tk.LEFT, padx=(0, 15))

        self.lbl_cc_current_job = ttk.Label(
            sys_status_frame, text="Current Job: N/A", font=("Helvetica", 9, "italic")
        )
        self.lbl_cc_current_job.pack(side=tk.LEFT, padx=(0, 15))

        self.lbl_cc_whisper_engine = ttk.Label(
            sys_status_frame,
            text=f"{get_text(self.current_lang, 'whisper_engine_status')} {format_whisper_runtime_status(self.controller.transcription_service)}",
            font=("Helvetica", 9),
        )
        self.lbl_cc_whisper_engine.pack(side=tk.LEFT, padx=(0, 15))

        self.lbl_cc_summary_engine = ttk.Label(
            sys_status_frame, text=f"Summary Engine: {self.controller.summary_engine_status}", font=("Helvetica", 9)
        )
        self.lbl_cc_summary_engine.pack(side=tk.LEFT)

        # Folder Actions & Operations Toolbar
        actions_bar = ttk.Frame(parent)
        actions_bar.pack(fill=tk.X, pady=(0, 10))

        self.btn_open_inbox = ttk.Button(
            actions_bar,
            text=get_text(self.current_lang, "open_inbox"),
            command=lambda: self._on_open_folder_clicked("inbox"),
        )
        self.btn_open_inbox.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_open_completed = ttk.Button(
            actions_bar,
            text=get_text(self.current_lang, "open_completed"),
            command=lambda: self._on_open_folder_clicked("completed"),
        )
        self.btn_open_completed.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_open_error = ttk.Button(
            actions_bar,
            text=get_text(self.current_lang, "open_error"),
            command=lambda: self._on_open_folder_clicked("error"),
        )
        self.btn_open_error.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_open_root = ttk.Button(
            actions_bar,
            text=get_text(self.current_lang, "open_root"),
            command=lambda: self._on_open_folder_clicked("root"),
        )
        self.btn_open_root.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_cc_refresh = ttk.Button(
            actions_bar,
            text=get_text(self.current_lang, "refresh_btn"),
            command=self.refresh_control_center,
        )
        self.btn_cc_refresh.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_retry_completion = ttk.Button(
            actions_bar,
            text=get_text(self.current_lang, "retry_completion_btn"),
            command=self._on_retry_completion_clicked,
            state=tk.DISABLED,
        )
        self.btn_retry_completion.pack(side=tk.LEFT)

        # Recent Completed Items Treeview Table
        self.recent_completed_frame = ttk.LabelFrame(
            parent, text=get_text(self.current_lang, "recent_completed_title"), padding="8"
        )
        self.recent_completed_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        comp_scroll = ttk.Scrollbar(self.recent_completed_frame)
        comp_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tv_completed = ttk.Treeview(
            self.recent_completed_frame,
            columns=("title", "date", "files"),
            show="headings",
            height=4,
            yscrollcommand=comp_scroll.set,
        )
        self.tv_completed.heading("title", text=get_text(self.current_lang, "col_title"))
        self.tv_completed.heading("date", text=get_text(self.current_lang, "col_date"))
        self.tv_completed.heading("files", text=get_text(self.current_lang, "col_files"))

        self.tv_completed.column("title", width=350)
        self.tv_completed.column("date", width=150)
        self.tv_completed.column("files", width=180)

        self.tv_completed.pack(fill=tk.BOTH, expand=True)
        comp_scroll.config(command=self.tv_completed.yview)

        # Recent Errors Treeview Table
        self.recent_errors_frame = ttk.LabelFrame(
            parent, text=get_text(self.current_lang, "recent_errors_title"), padding="8"
        )
        self.recent_errors_frame.pack(fill=tk.BOTH, expand=True)

        err_scroll = ttk.Scrollbar(self.recent_errors_frame)
        err_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tv_errors = ttk.Treeview(
            self.recent_errors_frame,
            columns=("folder", "stage", "message", "source", "date"),
            show="headings",
            height=4,
            yscrollcommand=err_scroll.set,
        )
        self.tv_errors.heading("folder", text=get_text(self.current_lang, "col_error_dir"))
        self.tv_errors.heading("stage", text=get_text(self.current_lang, "col_stage"))
        self.tv_errors.heading("message", text=get_text(self.current_lang, "col_message"))
        self.tv_errors.heading("source", text=get_text(self.current_lang, "col_source"))
        self.tv_errors.heading("date", text=get_text(self.current_lang, "col_date"))

        self.tv_errors.column("folder", width=180)
        self.tv_errors.column("stage", width=120)
        self.tv_errors.column("message", width=250)
        self.tv_errors.column("source", width=120)
        self.tv_errors.column("date", width=140)

        self.tv_errors.pack(fill=tk.BOTH, expand=True)
        err_scroll.config(command=self.tv_errors.yview)

    def _set_language(self, lang: str):
        """Switch current bilingual language and apply string updates."""
        self.current_lang = lang
        self._apply_language()

    def _apply_language(self):
        """Update all UI widget labels dynamically to the current language ('th' or 'en')."""
        lang = self.current_lang

        # Update Notebook tab titles
        self.notebook.tab(self.tab_workflow, text=get_text(lang, "tab_workflow"))
        self.notebook.tab(self.tab_control_center, text=get_text(lang, "tab_control_center"))

        # Update Header
        self.title_label.config(text=get_text(lang, "title"))
        self.lbl_lang_toggle.config(text=get_text(lang, "language_label"))

        # Update Workflow Tab Widgets
        if hasattr(self, "workflow_group_frame"):
            self.workflow_group_frame.config(text=get_text(lang, "workflow_section"))
        if hasattr(self, "select_workflow_root_button"):
            self.select_workflow_root_button.config(text=get_text(lang, "select_root_btn"))
        if hasattr(self, "load_inbox_button"):
            self.load_inbox_button.config(text=get_text(lang, "load_inbox_btn"))
        if hasattr(self, "start_runner_button"):
            self.start_runner_button.config(text=get_text(lang, "start_runner_btn"))
        if hasattr(self, "stop_runner_button"):
            self.stop_runner_button.config(text=get_text(lang, "stop_runner_btn"))
        if hasattr(self, "whisper_engine_status_label"):
            whisper_text = f"{get_text(lang, 'whisper_engine_status')} {format_whisper_runtime_status(self.controller.transcription_service)}"
            self.whisper_engine_status_label.config(text=whisper_text)

        # Update Control Center Tab Frames & Headings
        if hasattr(self, "cc_stat_inbox_frame"):
            self.cc_stat_inbox_frame.config(text=get_text(lang, "stat_inbox"))
            self.cc_stat_proc_frame.config(text=get_text(lang, "stat_processing"))
            self.cc_stat_comp_frame.config(text=get_text(lang, "stat_completed"))
            self.cc_stat_err_frame.config(text=get_text(lang, "stat_error"))

        if hasattr(self, "recent_completed_frame"):
            self.recent_completed_frame.config(text=get_text(lang, "recent_completed_title"))
            self.tv_completed.heading("title", text=get_text(lang, "col_title"))
            self.tv_completed.heading("date", text=get_text(lang, "col_date"))
            self.tv_completed.heading("files", text=get_text(lang, "col_files"))

        if hasattr(self, "recent_errors_frame"):
            self.recent_errors_frame.config(text=get_text(lang, "recent_errors_title"))
            self.tv_errors.heading("folder", text=get_text(lang, "col_error_dir"))
            self.tv_errors.heading("stage", text=get_text(lang, "col_stage"))
            self.tv_errors.heading("message", text=get_text(lang, "col_message"))
            self.tv_errors.heading("source", text=get_text(lang, "col_source"))
            self.tv_errors.heading("date", text=get_text(lang, "col_date"))

        if hasattr(self, "btn_open_inbox"):
            self.btn_open_inbox.config(text=get_text(lang, "open_inbox"))
            self.btn_open_completed.config(text=get_text(lang, "open_completed"))
            self.btn_open_error.config(text=get_text(lang, "open_error"))
            self.btn_open_root.config(text=get_text(lang, "open_root"))
            self.btn_cc_refresh.config(text=get_text(lang, "refresh_btn"))
            self.btn_retry_completion.config(text=get_text(lang, "retry_completion_btn"))

        self.refresh_control_center()

    def refresh_control_center(self):
        """Fetch pure read-only snapshot and refresh all Control Center widgets."""
        snapshot = get_control_center_snapshot(controller=self.controller)

        # Update Stat Card Numbers
        self.lbl_stat_inbox.config(text=str(snapshot.inbox_count))
        self.lbl_stat_processing.config(text=str(snapshot.processing_count))
        self.lbl_stat_completed.config(text=str(snapshot.completed_count))
        self.lbl_stat_error.config(text=str(snapshot.error_count))

        # Update Runner & Summary Labels
        state_display = get_state_display(self.current_lang, snapshot.runner_state)
        runner_str = f"{get_text(self.current_lang, 'runner_status')} {state_display}"
        self.lbl_cc_runner_status.config(text=runner_str)

        job_str = f"{get_text(self.current_lang, 'current_job')} {snapshot.current_job_name or 'N/A'}"
        self.lbl_cc_current_job.config(text=job_str)

        whisper_str = f"{get_text(self.current_lang, 'whisper_engine_status')} {snapshot.whisper_engine_status}"
        self.lbl_cc_whisper_engine.config(text=whisper_str)

        engine_str = f"{get_text(self.current_lang, 'summary_engine_status')} {snapshot.summary_engine_provider}"
        self.lbl_cc_summary_engine.config(text=engine_str)

        # Update Retry Completion Button state (Enabled ONLY when state is COMPLETION_ERROR)
        if snapshot.runner_state in (RunnerState.COMPLETION_ERROR.value, "COMPLETION_ERROR"):
            self.btn_retry_completion.config(state=tk.NORMAL)
        else:
            self.btn_retry_completion.config(state=tk.DISABLED)

        # Update Recent Completed Treeview Table
        for row in self.tv_completed.get_children():
            self.tv_completed.delete(row)

        for item in snapshot.recent_completed:
            files_status = []
            if item.summary_present:
                files_status.append("Summary")
            if item.transcript_present:
                files_status.append("Transcript")
            if item.audio_json_present:
                files_status.append("AudioJSON")
            files_str = ", ".join(files_status) if files_status else "Incomplete"

            self.tv_completed.insert(
                "",
                tk.END,
                values=(item.title, item.created_at, files_str),
            )

        # Update Recent Errors Treeview Table
        for row in self.tv_errors.get_children():
            self.tv_errors.delete(row)

        for err_item in snapshot.recent_errors:
            self.tv_errors.insert(
                "",
                tk.END,
                values=(
                    err_item.directory_name,
                    err_item.failed_stage,
                    err_item.error_message,
                    err_item.source_file,
                    err_item.failed_at,
                ),
            )

    def _on_retry_completion_clicked(self):
        """Invoke runner.retry_current_completion() when state is COMPLETION_ERROR."""
        if not self.controller.auto_runner:
            messagebox.showwarning("Retry Error", "Automatic job runner is not initialized.")
            return

        try:
            res = self.controller.auto_runner.retry_current_completion()
            self.refresh_control_center()
            messagebox.showinfo(
                "Retry Completion Success",
                f"Successfully completed meeting package:\n\nFolder: {res.package_dir.name}\nPath: {res.package_dir}",
            )
        except Exception as e:
            self.refresh_control_center()
            messagebox.showerror("Retry Completion Failed", str(e))

    def _on_open_folder_clicked(self, folder_type: str):
        """Open workflow folder in native OS file explorer safely."""
        if not self.controller.workflow_paths:
            messagebox.showwarning("Folder Warning", "Workflow root directory is not configured.")
            return

        target_path = None
        if folder_type == "inbox":
            target_path = self.controller.workflow_paths.inbox
        elif folder_type == "completed":
            target_path = self.controller.workflow_paths.completed
        elif folder_type == "error":
            target_path = self.controller.workflow_paths.error
        elif folder_type == "root":
            target_path = self.controller.workflow_paths.root

        success = open_folder_in_os(target_path)
        if not success:
            messagebox.showwarning("Folder Error", f"Unable to open directory: {target_path}")

    def _on_select_workflow_root_clicked(self):
        root_dir = filedialog.askdirectory(title="Select Local Google Drive Workflow Root Directory")
        if root_dir:
            try:
                paths = self.controller.set_workflow_root(root_dir)
                self.refresh_control_center()
                messagebox.showinfo(
                    "Workflow Initialized",
                    f"Google Drive workflow initialized at:\n\n{paths.root}\n\nFolders verified:\n- 01_Inbox\n- 02_Processing\n- 03_Completed\n- 99_Error",
                )
            except Exception as e:
                messagebox.showerror("Workflow Error", str(e))

    def _on_start_runner_clicked(self):
        try:
            self.controller.start_auto_runner()
            self.refresh_control_center()
            messagebox.showinfo("Auto Runner", "Automatic Job Runner started.\nMonitoring 01_Inbox periodically.")
        except Exception as e:
            messagebox.showerror("Auto Runner Error", str(e))

    def _on_stop_runner_clicked(self):
        try:
            self.controller.stop_auto_runner()
            self.refresh_control_center()
            messagebox.showinfo("Auto Runner", "Automatic Job Runner stopped.")
        except Exception as e:
            messagebox.showerror("Auto Runner Error", str(e))

    def _on_load_inbox_clicked(self):
        try:
            metadata = self.controller.load_next_inbox_audio()
            if metadata:
                self.refresh_control_center()
                messagebox.showinfo(
                    "Inbox Audio Claimed",
                    f"Successfully claimed '{metadata.filename}' from 01_Inbox into 02_Processing.\nReady for transcription.",
                )
        except Exception as e:
            messagebox.showwarning("Inbox Load Error", str(e))

    def _on_complete_workflow_clicked(self):
        try:
            template = self.template_var.get()
            result = self.controller.complete_workflow_job(template_name=template)
            self.complete_workflow_button.config(state=tk.DISABLED)
            self.refresh_control_center()
            messagebox.showinfo(
                "Workflow Job Completed",
                f"Saved to local Google Drive sync folder:\n\n{result.package_dir}\n\nGoogle Drive Desktop application handles background cloud synchronization.",
            )
        except Exception as e:
            messagebox.showerror("Workflow Completion Error", str(e))

    def _on_browse_clicked(self):
        file_path = filedialog.askopenfilename(
            title="Select PLAUD Audio File",
            filetypes=[
                ("Supported Audio Files", "*.mp3 *.wav *.m4a"),
                ("MP3 Audio", "*.mp3"),
                ("WAV Audio", "*.wav"),
                ("M4A Audio", "*.m4a"),
                ("All Files", "*.*"),
            ],
        )
        if file_path:
            self.controller.select_audio_file(file_path)

    def _on_transcribe_clicked(self):
        if self.controller.current_metadata:
            self.transcribe_button.config(state=tk.DISABLED)
            self.browse_button.config(state=tk.DISABLED)
            self.copy_ai_button.config(state=tk.DISABLED)
            self.export_button.config(state=tk.DISABLED)
            self.complete_workflow_button.config(state=tk.DISABLED)
            self.controller.start_transcription()

    def _on_copy_ai_clicked(self):
        try:
            template = self.template_var.get()
            payload = self.controller.copy_ai_payload(template_name=template)

            self.root.clipboard_clear()
            self.root.clipboard_append(payload)

            self.status_label.config(text="Status: Copied. Paste into ChatGPT, Gemini, or Claude.")
        except Exception as e:
            messagebox.showerror("Copy Error", str(e))

    def _on_import_ai_clicked(self):
        raw_text = self.ai_result_text.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Import Error", "Please paste AI JSON response text first.")
            return

        try:
            result = self.controller.import_ai_result(raw_text)
            self.import_status_label.config(
                text=f"Import Status: Successfully Imported '{result.title}'",
                font=("Helvetica", 9, "bold"),
            )
            messagebox.showinfo(
                "Import Successful",
                f"Successfully imported meeting summary:\n\nTitle: {result.title}\nKey Topics: {len(result.key_topics)}\nAction Items: {len(result.action_items)}",
            )
        except Exception as e:
            self.import_status_label.config(
                text=f"Import Status: Validation Failed ({e})",
                font=("Helvetica", 9, "italic"),
            )
            messagebox.showerror("Import Validation Error", str(e))

    def _on_export_package_clicked(self):
        output_dir = filedialog.askdirectory(title="Select Destination Directory for Meeting Package")
        if not output_dir:
            return

        try:
            template = self.template_var.get()
            result = self.controller.export_meeting_package(output_dir, template_name=template)
            messagebox.showinfo(
                "Export Successful",
                f"Successfully saved meeting package:\n\nFolder: {result.package_dir.name}\nPath: {result.package_dir}",
            )
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


def launch_app():
    """Main launcher entry point for local desktop UI application."""
    root = tk.Tk()
    app = OrbisMeetingWindow(root)
    root.mainloop()


if __name__ == "__main__":
    launch_app()
