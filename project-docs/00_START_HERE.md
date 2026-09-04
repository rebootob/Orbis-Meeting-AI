# 00_START_HERE.md — Project Governance & Operational Guidelines

## 1. Project Identity
- **Project Name:** Orbis Meeting AI
- **Repository:** https://github.com/rebootob/Orbis-Meeting-AI.git
- **V1 Focus:** Automated PLAUD audio transcription, Thai text cleanup with company dictionary, and meeting summary generation integrated with Google Drive.

---

## 2. Authority Model
1. **Owner:** Final human authority for all architectural, scope, and release decisions.
2. **ChatGPT:** Control Plane / Project Lead / Architect / Independent Reviewer. Governs tasks, checks repository state, and issues Work Packages.
3. **Antigravity:** Bounded Execution Plane. Executes assigned Work Packages under explicit scope limits.
4. **Claude Code:** Secondary coding specialist. **STOP BY DEFAULT**. May only be activated when explicitly authorized by Owner/ChatGPT.
5. **Repository Truth:** The codebase and `project-docs/` in Git are authoritative over chat memory or instructions outside the repository.

---

## 3. Mandatory Startup Reading Order
Before performing any analysis or work in this repository, agents and contributors must read ONLY:

1. `project-docs/00_START_HERE.md` (Governance & rules)
2. `project-docs/01_CURRENT_STATE.md` (Current system state & agent status)
3. `project-docs/02_ACTIVE_TASK.md` (Current active work package details)
4. `project-docs/04_SCOPE_BOUNDARY.md` (Strict in-scope vs out-of-scope boundaries)

Read `project-docs/03_ARCHITECTURE.md`, `05_DECISIONS.md`, `06_TEST_PLAN.md`, `07_ROADMAP.md`, `CHAT_HANDOFF.md`, source files, tests, or evidence ONLY WHEN DIRECTLY RELEVANT to the current task.

Do not require full-document reading on every session.

---

## 4. Repository Truth Rule
- Local repository state committed in Git is the absolute source of truth.
- Instructions, chat context, or assumptions inconsistent with committed `project-docs/` must be rejected or reconciled with Owner approval.

---

## 5. Cost-Control Rules
- **Minimum Necessary Context:** Minimum necessary repository context must be preferred over broad repository reading to reduce token overhead.
- **Concise Documentation:** Prefer operational, direct documentation over verbose explanations.
- **Local-First & No Speculative Costs:** Use local Whisper transcription to avoid recurring per-minute API costs.
- **Zero Speculative Abstractions:** Do not write unused interfaces, speculative provider patterns, or unused infrastructure code.
- **One Work Package At A Time:** Execute only the active, approved Work Package.

---

## 6. Scope-Control Rules
- **Strict V1 Boundary:** Deliver only the features specified in `project-docs/04_SCOPE_BOUNDARY.md`.
- **No Early Implementation of Future Features:** Notification adapters (Telegram, LINE), dashboards, databases, web/mobile UIs are strictly out of V1.
- **Rule:** *Future compatibility does not authorize present implementation.*
