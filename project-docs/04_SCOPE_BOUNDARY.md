# 04_SCOPE_BOUNDARY.md — Scope Boundaries & Control Rules

## 1. Golden Rule of Scope Control
> **Future compatibility does not authorize present implementation.**

---

## 2. IN V1 SCOPE (LOCKED — OWNER APPROVED EXTENSION)
- **Audio Source:** PLAUD audio files (`.mp3`, `.wav`, `.m4a`).
- **User Interface:** Local Desktop UI Shell (Tkinter/ttk).
- **Ingestion:** Local file selection & Google Drive Inbox folder polling.
- **Processing:** Local background worker processing.
- **Transcription:** Local Whisper transcription engine.
- **Post-Processing:** Thai text cleanup & company dictionary term replacement.
- **Summarization:** Provider-neutral meeting summary generation.
- **Output:** Writing processed summaries, transcript, and original audio reference into Google Drive Completed folder and displaying locally in Desktop UI.
- **V1 Required Output Contract:**
  1. AI-generated Meeting Title
  2. Quick Summary
  3. Key Topics
  4. Full Summary
  5. Decisions
  6. Action Items (with optional task, owner, due_date)
  7. Risks / Issues
  8. Follow-up
  9. Cleaned Transcript
  10. Original Audio reference/file

---

## 3. STRICTLY OUT OF V1 SCOPE
- **Web dashboard / browser-hosted application** (No admin panels, web interfaces, or frontend frameworks)
- **Mobile Application** (No iOS/Android apps)
- **Telegram integration** (No notifications, bots, webhooks, or stubs)
- **LINE integration** (No notifications, bots, Flex Messages, or stubs)
- **Voice / Speaker Recognition** (No speaker diarization or voice profiling)
- **Cross-Meeting Search** (No vector database or RAG indexing across meetings)
- **Chatbot / Q&A interface** (No interactive chat query system)
- **Teams / Zoom Integration** (No direct meeting bot joins)
- **Central Database** (No SQL/NoSQL database infrastructure; file-based only)
- **User Management** (No authentication, RBAC, or user profiles)
- **Cloud Production Deployment** (No AWS/GCP serverless or Kubernetes setups)

---

## 4. FUTURE ROADMAP (POST-V1 ONLY)
- Telegram notification adapter
- LINE notification adapter
- Speaker diarization & recognition
- Cross-meeting search & knowledge base
- Web dashboard & meeting history management
- Interactive AI Q&A chatbot
- Direct video conference integrations (Teams / Zoom)
