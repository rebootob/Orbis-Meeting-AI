# 07_ROADMAP.md — Project Implementation Roadmap

## V1 Development Phases

### Phase 0: Governance & Foundation (ACTIVE: WP-000)
- Establish repository architecture and governance documentation.
- Define authority hierarchy, cost controls, and strict V1 boundaries.

### Phase 1: Audio Ingestion & Local Transcription
- Local audio file loading and Whisper transcription pipeline.
- Raw transcript generation for Thai and English audio.

### Phase 2: Thai Cleanup & Summary Generation
- Company dictionary matching and Thai text post-processing.
- Generation of Quick Summary and Full Summary outputs.

### Phase 3: Google Drive Automation
- Google Drive Inbox folder polling and file ingestion.
- Writing output artifacts (`Quick Summary`, `Full Summary`, `Transcript`, `Original Audio`) to Google Drive Completed folder.

### Phase 4: Quality & Hardening
- Edge-case error handling (corrupted files, network failures, empty recordings).
- Performance optimization and local worker stability.

### Phase 5: V1 User Acceptance Testing & Release
- End-to-end verification with actual PLAUD meeting recordings.
- Final V1 sign-off by Owner.

---

## Post-V1 Roadmap (STRICTLY DEFERRED UNTIL V1 IS CLOSED)
- Telegram notification adapter
- LINE notification adapter
- Speaker diarization & voice recognition
- Cross-meeting search & knowledge base indexing
- Web management dashboard
- Interactive meeting Q&A chatbot
- Additional calendar/meeting integrations (Teams / Zoom)
