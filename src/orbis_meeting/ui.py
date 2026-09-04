"""
Local Desktop UI Shell for Orbis Meeting AI (WP-005A)

Provides a local desktop GUI using Python standard library Tkinter/ttk.
Supports audio file browsing, WP-001 intake validation, metadata display,
non-blocking background transcription execution (WP-002), WP-003 text cleanup,
and read-only transcript rendering while keeping the main UI responsive.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Union, Callable, Dict, Any

from orbis_meeting.audio_intake import validate_and_intake_audio, AudioJobMetadata, AudioIntakeError
from orbis_meeting.transcription import WhisperTranscriptionService, TranscriptionResult, TranscriptionError
from orbis_meeting.text_cleanup import TextCleanupService, TextCleanupError


class OrbisMeetingController:
    """
    Testable application controller managing desktop UI state transitions,
    audio validation, background worker threading, and cleanup integration.
    """

    def __init__(
        self,
        transcription_service: Optional[Any] = None,
        cleanup_service: Optional[Any] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        metadata_callback: Optional[Callable[[Optional[AudioJobMetadata]], None]] = None,
        transcript_callback: Optional[Callable[[str], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None,
        on_complete_callback: Optional[Callable[[], None]] = None,
    ):
        self.transcription_service = transcription_service or WhisperTranscriptionService()
        self.cleanup_service = cleanup_service or TextCleanupService()

        self.status_callback = status_callback
        self.metadata_callback = metadata_callback
        self.transcript_callback = transcript_callback
        self.error_callback = error_callback
        self.on_complete_callback = on_complete_callback

        self.current_metadata: Optional[AudioJobMetadata] = None
        self.state: str = "READY"
        self.is_processing: bool = False
        self.worker_thread: Optional[threading.Thread] = None

        self._update_status("READY: Please select an audio file.")

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
            self._update_status(f"AUDIO_SELECTED: {metadata.filename}")

            if self.metadata_callback:
                self.metadata_callback(metadata)
            return metadata
        except AudioIntakeError as e:
            self.current_metadata = None
            self._set_error(f"Audio Intake Error: {e}")
            if self.metadata_callback:
                self.metadata_callback(None)
            return None
        except Exception as e:
            self.current_metadata = None
            self._set_error(f"Validation Error: {e}")
            if self.metadata_callback:
                self.metadata_callback(None)
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
        self._update_status("PROCESSING: Transcribing audio locally...")

        self.worker_thread = threading.Thread(
            target=self._run_transcription_worker,
            args=(self.current_metadata,),
            daemon=True,
        )
        self.worker_thread.start()
        return True

    def _run_transcription_worker(self, metadata: AudioJobMetadata):
        """Worker thread executing WP-002 transcription and WP-003 cleanup."""
        try:
            raw_result = self.transcription_service.transcribe(metadata)
            cleaned_result = self.cleanup_service.clean_transcript(raw_result)

            self.state = "COMPLETED"
            self.is_processing = False
            self._update_status("COMPLETED: Cleaned transcript ready.")

            if self.transcript_callback:
                self.transcript_callback(cleaned_result.full_text)
            if self.on_complete_callback:
                self.on_complete_callback()
        except (TranscriptionError, TextCleanupError) as e:
            self.is_processing = False
            self._set_error(f"Processing Error: {e}")
            if self.on_complete_callback:
                self.on_complete_callback()
        except Exception as e:
            self.is_processing = False
            self._set_error(f"Unexpected Error: {e}")
            if self.on_complete_callback:
                self.on_complete_callback()

    def _update_status(self, message: str):
        if self.status_callback:
            self.status_callback(message)

    def _set_error(self, message: str):
        self.state = "ERROR"
        self._update_status(f"ERROR: {message}")
        if self.error_callback:
            self.error_callback(message)


class OrbisMeetingWindow:
    """
    Tkinter Graphical Desktop Window interface.
    """

    def __init__(self, root: tk.Tk, controller: Optional[OrbisMeetingController] = None):
        self.root = root
        self.root.title("Orbis Meeting AI — Local Desktop Shell")
        self.root.geometry("700x600")
        self.root.minsize(550, 450)

        # Setup controller with thread-safe callbacks
        self.controller = controller or OrbisMeetingController(
            status_callback=self._safe_status_update,
            metadata_callback=self._safe_metadata_update,
            transcript_callback=self._safe_transcript_update,
            error_callback=self._safe_error_update,
            on_complete_callback=self._safe_on_complete,
        )

        self._build_widgets()

    def _build_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title Header
        title_label = ttk.Label(
            main_frame,
            text="Orbis Meeting AI",
            font=("Helvetica", 16, "bold"),
        )
        title_label.pack(anchor=tk.W, pady=(0, 10))

        # Audio Selection Frame
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

        # Audio Information Frame
        info_frame = ttk.LabelFrame(main_frame, text="Audio Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_filename = ttk.Label(info_frame, text="Filename: N/A")
        self.lbl_filename.pack(anchor=tk.W)

        self.lbl_extension = ttk.Label(info_frame, text="Extension: N/A")
        self.lbl_extension.pack(anchor=tk.W)

        self.lbl_size = ttk.Label(info_frame, text="File Size: N/A")
        self.lbl_size.pack(anchor=tk.W)

        # Actions & Status Frame
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

        # Transcript Display Area (Read-Only)
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

        # Lock transcript widget as read-only by default
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

    def _safe_status_update(self, message: str):
        self.root.after(0, lambda: self.status_label.config(text=f"Status: {message}"))

    def _safe_metadata_update(self, metadata: Optional[AudioJobMetadata]):
        def _update():
            if metadata:
                self.selected_file_label.config(text=metadata.filename, font=("Helvetica", 10, "bold"))
                self.lbl_filename.config(text=f"Filename: {metadata.filename}")
                self.lbl_extension.config(text=f"Extension: {metadata.extension}")
                self.lbl_size.config(text=f"File Size: {metadata.file_size_bytes:,} bytes")
                self.transcribe_button.config(state=tk.NORMAL)
            else:
                self.selected_file_label.config(text="No audio file selected", font=("Helvetica", 10, "italic"))
                self.lbl_filename.config(text="Filename: N/A")
                self.lbl_extension.config(text="Extension: N/A")
                self.lbl_size.config(text="File Size: N/A")
                self.transcribe_button.config(state=tk.DISABLED)

        self.root.after(0, _update)

    def _safe_transcript_update(self, text: str):
        def _update():
            self.transcript_text.config(state=tk.NORMAL)
            self.transcript_text.delete("1.0", tk.END)
            self.transcript_text.insert(tk.END, text)
            self.transcript_text.config(state=tk.DISABLED)

        self.root.after(0, _update)

    def _safe_error_update(self, error_message: str):
        def _update():
            messagebox.showerror("Orbis Meeting AI Error", error_message)

        self.root.after(0, _update)

    def _safe_on_complete(self):
        def _update():
            self.browse_button.config(state=tk.NORMAL)
            if self.controller.current_metadata:
                self.transcribe_button.config(state=tk.NORMAL)

        self.root.after(0, _update)


def launch_app():
    """Main launcher entry point for local desktop UI application."""
    root = tk.Tk()
    app = OrbisMeetingWindow(root)
    root.mainloop()


if __name__ == "__main__":
    launch_app()
