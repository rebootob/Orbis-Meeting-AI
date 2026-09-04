# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-003 Thai Cleanup + Company Dictionary Foundation
- **Objective:** Implement a deterministic transcript cleanup layer for Thai/English mixed meeting text and a bounded, file-based company dictionary replacement mechanism for validated WP-002 `TranscriptionResult` objects.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `config/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- LLM / OpenAI / Gemini / Claude API calls or summarization
- Punctuation repair or grammar rewriting using AI/embeddings
- External third-party NLP/regex packages (pandas, spaCy, transformers, etc.)
- Google Drive API, authentication, or polling
- Telegram or LINE notification adapters or stubs
- Speaker diarization, voice profiling, or speaker recognition
- Database, vector search, or state database
- Web/Mobile UI or API servers

---

## Acceptance Criteria
- **AC-01:** WP-001 audio intake remains working.
- **AC-02:** WP-002 transcription layer remains working.
- **AC-03:** Cleanup module exists under current package (`src/orbis_meeting/text_cleanup.py`).
- **AC-04:** Cleanup accepts WP-002 `TranscriptionResult`.
- **AC-05:** Cleanup returns `job_id`, `language`, `full_text`, `segments`.
- **AC-06:** Segment `start`/`end` timestamps are preserved exactly.
- **AC-07:** Segment ordering is preserved.
- **AC-08:** Whitespace normalization is deterministic (collapse repeated spaces, trim).
- **AC-09:** Thai text is preserved correctly.
- **AC-10:** English text is preserved correctly.
- **AC-11:** Thai/English mixed text is supported.
- **AC-12:** Numbers/dates/technical codes are preserved.
- **AC-13:** Company dictionary is editable outside source code (`config/company_dictionary.json`).
- **AC-14:** Dictionary mappings are applied deterministically.
- **AC-15:** Overlapping dictionary keys prefer longer match.
- **AC-16:** Cleanup is idempotent: `clean(clean(x)) == clean(x)`.
- **AC-17:** Original `TranscriptionResult` is not mutated.
- **AC-18:** No LLM/API use exists.
- **AC-19:** No Google Drive implementation exists.
- **AC-20:** No Summary implementation exists.
- **AC-21:** No Telegram/LINE code or stubs exist.
- **AC-22:** No new third-party NLP dependency added.
- **AC-23:** Focused tests cover normalization and dictionary behavior.
- **AC-24:** All WP-001 tests still pass.
- **AC-25:** All WP-002 tests still pass.
- **AC-26:** All WP-003 tests pass.
- **AC-27:** No scope beyond WP-003 introduced.
