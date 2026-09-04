# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-005C PLAUD-like Summary Viewer
- **Objective:** Render the validated current `MeetingSummaryResult` inside the local Tkinter Desktop UI in a clear, human-readable PLAUD-like summary layout. Display meeting title, quick summary, key topics, full summary, decisions, action items (task/owner/due_date with '-' for None), risks/issues, and follow-up items with stable empty-state placeholders. Automatically update the viewer upon successful AI result import and clear it when selecting a new audio file. Zero AI API calls, zero export, zero network dependencies.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Live AI API calls (OpenAI, Anthropic, Gemini SDKs, HTTP requests)
- Export features (PDF/Word), Google Drive API, or sharing adapters
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Database persistence or central web/mobile backends

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-005B remain working.
- **AC-02:** Existing Tkinter queue thread-safety architecture remains intact.
- **AC-03:** Summary Viewer exists in Desktop UI.
- **AC-04:** Viewer renders Meeting Title.
- **AC-05:** Viewer renders Quick Summary.
- **AC-06:** Viewer renders Key Topics.
- **AC-07:** Viewer renders Full Summary.
- **AC-08:** Viewer renders Decisions.
- **AC-09:** Viewer renders Action Items.
- **AC-10:** Viewer renders Risks / Issues.
- **AC-11:** Viewer renders Follow-up.
- **AC-12:** Action Item Task is displayed.
- **AC-13:** Action Item Owner is displayed.
- **AC-14:** Action Item Due Date is displayed.
- **AC-15:** None owner/due_date are shown safely as "-".
- **AC-16:** Empty lists render stable human-readable placeholders.
- **AC-17:** Summary fields are read-only.
- **AC-18:** Successful AI import automatically updates viewer.
- **AC-19:** Viewer uses existing `current_summary_result`.
- **AC-20:** Selecting a new audio clears stale summary viewer content.
- **AC-21:** Importing a second valid summary replaces previous viewer content.
- **AC-22:** Thai text displays without transformation.
- **AC-23:** English text displays without transformation.
- **AC-24:** Long summary content remains scrollable/readable.
- **AC-25:** No summary generation logic duplicated.
- **AC-26:** No AI API/network call.
- **AC-27:** No Google Drive implementation.
- **AC-28:** No export PDF/Word.
- **AC-29:** No Telegram/LINE.
- **AC-30:** No web/mobile app.
- **AC-31:** No database.
- **AC-32:** No new third-party dependency.
- **AC-33:** Existing tests pass.
- **AC-34:** Focused WP-005C tests pass.
- **AC-35:** No scope beyond WP-005C.
