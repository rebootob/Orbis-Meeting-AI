# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-004 Meeting Summary Foundation (Cloud-Text-First / Provider-Neutral)
- **Objective:** Implement a provider-neutral Meeting Summary Foundation that consumes cleaned `TranscriptionResult` objects from WP-003, builds deterministic prompt/summary requests, enforces vendor-neutral provider boundaries, and validates structured meeting summary responses.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Installing or calling external LLM SDKs (OpenAI, Anthropic, Gemini, LangChain, etc.)
- Real HTTP/API calls or network operations in unit tests
- Real API key requirements or secret management (`.env`, secrets)
- Google Drive API, authentication, or polling
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Database, vector search, or RAG framework
- Web/Mobile UI or API servers

---

## Acceptance Criteria
- **AC-01:** WP-001 audio intake remains working.
- **AC-02:** WP-002 transcription remains working.
- **AC-03:** WP-003 cleanup remains working.
- **AC-04:** Summary module exists (`src/orbis_meeting/summary.py`).
- **AC-05:** Summary input accepts cleaned `TranscriptionResult`.
- **AC-06:** Input `TranscriptionResult` is not mutated.
- **AC-07:** `SummaryRequest` contains minimum necessary text data (`job_id`, `language`, `transcript_text`).
- **AC-08:** `SummaryProvider` boundary exists and is vendor-neutral (ABC/Protocol).
- **AC-09:** No real cloud provider or network call implementation exists in WP-004.
- **AC-10:** `MeetingSummaryResult` contains `job_id`, `language`, `quick_summary`, `full_summary`, `decisions`, `action_items`, `risks`, `follow_up`.
- **AC-11:** `ActionItem` contains `task`, `owner`, `due_date`.
- **AC-12:** `owner` may be `None`/`null`.
- **AC-13:** `due_date` may be `None`/`null`.
- **AC-14:** Structured provider response is strictly validated.
- **AC-15:** Missing required fields are rejected (`SummaryError`).
- **AC-16:** Wrong field types are rejected (`SummaryError`).
- **AC-17:** Empty or invalid summary output is rejected (`SummaryError`).
- **AC-18:** Provider exceptions are wrapped in predictable `SummaryError`.
- **AC-19:** Prompt explicitly forbids fabrication.
- **AC-20:** Prompt instructs `null` for unknown owner/date.
- **AC-21:** Prompt requires structured output contract.
- **AC-22:** Prompt contains no request for chain-of-thought.
- **AC-23:** No audio data is supplied to summary provider.
- **AC-24:** No filesystem path is supplied to summary provider.
- **AC-25:** No API key is required.
- **AC-26:** Unit tests use fake provider only (`FakeSummaryProvider`).
- **AC-27:** No network calls occur in tests.
- **AC-28:** All WP-001 tests pass.
- **AC-29:** All WP-002 tests pass.
- **AC-30:** All WP-003 tests pass.
- **AC-31:** All WP-004 tests pass.
- **AC-32:** No Google Drive implementation exists.
- **AC-33:** No Telegram/LINE code or stubs exist.
- **AC-34:** No speaker diarization exists.
- **AC-35:** No new third-party dependency added.
- **AC-36:** No scope beyond WP-004 introduced.
