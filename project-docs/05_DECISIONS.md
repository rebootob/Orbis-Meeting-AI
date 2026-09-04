# 05_DECISIONS.md — Architecture Decision Records (ADRs)

## ADR-001: Local-First Execution Strategy
- **Status:** APPROVED
- **Context:** Running transcription in the cloud incurs recurring per-minute audio processing costs.
- **Decision:** Execute worker processing and transcription locally on local computing hardware using open-source models (Whisper).
- **Consequences:** Eliminates recurring cloud transcription costs; requires local hardware resource management.

---

## ADR-002: Google Drive as V1 User-Facing Interface
- **Status:** APPROVED
- **Context:** Users need an accessible way to submit audio and retrieve summaries without complex custom UI development.
- **Decision:** Use Google Drive folders (`Inbox` and `Completed`) as the primary user workflow interface for V1.
- **Consequences:** Eliminates web/mobile frontend overhead; simplifies user interaction to file drag-and-drop.

---

## ADR-003: No Web/Mobile UI in V1
- **Status:** APPROVED
- **Context:** Building custom user interfaces increases scope, timeline, and security surface area.
- **Decision:** Strictly omit web UI, admin dashboards, and mobile applications from V1.
- **Consequences:** Keeps V1 scope strictly bounded to core audio processing and summary generation.

---

## ADR-004: Whisper-Based Local Transcription
- **Status:** APPROVED
- **Context:** High accuracy Thai and English speech recognition is required without ongoing vendor lock-in or cost.
- **Decision:** Adopt OpenAI Whisper (local model execution) as the primary transcription engine.
- **Consequences:** Requires local GPU/CPU compute; zero API transcription fees.

---

## ADR-005: Avoid Central Database Infrastructure in V1
- **Status:** APPROVED
- **Context:** Setting up and managing a database engine adds operational complexity for single-workflow processing.
- **Decision:** Use local filesystem and Google Drive file structures for tracking processed items in V1. No SQL or NoSQL database will be provisioned.
- **Consequences:** Minimal infrastructure setup; file-based state tracking.

---

## ADR-006: Defer Notification Adapters (Telegram / LINE)
- **Status:** APPROVED
- **Context:** Chat app integrations require bot token management, webhooks, and complex API maintenance.
- **Decision:** Defer all notification delivery channels until post-V1 release.
- **Consequences:** Zero notification infrastructure code or stubs in V1 codebase.

---

## ADR-007: Single Active Execution Agent Constraint
- **Status:** APPROVED
- **Context:** Concurrent execution agents (e.g. Antigravity and Claude Code) can create code conflicts, duplicate work, and waste credits.
- **Decision:** Only one execution agent may be active at any given time.
- **Consequences:** Prevents agent collision and maintains clear audit trails.

---

## ADR-008: Claude Code Agent Default STOP State
- **Status:** APPROVED
- **Context:** Antigravity handles execution within defined boundaries. Secondary agents should not run unguided.
- **Decision:** Claude Code is set to STOP by default and requires explicit human Owner authorization to be engaged.
- **Consequences:** Eliminates unintended secondary agent invocations.
