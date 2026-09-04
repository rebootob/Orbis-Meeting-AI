"""
Local Export Package Module for Orbis Meeting AI (WP-006)

Exports a complete meeting package folder containing:
- Summary.md
- Transcript.txt
- AI_SUMMARY_READY.md
- audio_reference.json

Ensures safe folder naming, overwrite protection, UTF-8 text encoding,
and atomic temporary folder creation with zero third-party dependencies.
"""

import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any

from orbis_meeting.audio_intake import AudioJobMetadata
from orbis_meeting.transcription import TranscriptionResult
from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.manual_handoff import build_manual_ai_payload


class ExportPackageError(RuntimeError):
    """Raised when export package generation or writing fails."""
    pass


@dataclass(frozen=True)
class ExportPackageResult:
    """Dataclass holding paths to the exported meeting package directory and files."""
    package_dir: Path
    summary_path: Path
    transcript_path: Path
    ai_ready_path: Path
    audio_reference_path: Path


def sanitize_folder_component(title: str) -> str:
    """
    Sanitize a meeting title for use as a filesystem folder name.

    Rules:
    - Replace Windows-invalid characters (< > : " / \\ | ? *) with an underscore or space.
    - Replace newlines and tabs with spaces.
    - Collapse multiple whitespace/underscores into a single underscore or space.
    - Strip leading/trailing spaces, dots, and underscores.
    - Limit length to 50 characters.
    - Fall back to "Meeting" if sanitized string is empty.
    """
    if not title or not isinstance(title, str):
        return "Meeting"

    # Replace invalid Windows chars and whitespace control chars
    cleaned = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", title)
    # Collapse multiple spaces or underscores
    cleaned = re.sub(r'[\s_]+', "_", cleaned)
    # Strip leading/trailing dots, spaces, underscores
    cleaned = cleaned.strip(". _")

    if not cleaned:
        return "Meeting"

    # Truncate to max 50 chars safely without trailing underscore/dot
    cleaned = cleaned[:50].strip(". _")
    return cleaned if cleaned else "Meeting"


def build_summary_markdown(summary: MeetingSummaryResult) -> str:
    """
    Build clean UTF-8 Markdown text for Summary.md from a MeetingSummaryResult.
    """
    lines = []
    lines.append(f"# {summary.title}")
    lines.append("")

    lines.append("## Quick Summary")
    lines.append(summary.quick_summary)
    lines.append("")

    lines.append("## Key Topics")
    if summary.key_topics:
        for topic in summary.key_topics:
            lines.append(f"- {topic}")
    else:
        lines.append("No key topics identified.")
    lines.append("")

    lines.append("## Full Summary")
    lines.append(summary.full_summary)
    lines.append("")

    lines.append("## Decisions")
    if summary.decisions:
        for decision in summary.decisions:
            lines.append(f"- {decision}")
    else:
        lines.append("No explicit decisions recorded.")
    lines.append("")

    lines.append("## Action Items")
    if summary.action_items:
        lines.append("| Task | Owner | Due Date |")
        lines.append("|---|---|---|")
        for item in summary.action_items:
            task_clean = item.task.replace("\n", " ").replace("|", r"\|").strip()
            owner_clean = (
                item.owner.replace("\n", " ").replace("|", r"\|").strip()
                if item.owner and item.owner.strip()
                else "-"
            )
            due_clean = (
                item.due_date.replace("\n", " ").replace("|", r"\|").strip()
                if item.due_date and item.due_date.strip()
                else "-"
            )
            lines.append(f"| {task_clean} | {owner_clean} | {due_clean} |")
    else:
        lines.append("No action items recorded.")
    lines.append("")

    lines.append("## Risks / Issues")
    if summary.risks:
        for risk in summary.risks:
            lines.append(f"- {risk}")
    else:
        lines.append("No risks/issues identified.")
    lines.append("")

    lines.append("## Follow-up")
    if summary.follow_up:
        for item in summary.follow_up:
            lines.append(f"- {item}")
    else:
        lines.append("No follow-up items recorded.")

    return "\n".join(lines)


def build_audio_reference(metadata: AudioJobMetadata) -> Dict[str, Any]:
    """
    Build local audio reference dictionary from AudioJobMetadata.
    """
    return {
        "job_id": metadata.job_id,
        "original_filename": metadata.filename,
        "extension": metadata.extension,
        "file_size_bytes": metadata.file_size_bytes,
        "sha256": metadata.job_id,
        "source_path": metadata.original_path,
    }


def export_meeting_package(
    output_parent: Union[str, Path],
    metadata: AudioJobMetadata,
    transcript_result: TranscriptionResult,
    summary_result: MeetingSummaryResult,
    template_name: str = "General Meeting",
    exported_at: Optional[datetime] = None,
) -> ExportPackageResult:
    """
    Export a meeting package into output_parent directory.

    Creates a unique meeting folder and writes:
    - Summary.md
    - Transcript.txt
    - AI_SUMMARY_READY.md
    - audio_reference.json

    Uses atomic write via temporary folder to prevent partial failure.
    Does NOT overwrite existing packages.
    Does NOT copy or move source audio file.
    """
    if not output_parent:
        raise ExportPackageError("Output parent directory path must be provided.")

    parent_path = Path(output_parent).resolve()
    if not parent_path.exists():
        raise ExportPackageError(f"Destination output directory does not exist: {parent_path}")

    if not parent_path.is_dir():
        raise ExportPackageError(f"Destination output path is not a directory: {parent_path}")

    if not metadata or not transcript_result or not summary_result:
        raise ExportPackageError("Export requires valid audio metadata, transcript result, and summary result.")

    ts = exported_at or datetime.now()
    timestamp_str = ts.strftime("%Y-%m-%d_%H%M")
    safe_title = sanitize_folder_component(summary_result.title)

    base_folder_name = f"{timestamp_str}_{safe_title}"
    target_dir = parent_path / base_folder_name

    counter = 2
    while target_dir.exists():
        target_dir = parent_path / f"{base_folder_name}_{counter}"
        counter += 1

    temp_dir_name = f".tmp_export_{uuid.uuid4().hex}"
    temp_dir = parent_path / temp_dir_name

    try:
        temp_dir.mkdir(parents=True, exist_ok=False)

        summary_path = temp_dir / "Summary.md"
        transcript_path = temp_dir / "Transcript.txt"
        ai_ready_path = temp_dir / "AI_SUMMARY_READY.md"
        audio_ref_path = temp_dir / "audio_reference.json"

        # 1. Write Summary.md
        summary_md_content = build_summary_markdown(summary_result)
        summary_path.write_text(summary_md_content, encoding="utf-8")

        # 2. Write Transcript.txt
        transcript_path.write_text(transcript_result.full_text, encoding="utf-8")

        # 3. Write AI_SUMMARY_READY.md
        ai_payload = build_manual_ai_payload(
            transcript_result,
            template_name=template_name,
            language=transcript_result.language,
        )
        ai_ready_path.write_text(ai_payload, encoding="utf-8")

        # 4. Write audio_reference.json
        audio_ref_dict = build_audio_reference(metadata)
        audio_ref_path.write_text(
            json.dumps(audio_ref_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Rename temp_dir to target_dir atomically
        temp_dir.rename(target_dir)

        return ExportPackageResult(
            package_dir=target_dir,
            summary_path=target_dir / "Summary.md",
            transcript_path=target_dir / "Transcript.txt",
            ai_ready_path=target_dir / "AI_SUMMARY_READY.md",
            audio_reference_path=target_dir / "audio_reference.json",
        )
    except Exception as e:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        raise ExportPackageError(f"Failed to export meeting package: {e}") from e
