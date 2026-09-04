"""
Local Drive Workflow Module for Orbis Meeting AI (WP-007)

V1 OPERATIONAL CONSTRAINT:
ONLY ONE Orbis Processing Host may process a shared workflow root at a time.
No multi-host locking or distributed coordination exists in V1.

Implements local sync-folder workflow support for Google Drive Desktop
without external Google APIs or OAuth dependencies.

Folder Structure:
<Workflow Root>
├── 01_Inbox
├── 02_Processing
├── 03_Completed
└── 99_Error
"""

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union, Tuple, Dict, Any

from orbis_meeting.audio_intake import (
    SUPPORTED_EXTENSIONS,
    AudioJobMetadata,
    AudioIntakeError,
    validate_and_intake_audio,
)
from orbis_meeting.transcription import TranscriptionResult
from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.export_package import ExportPackageResult, export_meeting_package


class DriveWorkflowError(RuntimeError):
    """Raised when local drive workflow initialization or processing fails."""
    pass


@dataclass(frozen=True)
class DriveWorkflowPaths:
    """Paths mapping to the four standard workflow subdirectories under root."""
    root: Path
    inbox: Path
    processing: Path
    completed: Path
    error: Path


def initialize_workflow_root(root: Union[str, Path]) -> DriveWorkflowPaths:
    """
    Initialize and validate a local workflow root directory.

    Ensures the following subdirectories exist:
    - 01_Inbox
    - 02_Processing
    - 03_Completed
    - 99_Error

    Raises DriveWorkflowError if root is empty, does not exist, or is not a directory.
    Does NOT create root itself if missing.
    """
    if not root:
        raise DriveWorkflowError("Workflow root path must be provided.")

    root_path = Path(root).resolve()
    if not root_path.exists():
        raise DriveWorkflowError(f"Workflow root directory does not exist: {root_path}")

    if not root_path.is_dir():
        raise DriveWorkflowError(f"Workflow root path is not a directory: {root_path}")

    inbox = root_path / "01_Inbox"
    processing = root_path / "02_Processing"
    completed = root_path / "03_Completed"
    error = root_path / "99_Error"

    inbox.mkdir(exist_ok=True)
    processing.mkdir(exist_ok=True)
    completed.mkdir(exist_ok=True)
    error.mkdir(exist_ok=True)

    return DriveWorkflowPaths(
        root=root_path,
        inbox=inbox,
        processing=processing,
        completed=completed,
        error=error,
    )


def discover_inbox_audio(paths: DriveWorkflowPaths) -> List[Path]:
    """
    Discover supported audio files (.mp3, .wav, .m4a) in 01_Inbox.

    Filters out directories, empty (0-byte) files, hidden files, and unsupported extensions.
    Returns files ordered deterministically by modification time ascending, then by filename.
    """
    if not paths.inbox.exists() or not paths.inbox.is_dir():
        return []

    discovered: List[Path] = []
    for item in paths.inbox.iterdir():
        if item.is_file() and not item.name.startswith("."):
            ext = item.suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                try:
                    if item.stat().st_size > 0:
                        discovered.append(item)
                except OSError:
                    continue

    # Deterministic sort: mtime ascending, then filename ascending
    discovered.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
    return discovered


