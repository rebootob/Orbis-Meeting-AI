"""
Control Center & Job History Module for Orbis Meeting AI (WP-011)

Provides filesystem-based read-only snapshot generation, bilingual Thai/English UI text,
safe native OS folder opening, and status formatting.

Strict constraints:
- Pure read-only module; does not modify workflow files or database.
- Uses standard library only (dataclasses, pathlib, json, os, typing, datetime).
- Preserves internal runner states ("TRANSCRIBING", "COMPLETING", etc.) unchanged in logic,
  translating them strictly for display purposes.
"""

import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

from orbis_meeting.drive_workflow import DriveWorkflowPaths, discover_inbox_audio
from orbis_meeting.job_runner import RunnerState


@dataclass(frozen=True)
class RecentCompletedItem:
    """Read-only snapshot item for a completed meeting package in 03_Completed."""
    title: str
    path: Path
    created_at: str
    summary_present: bool
    transcript_present: bool
    audio_json_present: bool


@dataclass(frozen=True)
class RecentErrorItem:
    """Read-only snapshot item for an error directory in 99_Error."""
    directory_name: str
    path: Path
    failed_at: str
    failed_stage: str
    error_message: str
    raw_json_present: bool
    source_file: str


@dataclass(frozen=True)
class ControlCenterSnapshot:
    """Comprehensive read-only status and history snapshot of the workflow root."""
    inbox_count: int
    processing_count: int
    completed_count: int
    error_count: int
    runner_state: str
    runner_is_running: bool
    summary_engine_enabled: bool
    summary_engine_provider: str
    current_job_name: Optional[str]
    recent_completed: List[RecentCompletedItem]
    recent_errors: List[RecentErrorItem]
    whisper_engine_status: str = "large-v3 | CPU | default"



