# 06_TEST_PLAN.md — V1 Verification & Test Strategy

> **NOTE:** This document defines test categories and criteria for future V1 implementation. **NO TEST CODE OR TEST HARNESSES ARE IMPLEMENTED IN WP-000.**

---

## 1. Test Categories & Verification Criteria

### 1.1 Audio Ingestion
- **Scope:** Ingestion of PLAUD audio recordings from Google Drive Inbox.
- **Criteria:** Correctly identify supported audio formats (`.mp3`, `.wav`, `.m4a`), verify file size integrity, and ignore non-audio files.

### 1.2 Transcription Execution
- **Scope:** Local Whisper model invocation.
- **Criteria:** Accurate speech-to-text conversion for Thai and English spoken content; timestamp alignment and complete text capture without silent truncation.

### 1.3 Thai Text Handling & Dictionary Replacement
- **Scope:** Post-processing cleanup and company dictionary substitution.
- **Criteria:** Correct spelling correction of Thai technical terms, company names, and jargon defined in the company dictionary.

### 1.4 Summary Output Generation
- **Scope:** LLM summary generation pipeline.
- **Criteria:** Verification of both required summary outputs:
  - **Quick Summary:** Key decisions, action items, executive bullet points.
  - **Full Summary:** Detailed meeting breakdown by topic.

### 1.5 Google Drive Workflow
- **Scope:** End-to-end file management in Google Drive.
- **Criteria:** Reliable reading from `Inbox`, atomic write of output artifacts (`Quick Summary`, `Full Summary`, `Transcript`, `Original Audio reference`) to `Completed`, and moving or marking processed inbox files.

### 1.6 Failure Handling & Resilience
- **Scope:** System error conditions.
- **Criteria:** Graceful recovery and clear logging on corrupted audio files, network disconnects during Drive sync, rate limits, or empty/silent audio recordings.

### 1.7 End-to-End User Acceptance Testing (UAT)
- **Scope:** Full workflow execution.
- **Criteria:** Owner places sample PLAUD audio into Google Drive Inbox; local worker processes file unattended; all 4 required outputs appear accurately formatted in Google Drive Completed.
