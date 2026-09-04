"""
Local Audio Intake Foundation for Orbis Meeting AI (WP-001)

Validates local audio files before downstream processing.
Treats input files as strictly read-only and generates deterministic job metadata.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
from typing import Union, Dict, Any

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a"}


class AudioIntakeError(ValueError):
    """Raised when an audio file fails intake validation."""
    pass


@dataclass(frozen=True)
class AudioJobMetadata:
    """Minimal metadata returned for validated audio files."""
    job_id: str
    original_path: str
    filename: str
    extension: str
    file_size_bytes: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_deterministic_job_id(file_path: Path) -> str:
    """Calculate a deterministic job ID using SHA-256 content hashing."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_and_intake_audio(file_path: Union[str, Path]) -> AudioJobMetadata:
    """
    Validate a local audio file and return job metadata.

    Validations:
    1. Input path is supplied (non-empty).
    2. File exists.
    3. Path points to a regular file (not a directory).
    4. Extension is supported (.mp3, .wav, .m4a - case-insensitive).
    5. File is not empty (file_size_bytes > 0).

    The original audio file is treated as strictly read-only.
    """
    if file_path is None or (isinstance(file_path, str) and not file_path.strip()):
        raise AudioIntakeError("Audio file path must be supplied.")

    path = Path(file_path).resolve()

    if not path.exists():
        raise AudioIntakeError(f"Audio file does not exist: {path}")

    if not path.is_file():
        raise AudioIntakeError(f"Path is not a regular file: {path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise AudioIntakeError(
            f"Unsupported audio file extension '{path.suffix}'. "
            f"Supported extensions: {sorted(list(SUPPORTED_EXTENSIONS))}"
        )

    file_size = path.stat().st_size
    if file_size == 0:
        raise AudioIntakeError(f"Audio file is empty (0 bytes): {path}")

    job_id = calculate_deterministic_job_id(path)

    return AudioJobMetadata(
        job_id=job_id,
        original_path=str(path),
        filename=path.name,
        extension=ext,
        file_size_bytes=file_size,
    )
