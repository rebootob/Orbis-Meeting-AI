# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-002 Local Whisper Transcription Foundation
- **Objective:** Implement a reliable local transcription layer using `faster-whisper` for validated WP-001 audio files. Return structured raw transcripts with timestamped segments without modifying original audio files.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`
- `requirements.txt` (if needed for dependencies)

### Forbidden Changes
- Thai text cleanup or company dictionary logic
- Punctuation repair or post-processing beyond Whisper output
- Summarization or LLM / OpenAI / Gemini / Claude API integration
- Google Drive API, authentication, or polling
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Database or vector search / RAG framework
- Web/Mobile UI or API servers

---

## Acceptance Criteria
- **AC-01:** WP-001 audio intake remains working unchanged.
- **AC-02:** Transcription module exists (`src/orbis_meeting/transcription.py`).
- **AC-03:** Transcription uses `faster-whisper` through a minimal wrapper/service.
- **AC-04:** Model name is configurable (default: `large-v3`).
- **AC-05:** Device is configurable (e.g. `cpu`, `cuda`, `auto`).
- **AC-06:** Compute type is configurable (e.g. `int8`, `float16`, `default`).
- **AC-07:** Service accepts validated WP-001 audio input (`AudioJobMetadata`).
- **AC-08:** Result contains `job_id`, `language`, `full_text`, `segments`.
- **AC-09:** Every segment contains `start`, `end`, `text`.
- **AC-10:** Thai transcription mode is supported (`language="th"`).
- **AC-11:** English transcription mode is supported (`language="en"`).
- **AC-12:** Automatic language detection is supported when `language=None`.
- **AC-13:** Original audio is not modified.
- **AC-14:** Model loading errors fail explicitly (`TranscriptionError`).
- **AC-15:** Transcription execution errors fail explicitly (`TranscriptionError`).
- **AC-16:** Invalid/empty transcription result fails explicitly (`TranscriptionError`).
- **AC-17:** Unit tests do NOT download a real Whisper model.
- **AC-18:** Focused tests use fake/mock transcription backend behavior.
- **AC-19:** All WP-001 tests continue to pass.
- **AC-20:** All WP-002 focused tests pass.
- **AC-21:** No Google Drive code exists.
- **AC-22:** No Thai cleanup/dictionary logic exists.
- **AC-23:** No summarization exists.
- **AC-24:** No Telegram/LINE implementation or stubs exist.
- **AC-25:** No scope beyond WP-002 introduced.
