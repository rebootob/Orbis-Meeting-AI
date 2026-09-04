# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-006 Local Export Package
- **Objective:** Add a local "Save Meeting Package..." workflow to the Orbis Desktop UI. When triggered by the user, export a complete meeting package folder containing `Summary.md`, `Transcript.txt`, `AI_SUMMARY_READY.md`, and `audio_reference.json` into a user-selected output directory. Ensure overwrite safety with unique sibling folder naming, atomic temp-folder write strategy, safe filename sanitization, UTF-8 Thai/English text preservation, and zero audio copying/moving or external cloud API calls.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Google Drive API or cloud storage integrations
- PDF or Word / DOCX export formats
- Live AI API calls (OpenAI, Anthropic, Gemini SDKs, HTTP requests)
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Copying, moving, or modifying original audio files
- Database persistence or central web/mobile backends

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-005C remain working.
- **AC-02:** Local export module exists (`src/orbis_meeting/export_package.py`).
- **AC-03:** UI contains Save Meeting Package action.
- **AC-04:** Export requires metadata + cleaned transcript + summary.
- **AC-05:** User chooses output parent directory.
- **AC-06:** Cancel causes no error.
- **AC-07:** A unique meeting folder is created.
- **AC-08:** Folder name uses safe title.
- **AC-09:** No existing package is overwritten.
- **AC-10:** Summary.md exists.
- **AC-11:** Transcript.txt exists.
- **AC-12:** AI_SUMMARY_READY.md exists.
- **AC-13:** audio_reference.json exists.
- **AC-14:** Summary.md uses current MeetingSummaryResult.
- **AC-15:** Transcript.txt uses cleaned transcript.
- **AC-16:** AI_SUMMARY_READY.md reuses WP-005B builder.
- **AC-17:** audio_reference.json uses WP-001 metadata.
- **AC-18:** Original audio is not modified.
- **AC-19:** Original audio is not copied.
- **AC-20:** Original audio is not moved.
- **AC-21:** Thai text preserved.
- **AC-22:** Action items render safely.
- **AC-23:** None owner/due date render "-".
- **AC-24:** Empty sections have stable placeholders.
- **AC-25:** Export button disabled before summary ready.
- **AC-26:** Export button enabled after validated summary import.
- **AC-27:** New audio resets export readiness.
- **AC-28:** No PDF/Word.
- **AC-29:** No Google Drive.
- **AC-30:** No Telegram/LINE.
- **AC-31:** No API/network.
- **AC-32:** No database.
- **AC-33:** No third-party dependency.
- **AC-34:** Focused tests pass.
- **AC-35:** Existing tests pass.
- **AC-36:** No scope beyond WP-006.
