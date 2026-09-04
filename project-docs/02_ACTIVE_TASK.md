# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-009 Automatic Summary Engine (Local-First / Provider-Neutral / Zero Cloud API)
- **Objective:** Implement local automatic summary generation (`src/orbis_meeting/auto_summary.py`) using a provider-neutral local command interface (`LocalCommandSummaryProvider`, `AutomaticSummaryService`). Integrate with `AutomaticJobRunner` (`src/orbis_meeting/job_runner.py`) so that after transcription and text cleanup succeed, if an automatic summary service is configured, the runner automatically transitions through `SUMMARIZING`, parses/validates raw JSON into a canonical `MeetingSummaryResult`, updates session state, and transitions to `SUMMARY_READY`. If summary generation fails or is unconfigured, the job is preserved safely for manual AI handoff without routing to `99_Error`.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Cloud AI APIs (OpenAI, Gemini, Claude, HTTP requests)
- Ollama CLI / LLM model downloads or installs during WP-009
- Shell injection / `shell=True` in subprocess calls
- Automatic call to `complete_workflow_job()` (belongs to WP-010)
- Multi-host coordination, distributed locks, or multi-worker concurrency
- Telegram, LINE, email, PDF/Word export, databases, or web/mobile UIs
- External schedulers, OS services, cron, or asyncio rewrites

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-008 remain working.
- **AC-02:** `src/orbis_meeting/auto_summary.py` created with `AutomaticSummaryError`, `LocalCommandSummaryProvider`, `AutomaticSummaryService`.
- **AC-03:** Local provider executes command via stdlib `subprocess` without `shell=True`.
- **AC-04:** Complete prompt passed via stdin without truncation (or raises error if `max_input_chars` exceeded).
- **AC-05:** Reuses WP-004 `MeetingSummaryResult` schema & strict JSON validation via `import_manual_ai_result`.
- **AC-06:** Runner states extended with `SUMMARIZING`, `SUMMARY_READY`, `SUMMARY_ERROR`.
- **AC-07:** Runner automatically executes summary after cleanup when service is configured.
- **AC-08:** `current_summary_result` populated and `SUMMARY_IMPORTED` emitted on success.
- **AC-09:** Automatic summary failure transitions to `SUMMARY_ERROR`, preserving job in `02_Processing` for manual AI fallback.
- **AC-10:** Single-job policy & stop drain safety preserved.
- **AC-11:** `complete_workflow_job()` is NOT called automatically in WP-009.
- **AC-12:** Zero cloud AI API calls.
- **AC-13:** Focused and full tests pass.
