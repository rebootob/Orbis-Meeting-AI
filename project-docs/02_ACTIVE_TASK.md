# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-005B Manual AI Handoff
- **Objective:** Add a Manual AI Handoff workflow to the local Desktop UI. Generate an AI-ready payload (combining template focus, instructions, schema, and cleaned transcript), copy it to the local clipboard for manual pasting into ChatGPT/Gemini/Claude, accept manually pasted AI JSON responses (including markdown code blocks), and parse/validate the response using the existing WP-004 `MeetingSummaryResult` contract without making any external API/network calls.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Live AI API calls (OpenAI, Anthropic, Gemini SDKs, HTTP requests)
- Full summary viewer rendering (reserved for WP-005C)
- Google Drive API, export features (PDF/Word), or sharing
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Database persistence or central web/mobile backends

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-005A features remain working.
- **AC-02:** Manual AI handoff module exists (`src/orbis_meeting/manual_handoff.py`).
- **AC-03:** Built-in template selector supports `General Meeting`, `Management Meeting`, `Project Meeting`, and `Problem Solving / RCA`.
- **AC-04:** `build_manual_ai_payload()` generates one AI-ready payload combining template emphasis, WP-004 prompt rules, JSON schema, and cleaned transcript text.
- **AC-05:** `Copy for AI` action requires an existing cleaned transcript.
- **AC-06:** `Copy for AI` places payload on the local OS clipboard safely.
- **AC-07:** Clear user feedback ("Copied. Paste into ChatGPT, Gemini, or Claude.") is shown upon copying.
- **AC-08:** `Import AI Result` area accepts raw JSON or markdown-wrapped ```json ... ``` text.
- **AC-09:** `import_manual_ai_result()` strips markdown code blocks if present and parses JSON.
- **AC-10:** Raw JSON is validated against WP-004 `parse_and_validate_summary_response()` schema.
- **AC-11:** Valid imported `MeetingSummaryResult` is stored in the local session controller.
- **AC-12:** Malformed JSON or invalid schema raises a explicit `ManualHandoffError`.
- **AC-13:** Zero external network or API calls are made.
- **AC-14:** Desktop UI shell includes template dropdown, Copy button, AI Result text area, and Import button.
- **AC-15:** All unit tests across WP-001 through WP-005B pass cleanly.
