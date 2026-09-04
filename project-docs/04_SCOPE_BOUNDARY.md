# 04_SCOPE_BOUNDARY.md — Scope Boundaries & Control Rules

## 1. Golden Rule of Scope Control
> **Future compatibility does not authorize present implementation.**

---

## 2. IN V1 SCOPE (LOCKED)
- **Audio Source:** PLAUD audio files.
- **Ingestion:** Google Drive Inbox polling / monitoring.
- **Processing:** Local background worker processing.
- **Transcription:** Local Whisper transcription.
- **Post-Processing:** Thai text cleanup & company dictionary term replacement.
- **Summarization:** Meeting summary generation (Quick Summary & Full Summary).
- **Output:** Writing processed summaries, transcript, and original audio reference into Google Drive Completed folder.
- **V1 Required Outputs:**
  1. Quick Summary
  2. Full Summary
  3. Transcript
  4. Original Audio reference/file

---

## 3. STRICTLY OUT OF V1 SCOPE
- **Telegram integration** (No notifications, bots, webhooks, or stubs)
- **LINE integration** (No notifications, bots, Flex Messages, or stubs)
- **Dashboard / Web UI** (No admin panels, web interfaces, or frontend frameworks)
- **Mobile Application** (No iOS/Android apps)
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
- direct video conference integrations (Teams / Zoom)
