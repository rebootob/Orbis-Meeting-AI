# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-011 Control Center / Job History
- **Objective:** Provide a filesystem-based read-only Control Center & Job History module (`src/orbis_meeting/control_center.py`) and a bilingual (Thai / English) Tkinter UI integration (`src/orbis_meeting/ui.py`). Features include counting audio files in `01_Inbox`, processing jobs in `02_Processing`, completed packages in `03_Completed`, and error directories in `99_Error`; displaying up to 10 most recent completed meetings and error packages (parsing `error.json` with safe fallback handling); offering safe native OS folder opening (`os.startfile`); supporting runtime language toggle (TH | EN) without app restart while leaving internal runner states ("TRANSCRIBING", "COMPLETING", etc.) unchanged; and enabling "Retry Completion" ONLY when runner state is `COMPLETION_ERROR`.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Database (SQLite, PostgreSQL, ORM) or web dashboard
- Cloud AI APIs (OpenAI, Gemini, Claude, HTTP requests)
- Google Drive API, OAuth, service accounts
- Telegram, LINE, Email, PDF/DOCX export, mobile UIs
- Speaker diarization, cross-meeting search, multi-host concurrency
- External schedulers, cron, or asyncio rewrites

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-010 remain working.
- **AC-02:** Pure read-only filesystem scanning without database or file mutations in Control Center.
- **AC-03:** Accurate folder counts for `01_Inbox`, `02_Processing`, `03_Completed`, and `99_Error`.
- **AC-04:** Displays top 10 recent completed packages (sorted by mtime descending) with title extraction from `Summary.md`.
- **AC-05:** Displays top 10 recent error packages (sorted by mtime descending) with safe fallback if `error.json` is corrupt or missing.
- **AC-06:** Native OS folder opening (`open_folder_in_os`) handles non-existent paths gracefully.
- **AC-07:** Bilingual UI support (TH / EN) with runtime language toggle.
- **AC-08:** Internal state strings remain unchanged; translated strictly for display.
- **AC-09:** Retry Completion button enabled ONLY when runner state is `COMPLETION_ERROR`.
- **AC-10:** Comprehensive unit test suite (164 tests) passes cleanly.
