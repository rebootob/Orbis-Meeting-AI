# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-005A Desktop UI Shell
- **Objective:** Implement a minimal, functional Local Desktop UI Shell using Python standard library Tkinter/ttk. The UI allows users to browse and select local PLAUD audio files (`.mp3`, `.wav`, `.m4a`), validates audio intake using WP-001, displays audio metadata and status states, executes background transcription via WP-002, applies text cleanup via WP-003, and displays the cleaned transcript in a read-only viewer while keeping the GUI responsive.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Third-party GUI frameworks (PyQt, PySide, Electron, Streamlit, Gradio, etc.)
- Summary template selector or live AI API calls (OpenAI, Claude, Gemini)
- Summary viewer or export features (PDF, Word, etc.)
- Real cloud API calls, API keys, or network calls in tests
- Google Drive API, authentication, or polling
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Central database, web dashboard, or mobile application

---

## Acceptance Criteria
- **AC-01:** WP-001 audio intake remains working.
- **AC-02:** WP-002 transcription remains working.
- **AC-03:** WP-003 cleanup remains working.
- **AC-04:** WP-004 summary foundation remains working.
- **AC-05:** Local desktop UI module exists (`src/orbis_meeting/ui.py`).
- **AC-06:** UI uses Python standard-library Tkinter/ttk only.
- **AC-07:** User can browse/select `.mp3`, `.wav`, `.m4a` files.
- **AC-08:** Selected file is validated using existing WP-001 intake logic.
- **AC-09:** No duplicate audio validation implementation.
- **AC-10:** Audio metadata (filename, extension, size) is displayed.
- **AC-11:** Original audio is not modified.
- **AC-12:** Transcribe action/button exists.
- **AC-13:** Transcription uses existing WP-002 boundary.
- **AC-14:** Real Whisper model download is not required in unit tests.
- **AC-15:** UI remains responsive while transcription executes (threading).
- **AC-16:** Duplicate transcription action is prevented while processing.
- **AC-17:** Cleaned transcript is displayed via WP-003 `TextCleanupService`.
- **AC-18:** Transcript display is read-only.
- **AC-19:** Explicit status states exist (`READY`, `AUDIO_SELECTED`, `PROCESSING`, `COMPLETED`, `ERROR`).
- **AC-20:** Errors are displayed gracefully without crashing the application.
- **AC-21:** User canceling file dialog causes no error.
- **AC-22:** Unsupported/invalid audio is rejected predictably.
- **AC-23:** No summary provider/API call is made in WP-005A.
- **AC-24:** No ChatGPT/Gemini/Claude integration exists in UI shell.
- **AC-25:** No Google Drive implementation exists.
- **AC-26:** No Telegram/LINE implementation exists.
- **AC-27:** No web server/dashboard exists.
- **AC-28:** No mobile app exists.
- **AC-29:** No new GUI third-party dependency added.
- **AC-30:** No scope beyond WP-005A introduced.
- **AC-31:** Existing WP-001 through WP-004 unit tests pass.
- **AC-32:** Focused WP-005A unit tests pass.
