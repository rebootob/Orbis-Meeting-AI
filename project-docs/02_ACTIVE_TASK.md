# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-007 Google Drive Multi-Device Workflow (Single Processing Host)
- **Objective:** Implement local sync-folder workflow support for Orbis Meeting AI to enable multi-device audio submission via Google Drive Desktop without requiring Google APIs or OAuth. Orbis manages `01_Inbox`, `02_Processing`, `03_Completed`, and `99_Error` directories under a user-configured workflow root. Enforces single-processing-host operational constraint, file stability check before claiming, deterministic inbox discovery/ordering, safe claim to processing, failure handling to `99_Error` with `error.json`, and completion package export to `03_Completed` reusing WP-006.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Google Drive API, OAuth, service accounts, or Google Cloud SDKs
- Distributed locking, leases, heartbeat, or multi-worker coordination
- Automatic background daemon or watcher threads
- PDF/Word export, Telegram/LINE, email, or database integrations
- Live AI API calls (OpenAI, Anthropic, Gemini SDKs, HTTP requests)

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-006 remain working.
- **AC-02:** Local drive workflow module exists (`src/orbis_meeting/drive_workflow.py`).
- **AC-03:** No Google API is used.
- **AC-04:** Workflow root is user-configurable.
- **AC-05:** Required 4 workflow directories can be initialized.
- **AC-06:** Inbox discovery accepts only supported audio.
- **AC-07:** File stability guard exists.
- **AC-08:** Inbox ordering deterministic.
- **AC-09:** One stable audio can be claimed into Processing.
- **AC-10:** Claim preserves audio bytes.
- **AC-11:** Job folder is collision-safe.
- **AC-12:** Single Processing Host limitation is documented.
- **AC-13:** No multi-worker locking exists.
- **AC-14:** No watcher/daemon required.
- **AC-15:** Existing manual Browse Audio path remains working.
- **AC-16:** Workflow-origin job distinguished from manual-origin job.
- **AC-17:** Workflow completion requires validated summary.
- **AC-18:** Completion reuses WP-006 exporter.
- **AC-19:** Completed output is created under 03_Completed.
- **AC-20:** No existing Completed package is overwritten.
- **AC-21:** Failure path preserves audio under 99_Error.
- **AC-22:** error.json contains bounded error metadata.
- **AC-23:** No failed audio silently deleted.
- **AC-24:** UI can select/validate workflow root.
- **AC-25:** UI can explicitly load next Inbox audio.
- **AC-26:** UI can explicitly complete ready workflow job.
- **AC-27:** UI never claims actual cloud upload success.
- **AC-28:** No OAuth/API credentials.
- **AC-29:** No Google Drive SDK.
- **AC-30:** No database.
- **AC-31:** No Telegram/LINE.
- **AC-32:** No AI API.
- **AC-33:** No web/mobile app.
- **AC-34:** No distributed worker design.
- **AC-35:** No new third-party dependency expected.
- **AC-36:** Focused tests pass.
- **AC-37:** Existing tests pass.
- **AC-38:** No scope beyond WP-007.