UI_TEXT: Dict[str, Dict[str, str]] = {
    "th": {
        "title": "Orbis Meeting AI",
        "tab_workflow": "กระบวนการทำงานหลัก (Workflow)",
        "tab_control_center": "ศูนย์ควบคุมและประวัติงาน (Control Center)",
        "language_label": "ภาษา / Language:",
        "workflow_section": "โฟลเดอร์ Google Drive Sync (Host ดำเนินการเดี่ยว)",
        "select_root_btn": "เลือกโฟลเดอร์หลัก...",
        "load_inbox_btn": "โหลดไฟล์เสียงถัดไป",
        "start_runner_btn": "เริ่มระบบอัตโนมัติ",
        "stop_runner_btn": "หยุดระบบอัตโนมัติ",
        "runner_status": "สถานะ Runner:",
        "current_job": "งานปัจจุบัน:",
        "stat_inbox": "ไฟล์รอประมวลผล (Inbox)",
        "stat_processing": "กำลังประมวลผล (Processing)",
        "stat_completed": "เสร็จสมบูรณ์ (Completed)",
        "stat_error": "เกิดข้อผิดพลาด (Error)",
        "summary_engine_status": "เครื่องมือสรุปผล AI:",
        "whisper_engine_status": "ระบบถอดเสียง:",
        "recent_completed_title": "รายการประชุมเสร็จสมบูรณ์ล่าสุด (10 รายการแรก)",
        "recent_errors_title": "รายการข้อผิดพลาดล่าสุด (10 รายการแรก)",
        "col_title": "ชื่อหัวข้อประชุม / โฟลเดอร์",
        "col_date": "วันที่ / เวลา",
        "col_files": "ไฟล์ในแพ็กเกจ",
        "col_error_dir": "โฟลเดอร์ข้อผิดพลาด",
        "col_stage": "ขั้นตอนที่ล้มเหลว",
        "col_message": "รายละเอียดข้อผิดพลาด",
        "col_source": "ไฟล์ต้นทาง",
        "open_inbox": "เปิดโฟลเดอร์ Inbox",
        "open_completed": "เปิดโฟลเดอร์ Completed",
        "open_error": "เปิดโฟลเดอร์ Error",
        "open_root": "เปิดโฟลเดอร์ Workflow Root",
        "refresh_btn": "รีเฟรชข้อมูล (Refresh)",
        "retry_completion_btn": "ลองย้ายไฟล์เสร็จสิ้นอีกครั้ง (Retry Completion)",
        "retry_disabled_tooltip": "เปิดใช้งานเฉพาะเมื่อสถานะ Runner เป็น COMPLETION_ERROR",
        # Internal State strings translated strictly for UI display:
        "state_STOPPED": "หยุดทำงาน (Stopped)",
        "state_STOPPING": "กำลังหยุดทำงาน (Stopping)",
        "state_IDLE": "รอรับงาน (Idle)",
        "state_SCANNING": "กำลังตรวจหาไฟล์ (Scanning)",
        "state_CLAIMING": "กำลังรับไฟล์งาน (Claiming)",
        "state_TRANSCRIBING": "กำลังถอดความเสียง (Transcribing)",
        "state_CLEANING": "กำลังปรับแต่งข้อความ (Cleaning)",
        "state_WAITING_FOR_SUMMARY": "รอสร้างบทสรุป (Waiting for Summary)",
        "state_SUMMARIZING": "กำลังสร้างบทสรุป (Summarizing)",
        "state_SUMMARY_READY": "บทสรุปพร้อมใช้งาน (Summary Ready)",
        "state_SUMMARY_ERROR": "ข้อผิดพลาดบทสรุป (Summary Error)",
        "state_COMPLETING": "กำลังย้ายเข้าโฟลเดอร์เสร็จสิ้น (Completing)",
        "state_COMPLETION_ERROR": "ข้อผิดพลาดขั้นตอนเสร็จสิ้น (Completion Error)",
        "state_ERROR": "เกิดข้อผิดพลาด (Error)",
    },
    "en": {
        "title": "Orbis Meeting AI",
        "tab_workflow": "Main Workflow",
        "tab_control_center": "Control Center & Job History",
        "language_label": "Language / ภาษา:",
        "workflow_section": "Google Drive Sync Folder (Single Processing Host)",
        "select_root_btn": "Select Workflow Root...",
        "load_inbox_btn": "Load Next Inbox Audio",
        "start_runner_btn": "Start Auto Runner",
        "stop_runner_btn": "Stop Auto Runner",
        "runner_status": "Runner Status:",
        "current_job": "Current Job:",
        "stat_inbox": "Inbox Audio Files",
        "stat_processing": "Processing Jobs",
        "stat_completed": "Completed Packages",
        "stat_error": "Error Packages",
        "summary_engine_status": "Summary Engine:",
        "whisper_engine_status": "Whisper Engine:",
        "recent_completed_title": "Recent Completed Meetings (Top 10)",
        "recent_errors_title": "Recent Job Failures (Top 10)",
        "col_title": "Meeting Title / Folder",
        "col_date": "Date / Time",
        "col_files": "Package Files",
        "col_error_dir": "Error Folder",
        "col_stage": "Failed Stage",
        "col_message": "Error Message",
        "col_source": "Source File",
        "open_inbox": "Open Inbox Folder",
        "open_completed": "Open Completed Folder",
        "open_error": "Open Error Folder",
        "open_root": "Open Workflow Root",
        "refresh_btn": "Refresh",
        "retry_completion_btn": "Retry Completion",
        "retry_disabled_tooltip": "Enabled only when Runner state is COMPLETION_ERROR",
        # Internal State strings translated strictly for UI display:
        "state_STOPPED": "Stopped",
        "state_STOPPING": "Stopping",
        "state_IDLE": "Idle",
        "state_SCANNING": "Scanning",
        "state_CLAIMING": "Claiming Job",
        "state_TRANSCRIBING": "Transcribing Audio",
        "state_CLEANING": "Cleaning Text",
        "state_WAITING_FOR_SUMMARY": "Waiting for Summary",
        "state_SUMMARIZING": "Summarizing",
        "state_SUMMARY_READY": "Summary Ready",
        "state_SUMMARY_ERROR": "Summary Error",
        "state_COMPLETING": "Completing Package",
        "state_COMPLETION_ERROR": "Completion Error",
        "state_ERROR": "Error",
    },
}


