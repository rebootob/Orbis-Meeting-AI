# 03_ARCHITECTURE.md — System Architecture

## 1. High-Level V1 Architecture Flow

```
+------------------+
|   PLAUD Audio    |
+--------+---------+
         |
         v
+------------------+
| Google Drive     |
| Inbox            |
+--------+---------+
         |
         v
+------------------+
| Local Worker     |
+--------+---------+
         |
         v
+------------------+
| Whisper Local    |
| Transcription    |
+--------+---------+
         |
         v
+------------------+
| Thai Cleanup &   |
| Company Dict     |
+--------+---------+
         |
         v
+------------------+
| Meeting Summary  |
| Generation       |
+--------+---------+
         |
         v
+------------------+
| Google Drive     |
| Completed        |
+------------------+
```

---

## 2. V1 Output Artifacts
Every processed meeting audio generates the following 4 output items placed in Google Drive Completed:
1. **Quick Summary:** Executive overview, key takeaways, action items.
2. **Full Summary:** Comprehensive meeting notes and detailed discussion points.
3. **Transcript:** Cleaned Thai transcript text.
4. **Original Audio:** Reference audio file moved or linked.

---

## 3. Future Notification Adapter Boundary (Conceptual Only)

```
+------------------+
| Completed Output |
+--------+---------+
         |
         v (Future boundary after V1 closure)
+------------------------------------+
| Future Notification Adapter        |
|  ├── Telegram                      |
|  └── LINE                          |
+------------------------------------+
```

> **IMPORTANT ARCHITECTURAL DIRECTIVE:**
> The Notification Adapter boundary above is purely conceptual for future planning. **DO NOT** design, code, stub, or implement notification interfaces, classes, configurations, or dependencies during V1 or WP-000.