def is_file_stable(
    file_path: Union[str, Path],
    check_interval_seconds: float = 0.5,
    sleep_fn: Optional[Any] = None,
) -> bool:
    """
    Verify that an Inbox audio file is fully written and stable (not actively syncing).

    Checks that file size and modification time remain unchanged across two observations.
    If check_interval_seconds is <= 0, checks basic file existence and size > 0.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return False

    try:
        stat1 = path.stat()
        if stat1.st_size == 0:
            return False

        if check_interval_seconds <= 0:
            return True

        if sleep_fn:
            sleep_fn(check_interval_seconds)
        else:
            time.sleep(check_interval_seconds)

        stat2 = path.stat()
        return stat1.st_size == stat2.st_size and stat1.st_mtime == stat2.st_mtime
    except OSError:
        return False


def claim_inbox_audio(
    audio_path: Union[str, Path],
    paths: DriveWorkflowPaths,
    check_interval_seconds: float = 1.0,
    sleep_fn: Optional[Any] = None,
) -> Tuple[Path, Path, AudioJobMetadata]:
    """
    Claim a stable audio file from 01_Inbox into 02_Processing.

    Single Processing Host claim boundary:
    Moves 01_Inbox/<file> -> 02_Processing/<job_dir>/<file>.
    Does NOT alter audio content bytes or transcode audio.

    Returns (job_dir, claimed_audio_path, metadata).
    """
    src_path = Path(audio_path).resolve()
    if not src_path.exists() or not src_path.is_file():
        raise DriveWorkflowError(f"Inbox audio file does not exist: {src_path}")

    if src_path.parent.resolve() != paths.inbox.resolve():
        raise DriveWorkflowError(f"Audio file '{src_path.name}' is not located directly inside 01_Inbox.")

    if not is_file_stable(src_path, check_interval_seconds=check_interval_seconds, sleep_fn=sleep_fn):
        raise DriveWorkflowError(f"Inbox audio file is not stable or still syncing: {src_path.name}")

    try:
        metadata = validate_and_intake_audio(src_path)
    except AudioIntakeError as e:
        raise DriveWorkflowError(f"Intake validation failed for {src_path.name}: {e}") from e

    # Create collision-safe job directory inside 02_Processing
    safe_stem = src_path.stem.replace(" ", "_")
    base_job_dir_name = f"{metadata.job_id[:12]}_{safe_stem}"
    job_dir = paths.processing / base_job_dir_name

    counter = 2
    while job_dir.exists():
        job_dir = paths.processing / f"{base_job_dir_name}_{counter}"
        counter += 1

    job_dir.mkdir(parents=True, exist_ok=False)

    target_audio_path = job_dir / src_path.name
    shutil.move(str(src_path), str(target_audio_path))

    # Return metadata updated with new original_path
    updated_metadata = AudioJobMetadata(
        job_id=metadata.job_id,
        original_path=str(target_audio_path),
        filename=metadata.filename,
        extension=metadata.extension,
        file_size_bytes=metadata.file_size_bytes,
    )

    return job_dir, target_audio_path, updated_metadata


def complete_workflow_job(
    job_dir: Optional[Path],
    target_audio_path: Optional[Path],
    metadata: AudioJobMetadata,
    transcript_result: TranscriptionResult,
    summary_result: MeetingSummaryResult,
    paths: DriveWorkflowPaths,
    template_name: str = "General Meeting",
) -> ExportPackageResult:
    """
    Complete a workflow job by exporting the meeting package to 03_Completed.

    Uses WP-006 export_meeting_package().
    Moves workflow-owned audio into the completed meeting directory.
    Cleans up 02_Processing job folder upon success.
    """
    if not paths.completed.exists():
        raise DriveWorkflowError(f"Completed workflow directory missing: {paths.completed}")

    try:
        # Export WP-006 package into 03_Completed
        export_res = export_meeting_package(
            output_parent=paths.completed,
            metadata=metadata,
            transcript_result=transcript_result,
            summary_result=summary_result,
            template_name=template_name,
        )
    except Exception as e:
        raise DriveWorkflowError(f"Failed to create completed meeting package: {e}") from e

    # Move workflow-owned audio file into completed package directory
    if target_audio_path and target_audio_path.exists():
        dest_audio_path = export_res.package_dir / target_audio_path.name
        if not dest_audio_path.exists():
            try:
                shutil.move(str(target_audio_path), str(dest_audio_path))
            except Exception as e:
                raise DriveWorkflowError(f"Failed to move audio to completed package: {e}") from e

            # Update audio_reference.json with final completed audio path
            audio_ref_file = export_res.audio_reference_path
            if audio_ref_file.exists():
                try:
                    ref_data = json.loads(audio_ref_file.read_text(encoding="utf-8"))
                    ref_data["source_path"] = str(dest_audio_path)
                    audio_ref_file.write_text(
                        json.dumps(ref_data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as e:
                    raise DriveWorkflowError(f"Failed to update audio reference in completed package: {e}") from e

    # Clean up processing job directory ONLY AFTER all finalization steps succeed
    if job_dir and job_dir.exists() and job_dir.is_dir():
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass

    return export_res


def fail_workflow_job(
    paths: DriveWorkflowPaths,
    job_id: str = "unknown",
    audio_filename: str = "unknown",
    audio_path: Optional[Path] = None,
    job_dir: Optional[Path] = None,
    stage: str = "Intake",
    error_message: str = "Unknown error",
) -> Path:
    """
    Handle job failure by moving audio and details into 99_Error without deleting audio.

    Writes error.json with error metadata.
    """
    ts_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base_err_name = f"{ts_str}_{job_id[:8]}"
    error_dir = paths.error / base_err_name

    counter = 2
    while error_dir.exists():
        error_dir = paths.error / f"{base_err_name}_{counter}"
        counter += 1

    error_dir.mkdir(parents=True, exist_ok=False)

    # Move audio file if present
    if audio_path and audio_path.exists():
        dest_audio = error_dir / audio_path.name
        if not dest_audio.exists():
            try:
                shutil.move(str(audio_path), str(dest_audio))
            except Exception:
                pass

    # Clean up job_dir in 02_Processing if leftover
    if job_dir and job_dir.exists() and job_dir != error_dir:
        try:
            for item in job_dir.iterdir():
                if item.is_file() and not (error_dir / item.name).exists():
                    shutil.move(str(item), str(error_dir / item.name))
            shutil.rmtree(job_dir)
        except Exception:
            pass

    # Write error.json
    error_info = {
        "job_id": job_id,
        "audio_filename": audio_filename,
        "stage": stage,
        "error": error_message,
        "failed_at": datetime.now().isoformat(),
    }
    (error_dir / "error.json").write_text(
        json.dumps(error_info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return error_dir
