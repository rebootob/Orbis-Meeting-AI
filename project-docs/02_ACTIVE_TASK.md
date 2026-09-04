# 02_ACTIVE_TASK.md — Active Work Package

## Work Package Details
- **Active Work Package:** WP-000 Repository Foundation + Governance
- **Objective:** Establish repository governance, authority structure, cost controls, and strict V1 scope boundaries before starting any application code implementation.

---

## Scope Rules

### Allowed Changes
- `README.md` (if necessary)
- `project-docs/**`

### Forbidden Changes
- `src/**`
- Application code or implementation scripts
- Third-party dependencies or environment configuration
- Google Drive API or client implementation
- Whisper transcription engine or wrappers
- Telegram notification adapters or stubs
- LINE notification adapters or stubs

---

## Acceptance Criteria
1. All nine governance documents exist under `project-docs/`.
2. V1 scope is explicit across governance files.
3. Out-of-scope items for V1 are explicitly listed.
4. Authority hierarchy (Owner / ChatGPT / Antigravity / Claude Code) is explicitly defined.
5. One-active-work-package rule is explicitly mandated.
6. STOP conditions are explicitly specified.
7. Telegram and LINE notifications remain future roadmap items only.
8. Zero application code or stubs introduced during WP-000.