def get_text(lang: str, key: str, **kwargs) -> str:
    """Retrieve UI string by language code ('th' or 'en') with safe fallbacks."""
    lang_dict = UI_TEXT.get(lang, UI_TEXT["th"])
    text = lang_dict.get(key, UI_TEXT["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def get_state_display(lang: str, state: Union[str, Enum]) -> str:
    """
    Translate internal state enum or string (e.g. 'TRANSCRIBING') to Thai/English display text.
    Does NOT modify or return a different underlying state string.
    """
    if hasattr(state, "value"):
        state_str = str(state.value)
    else:
        state_str = str(state)

    key = f"state_{state_str}"
    lang_dict = UI_TEXT.get(lang, UI_TEXT["th"])
    return lang_dict.get(key, state_str)


def open_folder_in_os(folder_path: Union[str, Path, None]) -> bool:
    """
    Safely open a directory in native OS file manager (Windows Explorer, macOS Finder, etc.).

    Returns True if successfully launched, False if folder is missing/invalid or launch fails.
    Never raises an exception.
    """
    if not folder_path:
        return False

    try:
        path = Path(folder_path).resolve()
        if not path.exists() or not path.is_dir():
            return False

        if hasattr(os, "startfile"):
            os.startfile(str(path))
            return True
        else:
            sys_name = platform.system()
            if sys_name == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True
    except Exception:
        return False


def _extract_title_from_summary(summary_path: Path, default_name: str) -> str:
    """Read MEETING TITLE from Summary.md safely."""
    try:
        if not summary_path.exists() or not summary_path.is_file():
            return default_name

        content = summary_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("MEETING TITLE:"):
                extracted = line_str.replace("MEETING TITLE:", "").strip()
                if extracted:
                    return extracted
            elif line_str.startswith("# "):
                extracted = line_str[2:].strip()
                if extracted:
                    return extracted
        return default_name
    except Exception:
        return default_name


def get_control_center_snapshot(
    paths: Optional[DriveWorkflowPaths] = None,
    controller: Optional[Any] = None,
    runner: Optional[Any] = None,
) -> ControlCenterSnapshot:
    """
    Construct a pure read-only snapshot of local workflow state, recent packages, and runner info.

    All directory and file operations use exception handling so missing, empty, or malformed
    files/directories will fall back safely without raising exceptions.
    """
    # 1. Resolve workflow paths and job runner from arguments or controller
    resolved_paths: Optional[DriveWorkflowPaths] = paths
    if resolved_paths is None and controller is not None:
        resolved_paths = getattr(controller, "workflow_paths", None)

    resolved_runner: Optional[Any] = runner
    if resolved_runner is None and controller is not None:
        resolved_runner = getattr(controller, "auto_runner", None)

    # 2. Extract Runner State
    if resolved_runner is not None:
        raw_state = getattr(resolved_runner, "state", RunnerState.STOPPED)
        runner_state = raw_state.value if hasattr(raw_state, "value") else str(raw_state)
        runner_is_running = bool(getattr(resolved_runner, "is_running", False))
        current_job_name = getattr(resolved_runner, "current_job", None)
    else:
        runner_state = RunnerState.STOPPED.value
        runner_is_running = False
        current_job_name = None

    # 3. Extract Summary Engine Info
    summary_engine_enabled = False
    summary_engine_provider = "Disabled"
    if controller is not None:
        if getattr(controller, "auto_summary_service", None) is not None:
            summary_engine_enabled = True
            summary_engine_provider = getattr(
                controller, "summary_engine_status", "Local Automatic Ready"
            )
        elif getattr(controller, "summary_engine_status", None):
            summary_engine_provider = controller.summary_engine_status

    # Extract Whisper Engine Status
    from orbis_meeting.transcription import format_whisper_runtime_status
    if controller is not None and isinstance(getattr(controller, "whisper_runtime_status", None), str):
        whisper_engine_status = controller.whisper_runtime_status
    elif controller is not None and getattr(controller, "transcription_service", None) is not None:
        whisper_engine_status = format_whisper_runtime_status(controller.transcription_service)
    else:
        whisper_engine_status = format_whisper_runtime_status()

    # 4. Handle unconfigured/missing workflow paths
    if not resolved_paths or not resolved_paths.root or not resolved_paths.root.exists():
        return ControlCenterSnapshot(
            inbox_count=0,
            processing_count=0,
            completed_count=0,
            error_count=0,
            runner_state=runner_state,
            runner_is_running=runner_is_running,
            summary_engine_enabled=summary_engine_enabled,
            summary_engine_provider=summary_engine_provider,
            current_job_name=current_job_name,
            recent_completed=[],
            recent_errors=[],
            whisper_engine_status=whisper_engine_status,
        )

    # 5. Scan 01_Inbox
    inbox_count = 0
    if resolved_paths.inbox and resolved_paths.inbox.exists():
        try:
            inbox_files = discover_inbox_audio(resolved_paths)
            inbox_count = len(inbox_files)
        except Exception:
            inbox_count = 0

    # 6. Scan 02_Processing
    processing_count = 0
    if resolved_paths.processing and resolved_paths.processing.exists():
        try:
            processing_count = sum(
                1 for p in resolved_paths.processing.iterdir() if p.is_dir()
            )
        except Exception:
            processing_count = 0

    # 7. Scan 03_Completed
    completed_dirs: List[Path] = []
    if resolved_paths.completed and resolved_paths.completed.exists():
        try:
            completed_dirs = [p for p in resolved_paths.completed.iterdir() if p.is_dir()]
        except Exception:
            completed_dirs = []

    completed_count = len(completed_dirs)

    # Sort completed packages by mtime descending (newest first)
    def _safe_mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except Exception:
            return 0.0

    completed_dirs.sort(key=_safe_mtime, reverse=True)
    recent_completed_dirs = completed_dirs[:10]

    recent_completed_items: List[RecentCompletedItem] = []
    for pkg in recent_completed_dirs:
        mtime_val = _safe_mtime(pkg)
        created_at_str = (
            datetime.fromtimestamp(mtime_val).strftime("%Y-%m-%d %H:%M:%S")
            if mtime_val > 0
            else "N/A"
        )
        summary_file = pkg / "Summary.md"
        transcript_file = pkg / "Transcript.txt"
        audio_json_file = pkg / "audio_reference.json"

        title = _extract_title_from_summary(summary_file, pkg.name)

        recent_completed_items.append(
            RecentCompletedItem(
                title=title,
                path=pkg,
                created_at=created_at_str,
                summary_present=summary_file.exists(),
                transcript_present=transcript_file.exists(),
                audio_json_present=audio_json_file.exists(),
            )
        )

    # 8. Scan 99_Error
    error_dirs: List[Path] = []
    if resolved_paths.error and resolved_paths.error.exists():
        try:
            error_dirs = [p for p in resolved_paths.error.iterdir() if p.is_dir()]
        except Exception:
            error_dirs = []

    error_count = len(error_dirs)

    error_dirs.sort(key=_safe_mtime, reverse=True)
    recent_error_dirs = error_dirs[:10]

    recent_error_items: List[RecentErrorItem] = []
    for err_dir in recent_error_dirs:
        mtime_val = _safe_mtime(err_dir)
        formatted_mtime = (
            datetime.fromtimestamp(mtime_val).strftime("%Y-%m-%d %H:%M:%S")
            if mtime_val > 0
            else "N/A"
        )

        error_json_file = err_dir / "error.json"
        raw_json_present = error_json_file.exists() and error_json_file.is_file()

        failed_at = formatted_mtime
        failed_stage = "UNKNOWN"
        error_message = "Error metadata unavailable"
        source_file = "N/A"

        if raw_json_present:
            try:
                data = json.loads(error_json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    failed_at = data.get("failed_at", formatted_mtime)
                    failed_stage = data.get("stage", "UNKNOWN")
                    error_message = data.get("error", "Error metadata unavailable")
                    source_file = data.get("audio_filename", "N/A")
            except Exception:
                # If error.json is corrupt/malformed, fall back safely
                raw_json_present = False

        recent_error_items.append(
            RecentErrorItem(
                directory_name=err_dir.name,
                path=err_dir,
                failed_at=failed_at,
                failed_stage=failed_stage,
                error_message=error_message,
                raw_json_present=raw_json_present,
                source_file=source_file,
            )
        )

    return ControlCenterSnapshot(
        inbox_count=inbox_count,
        processing_count=processing_count,
        completed_count=completed_count,
        error_count=error_count,
        runner_state=runner_state,
        runner_is_running=runner_is_running,
        summary_engine_enabled=summary_engine_enabled,
        summary_engine_provider=summary_engine_provider,
        current_job_name=current_job_name,
        recent_completed=recent_completed_items,
        recent_errors=recent_error_items,
        whisper_engine_status=whisper_engine_status,
    )
