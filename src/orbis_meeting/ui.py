"""
Local Desktop UI Shell for Orbis Meeting AI (WP-005A)

Provides a local desktop GUI using Python standard library Tkinter/ttk.
Supports audio file browsing, WP-001 intake validation, metadata display,
non-blocking background transcription execution (WP-002), WP-003 text cleanup,
and read-only transcript rendering while keeping the main UI responsive.

Uses thread-safe queue.Queue() handoff for all Tkinter GUI widget updates.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any, Tuple

from orbis_meeting.audio_intake import validate_and_intake_audio, AudioJobMetadata, AudioIntakeError
from orbis_meeting.transcription import WhisperTranscriptionService, TranscriptionResult, TranscriptionError
from orbis_meeting.text_cleanup import TextCleanupService, TextCleanupError


class OrbisMeetingController:
    """
    Testable application controller managing desktop UI state transitions,
    audio validation, background worker threading, and cleanup integration.
    Pushes events to a thread-safe queue.Queue() for main-thread UI consumption.
    """

    def __init__(
        self,
        transcription_service: Optional[Any] = None,
        cleanup_service: Optional[Any] = None,
        event_queue: Optional[queue.Queue] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        metadata_callback: Optional[Callable[[Optional[AudioJobMetadata]], None]] = None,
        transcript_callback: Optional[Callable[[str], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None,
        on_complete_callback: Optional[Callable[[], None]] = None,
    ):
        self.transcription_service = transcription_service or WhisperTranscriptionService()
        self.cleanup_service = cleanup_service or TextCleanupService()
        self.event_queue = event_queue if event_queue is not None else queue.Queue()

        self.status_callback = status_callback
        self.metadata_callback = metadata_callback
        self.transcript_callback = transcript_callback
        self.error_callback = error_callback
        self.on_complete_callback = on_complete_callback

        self.current_metadata: Optional[AudioJobMetadata] = None
        self.state: str = "READY"
        self.is_processing: bool = False
        self.worker_thread: Optional[threading.Thread] = None

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

    def select_audio_file(self, file_path: Optional[Union[str, Path]]) -> Optional[AudioJobMetadata]:
        """
        Handle user selecting an audio file.
        If file_path is None or empty (user cancelled dialog), do nothing and maintain current state.
        """
        if file_path is None or (isinstance(file_path, str) and not file_path.strip()):
            return self.current_metadata

        if self.is_processing:
            self._set_error("Cannot select audio file while transcription is in progress.")
            return self.current_metadata

        try:
            metadata = validate_and_intake_audio(file_path)
            self.current_metadata = metadata
            self.state = "AUDIO_SELECTED"
            self._emit_event("METADATA", metadata)
            self._emit_event("STATUS", f"AUDIO_SELECTED: {metadata.filename}")
            return metadata
        except AudioIntakeError as e:
            self.current_metadata = None
            self._emit_event("METADATA", None)
            self._set_error(f"Audio Intake Error: {e}")
            return None
        except Exception as e:
            self.current_metadata = None
            self._emit_event("METADATA", None)
            self._set_error(f"Validation Error: {e}")
            return None

    def start_transcription(self) -> bool:
        """
        Initiate non-blocking background transcription if a valid audio file is selected.
        """
        if self.is_processing:
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

            self.state = "COMPLETED"
            self.is_processing = False

            self._emit_event("TRANSCRIPT", cleaned_result.full_text)
            self._emit_event("STATUS", "COMPLETED: Cleaned transcript ready.")
            self._emit_event("COMPLETE", None)
        except (TranscriptionError, TextCleanupError) as e:
            self.is_processing = False
            self._set_error(f"Processing Error: {e}")
            self._emit_event("COMPLETE", None)
        except Exception as e:
            self.is_processing = False
            self._set_error(f"Unexpected Error: {e}")
            self._emit_event("COMPLETE", None)

    def _set_error(self, message: str):
        self.state = "ERROR"
        self._emit_event("ERROR", message)
        self._emit_event("STATUS", f"ERROR: {message}")


class OrbisMeetingWindow:
    """
    Tkinter Graphical Desktop Window interface.
    Drains event_queue on the main Tkinter thread for all widget updates.
    """

    def __init__(self, root: tk.Tk, controller: Optional[OrbisMeetingController] = None):
        self.root = root
        self.root.title("Orbis Meeting AI — Local Desktop Shell")
        self.root.geometry("700x600")
        self.root.minsize(550, 450)

        self.ui_queue: queue.Queue = queue.Queue()

        self.controller = controller or OrbisMeetingController(
            event_queue=self.ui_queue,
        )

        self._build_widgets()
        self._schedule_queue_poll()

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
        elif event_type == "TRANSCRIPT":
            self.transcript_text.config(state=tk.NORMAL)
            self.transcript_text.delete("1.0", tk.END)
            self.transcript_text.insert(tk.END, payload)
            self.transcript_text.config(state=tk.DISABLED)
        elif event_type == "ERROR":
            messagebox.showerror("Orbis Meeting AI Error", payload)
        elif event_type == "COMPLETE":
            self.browse_button.config(state=tk.NORMAL)
            if self.controller.current_metadata:
                self.transcribe_button.config(state=tk.NORMAL)

    def _build_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            main_frame,
            text="Orbis Meeting AI",
            font=("Helvetica", 16, "bold"),
        )
        title_label.pack(anchor=tk.W, pady=(0, 10))

        selection_frame = ttk.LabelFrame(main_frame, text="Audio Input", padding="10")
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

        info_frame = ttk.LabelFrame(main_frame, text="Audio Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_filename = ttk.Label(info_frame, text="Filename: N/A")
        self.lbl_filename.pack(anchor=tk.W)

        self.lbl_extension = ttk.Label(info_frame, text="Extension: N/A")
        self.lbl_extension.pack(anchor=tk.W)

        self.lbl_size = ttk.Label(info_frame, text="File Size: N/A")
        self.lbl_size.pack(anchor=tk.W)

        action_frame = ttk.Frame(main_frame)
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

        transcript_frame = ttk.LabelFrame(main_frame, text="Cleaned Transcript", padding="10")
        transcript_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(transcript_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.transcript_text = tk.Text(
            transcript_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 10),
        )
        self.transcript_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.transcript_text.yview)

        self.transcript_text.config(state=tk.DISABLED)

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
            self.controller.start_transcription()


def launch_app():
    """Main launcher entry point for local desktop UI application."""
    root = tk.Tk()
    app = OrbisMeetingWindow(root)
    root.mainloop()


if __name__ == "__main__":
    launch_app()
