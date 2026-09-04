# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-008 Automatic Job Runner (Single-Host Ingestion & Processing)
- **Objective:** Implement a single-host automatic job runner (`src/orbis_meeting/job_runner.py`) that periodically scans `01_Inbox`, checks file stability using real WP-007 stability logic, claims the oldest stable audio into `02_Processing`, runs Whisper transcription and text cleanup automatically, stores the cleaned transcript result in session state, and pauses at `WAITING_FOR_SUMMARY`. The runner processes only one active workflow job at a time, routes per-job failures to `99_Error`, survives job failures, and allows existing manual AI handoff / complete workflow job steps to finish the meeting lifecycle before resuming on subsequent scans.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Automatic AI summary generation (OpenAI, Gemini, Claude, local LLMs)
- Google Drive API, OAuth, service accounts, or Google Cloud SDKs
- Multi-host coordination, distributed locks, or multi-worker concurrency
- Telegram, LINE, email, PDF/Word export, databases, or web/mobile UIs
- External schedulers, OS services, cron, or asyncio rewrites

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-007 remain working.
- **AC-02:** Automatic job runner module exists (`src/orbis_meeting/job_runner.py`).
- **AC-03:** Single Processing Host model preserved.
- **AC-04:** Runner can start/stop cleanly.
- **AC-05:** Runner periodically scans Inbox.
- **AC-06:** No busy loop (uses `threading.Event` wait).
- **AC-07:** Real stability guard reused.
- **AC-08:** Unstable file remains in Inbox.
- **AC-09:** Oldest deterministic file selected.
- **AC-10:** Only one active workflow job at a time.
- **AC-11:** Audio auto-claimed into Processing.
- **AC-12:** Whisper runs automatically after claim.
- **AC-13:** Cleanup runs automatically after transcription.
- **AC-14:** Result stored as cleaned transcript.
- **AC-15:** Runner stops at WAITING_FOR_SUMMARY.
- **AC-16:** No summary generated automatically.
- **AC-17:** Existing manual AI handoff remains usable.
- **AC-18:** Existing workflow Complete remains usable.
- **AC-19:** No second job claimed while waiting for summary.
- **AC-20:** After Complete, runner can resume.
- **AC-21:** Processing failure routes to Error (`99_Error`).
- **AC-22:** Failed audio preserved in Error directory.
- **AC-23:** Runner survives per-job failure.
- **AC-24:** Manual mode remains usable when runner stopped.
- **AC-25:** Manual mode cannot corrupt active auto workflow.
- **AC-26:** Tk thread safety preserved (queue events, no direct widget calls).
- **AC-27:** No Google API/OAuth.
- **AC-28:** No AI API.
- **AC-29:** No local LLM yet.
- **AC-30:** No Telegram/LINE.
- **AC-31:** No database.
- **AC-32:** No multi-worker.
- **AC-33:** No external scheduler.
- **AC-34:** No third-party dependency expected.
- **AC-35:** Focused and full tests pass.
- **AC-36:** No scope beyond WP-008.
