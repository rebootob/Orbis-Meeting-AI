# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-001 Local Audio Intake Foundation
- **Objective:** Create a minimal, reliable local audio intake validation layer for Orbis Meeting AI. Validate audio files before downstream transcription processing without modifying original files.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Whisper or transcription dependencies / wrappers
- Audio decoding / FFmpeg integrations
- Thai cleanup or company dictionary logic
- Meeting summarization or LLM integration
- Google Drive API or polling
- Telegram or LINE notification code or stubs
- Database or state persistence infrastructure
- Web/Mobile UI or API servers

---

## Acceptance Criteria
- **AC-01:** Minimal Python project structure exists (`src/orbis_meeting/`, `tests/`).
- **AC-02:** `.mp3` input is accepted.
- **AC-03:** `.wav` input is accepted.
- **AC-04:** `.m4a` input is accepted.
- **AC-05:** Extension matching is case-insensitive (e.g. `.MP3`, `.WAV`, `.M4A`).
- **AC-06:** Missing file path is rejected explicitly.
- **AC-07:** Directory path is rejected explicitly.
- **AC-08:** Unsupported extension is rejected explicitly.
- **AC-09:** Zero-byte audio file is rejected explicitly.
- **AC-10:** Accepted file returns metadata containing `job_id`, `original_path`, `filename`, `extension`, `file_size_bytes`.
- **AC-11:** `job_id` is deterministic for the same unchanged input file.
- **AC-12:** Original input audio file remains strictly unchanged (read-only).
- **AC-13:** Focused automated tests cover all valid and invalid cases.
- **AC-14:** All WP-001 unit tests pass.
- **AC-15:** No transcription dependency or implementation exists.
- **AC-16:** No Google Drive implementation exists.
- **AC-17:** No Telegram or LINE notification code/stub exists.
- **AC-18:** No application scope beyond WP-001 introduced.
