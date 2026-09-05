# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-013 Ollama Structured Local Summary Adapter
- **Objective:** Implement a local CLI adapter module (`src/orbis_meeting/ollama_structured_adapter.py`) that connects `LocalCommandSummaryProvider` to the local Ollama HTTP API (`http://127.0.0.1:11434/api/generate`). Reads summary prompt payload from UTF-8 stdin, sends JSON Schema POST payload with `think=false`, `stream=false`, `temperature=0`, extracts raw model JSON response string, and writes response string directly to stdout. Integrates with existing `LocalCommandSummaryProvider` and `AutomaticSummaryService` without weakening strict machine-to-machine JSON validation.

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- Weakening `parse_automatic_summary_response()` or accepting surrounding prose/markdown fences
- Scraping first/last braces or silently repairing invalid JSON
- Adding cloud AI APIs (OpenAI, Gemini, Claude, HTTP requests to external servers)
- Adding Telegram, LINE, Email, web/mobile UI, or database
- Auto-downloading Ollama models or installing Ollama
- External schedulers, cron, or asyncio rewrites

---

## Acceptance Criteria
- **AC-01:** Existing strict automatic parser (`parse_automatic_summary_response`) remains unchanged and enforced.
- **AC-02:** Adapter uses only local Ollama HTTP API (`http://127.0.0.1:11434/api/generate`).
- **AC-03:** Qwen3 thinking disabled (`think: false`).
- **AC-04:** Streaming disabled (`stream: false`).
- **AC-05:** Temperature set to 0 (`options: {temperature: 0}`).
- **AC-06:** Explicit JSON Schema matching Orbis summary contract sent in request (`format`).
- **AC-07:** Thai UTF-8 text survives request/response path intact.
- **AC-08:** stdout contains raw model response string only (no log lines, prefixes, or markdown formatting).
- **AC-09:** Failures write to stderr and return non-zero exit code.
- **AC-10:** No live network requirement in automated unit tests (HTTP boundary mocked).
- **AC-11:** Existing regression suite passes cleanly (192 tests).
- **AC-12:** Runtime configuration works via `ORBIS_SUMMARY_COMMAND_JSON` + `LocalCommandSummaryProvider`.
- **AC-13:** No V1 scope expansion.
