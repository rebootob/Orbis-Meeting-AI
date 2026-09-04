# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-012 Whisper Runtime Performance Configuration
- **Objective:** Provide runtime configuration of local Whisper speech-to-text parameters (`ORBIS_WHISPER_MODEL`, `ORBIS_WHISPER_DEVICE`, `ORBIS_WHISPER_COMPUTE_TYPE`) via standard environment variables without changing source code. Default values maintain backward compatibility (`large-v3`, `cpu`, `default`). Validation rules enforce safe string trimming, reject empty explicitly-set values, and restrict devices to `cpu` or `cuda` (case-insensitive check). Features include environment config loading (`load_whisper_runtime_config_from_environment`), service factory (`build_transcription_service_from_environment`), status formatting (`format_whisper_runtime_status`), and display in main workflow and control center snapshot with bilingual TH/EN text labels (`ระบบถอดเสียง:`, `Whisper Engine:`).

---

## Scope Rules

### Allowed Changes
- `src/**`
- `tests/**`
- `project-docs/**`

### Forbidden Changes
- GPU auto-probing, `nvidia-smi` execution, cuDNN installer automation, or silent fallback from `cuda` to `cpu`
- Settings UI dropdowns, settings save buttons, settings database, or JSON config file persistence
- Network calls or model downloading during automated unit tests
- Cloud AI APIs (OpenAI, Gemini, Claude, HTTP requests)
- External schedulers, cron, or asyncio rewrites

---

## Acceptance Criteria
- **AC-01:** WP-001 through WP-011 remain working.
- **AC-02:** Environment variables `ORBIS_WHISPER_MODEL`, `ORBIS_WHISPER_DEVICE`, `ORBIS_WHISPER_COMPUTE_TYPE` load cleanly with defaults (`large-v3`, `cpu`, `default`).
- **AC-03:** Whitespace on env values is trimmed; empty explicitly-set values raise `WhisperRuntimeConfigError`.
- **AC-04:** Device validation accepts case-insensitive `cpu` and `cuda`; invalid devices raise `WhisperRuntimeConfigError`.
- **AC-05:** Dependency injection via `model_backend` is preserved in `build_transcription_service_from_environment`.
- **AC-06:** Model lazy-loading is preserved; no model downloading during initialization or tests.
- **AC-07:** Whisper runtime status string formatted cleanly (e.g. `large-v3 | CPU | default`, `medium | CUDA | float16`).
- **AC-08:** Bilingual UI labels added (TH: `ระบบถอดเสียง:`, EN: `Whisper Engine:`) in Control Center and Main Workflow tab.
- **AC-09:** Display-only status without setting save buttons or configuration database.
- **AC-10:** Comprehensive unit test suite (177 tests) passes cleanly.

