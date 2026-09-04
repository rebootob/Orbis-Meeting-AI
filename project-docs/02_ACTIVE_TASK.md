# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-010 Automatic End-to-End Completion
- **Objective:** Extend `AutomaticJobRunner` (`src/orbis_meeting/job_runner.py`) so that when a workflow job reaches `SUMMARY_READY` via local automatic summary, the runner automatically transitions state to `COMPLETING`, invokes `controller.complete_workflow_job()`, verifies exported package outputs in `03_Completed` (Summary.md, Transcript.txt, AI_SUMMARY_READY.md, audio_reference.json, and original audio), clears active workflow session state, transitions state to `IDLE`, and allows subsequent runner scans to process the next Inbox audio file automatically. If completion fails, job state is preserved in `02_Processing` without routing to `99_Error`, state transitions to `COMPLETION_ERROR`, and manual retry is allowed.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Cloud AI APIs (OpenAI, Gemini, Claude, HTTP requests)
- Google Drive API, OAuth, service accounts
- Telegram, LINE, Email, PDF/DOCX export, databases, web/mobile UIs
- Speaker diarization, cross-meeting search, multi-host concurrency
- External schedulers, cron, or asyncio rewrites

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-009 remain working.
- **AC-02:** Automatic completion occurs after automatic `SUMMARY_READY`.
- **AC-03:** `COMPLETING` and `COMPLETION_ERROR` runner states exist.
- **AC-04:** Completion reuses existing workflow completion primitive (`complete_workflow_job`).
- **AC-05:** Package created under `03_Completed`.
- **AC-06:** Required package files exist (`Summary.md`, `Transcript.txt`, `AI_SUMMARY_READY.md`, `audio_reference.json`).
- **AC-07:** Workflow-owned original audio is preserved/finalized safely without byte modification.
- **AC-08:** Successful completion clears active workflow session state.
- **AC-09:** Runner returns to `IDLE` after completion.
- **AC-10:** Runner can process next Inbox meeting on subsequent scan (single active job policy maintained).
- **AC-11:** Completion failure transitions to `COMPLETION_ERROR`, preserving session data and blocking next job.
- **AC-12:** Manual retry/recovery possible.
- **AC-13:** Stop/drain safety preserved.
- **AC-14:** Focused and full tests pass.
