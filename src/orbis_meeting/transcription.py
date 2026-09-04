"""
Local Whisper Transcription Foundation for Orbis Meeting AI (WP-002)

Provides local speech-to-text transcription for validated audio files using faster-whisper.
Returns structured raw transcripts with timestamped segments without modifying original audio.
"""

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

from orbis_meeting.audio_intake import AudioJobMetadata, validate_and_intake_audio


class TranscriptionError(RuntimeError):
    """Raised when transcription fails during model loading or execution."""
    pass


class WhisperRuntimeConfigError(ValueError):
    """Raised when Whisper runtime configuration environment variables are invalid."""
    pass


@dataclass(frozen=True)
class WhisperRuntimeConfig:
    """Runtime configuration for local Whisper transcription engine."""
    model_name: str = "large-v3"
    device: str = "cpu"
    compute_type: str = "default"


@dataclass(frozen=True)
class TranscriptionSegment:
    """Individual timestamped text segment from transcription."""
    start: float
    end: float
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptionResult:
    """Structured transcription result containing full text and segments."""
    job_id: str
    language: str
    full_text: str
    segments: List[TranscriptionSegment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "language": self.language,
            "full_text": self.full_text,
            "segments": [seg.to_dict() for seg in self.segments],
        }


class WhisperTranscriptionService:
    """
    Local transcription service wrapper around faster-whisper.
    Supports model configuration and dependency injection for unit testing.
    """

    def __init__(
        self,
        model_name: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "default",
        model_backend: Optional[Any] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = model_backend

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self._model
        except Exception as e:
            raise TranscriptionError(
                f"Failed to load Whisper model '{self.model_name}' on device '{self.device}': {e}"
            ) from e

    def transcribe(
        self,
        audio_input: Union[AudioJobMetadata, str, Path],
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe a validated audio file.

        :param audio_input: AudioJobMetadata instance, or file path (validated via AudioIntake).
        :param language: Language code ("th", "en", etc.), or None for automatic detection.
        :return: TranscriptionResult dataclass.
        """
        if isinstance(audio_input, AudioJobMetadata):
            job_metadata = audio_input
            audio_path = Path(job_metadata.original_path)
            if not audio_path.exists():
                raise TranscriptionError(f"Audio file specified in job_id '{job_metadata.job_id}' does not exist: {audio_path}")
        else:
            # Validate input using WP-001 intake layer if a raw path is passed
            job_metadata = validate_and_intake_audio(audio_input)
            audio_path = Path(job_metadata.original_path)

        model = self._get_model()

        try:
            kwargs = {}
            if language is not None:
                kwargs["language"] = language

            segments_iter, info = model.transcribe(str(audio_path), **kwargs)
        except Exception as e:
            raise TranscriptionError(
                f"Transcription execution failed for job_id '{job_metadata.job_id}': {e}"
            ) from e

        if info is None:
            raise TranscriptionError(f"Transcription returned invalid metadata info for job_id '{job_metadata.job_id}'.")

        parsed_segments: List[TranscriptionSegment] = []
        try:
            for s in segments_iter:
                text = getattr(s, "text", "").strip() if getattr(s, "text", None) else ""
                start = float(getattr(s, "start", 0.0))
                end = float(getattr(s, "end", 0.0))

                if start < 0 or end < start:
                    raise TranscriptionError(
                        f"Invalid timestamp segment in job_id '{job_metadata.job_id}': start={start}, end={end}"
                    )

                if text:
                    parsed_segments.append(TranscriptionSegment(start=start, end=end, text=text))
        except TranscriptionError:
            raise
        except Exception as e:
            raise TranscriptionError(
                f"Failed reading transcription segments for job_id '{job_metadata.job_id}': {e}"
            ) from e

        full_text = " ".join(seg.text for seg in parsed_segments).strip()
        if not full_text:
            raise TranscriptionError(f"Transcription resulted in empty text for job_id '{job_metadata.job_id}'.")

        detected_language = getattr(info, "language", None) or language or "unknown"

        return TranscriptionResult(
            job_id=job_metadata.job_id,
            language=detected_language,
            full_text=full_text,
            segments=parsed_segments,
        )


def load_whisper_runtime_config_from_environment() -> WhisperRuntimeConfig:
    """
    Load and validate Whisper runtime configuration from environment variables.

    Environment variables:
    - ORBIS_WHISPER_MODEL (default: "large-v3")
    - ORBIS_WHISPER_DEVICE (default: "cpu", supported: "cpu", "cuda")
    - ORBIS_WHISPER_COMPUTE_TYPE (default: "default")

    Raises WhisperRuntimeConfigError if explicitly provided env variables are invalid or empty.
    """
    raw_model = os.environ.get("ORBIS_WHISPER_MODEL")
    if raw_model is not None:
        model_name = raw_model.strip()
        if not model_name:
            raise WhisperRuntimeConfigError("ORBIS_WHISPER_MODEL environment variable cannot be empty.")
    else:
        model_name = "large-v3"

    raw_device = os.environ.get("ORBIS_WHISPER_DEVICE")
    if raw_device is not None:
        device_str = raw_device.strip().lower()
        if not device_str:
            raise WhisperRuntimeConfigError("ORBIS_WHISPER_DEVICE environment variable cannot be empty.")
        if device_str not in {"cpu", "cuda"}:
            raise WhisperRuntimeConfigError(
                f"Invalid ORBIS_WHISPER_DEVICE '{raw_device}'. Supported devices are 'cpu' and 'cuda'."
            )
        device = device_str
    else:
        device = "cpu"

    raw_compute = os.environ.get("ORBIS_WHISPER_COMPUTE_TYPE")
    if raw_compute is not None:
        compute_type = raw_compute.strip()
        if not compute_type:
            raise WhisperRuntimeConfigError("ORBIS_WHISPER_COMPUTE_TYPE environment variable cannot be empty.")
    else:
        compute_type = "default"

    return WhisperRuntimeConfig(
        model_name=model_name,
        device=device,
        compute_type=compute_type,
    )


def build_transcription_service_from_environment(
    model_backend: Optional[Any] = None,
) -> WhisperTranscriptionService:
    """
    Build a WhisperTranscriptionService using environment variable runtime configuration.
    Preserves dependency injection via model_backend for unit testing without downloading models.
    """
    config = load_whisper_runtime_config_from_environment()
    return WhisperTranscriptionService(
        model_name=config.model_name,
        device=config.device,
        compute_type=config.compute_type,
        model_backend=model_backend,
    )


def format_whisper_runtime_status(
    config_or_service: Optional[Union[WhisperRuntimeConfig, WhisperTranscriptionService]] = None,
) -> str:
    """
    Format a bounded status string representation of the Whisper runtime configuration.
    Example: 'large-v3 | CPU | default' or 'medium | CUDA | int8_float16'
    """
    if config_or_service is None:
        try:
            config = load_whisper_runtime_config_from_environment()
            model_name = config.model_name
            device = config.device.upper()
            compute_type = config.compute_type
        except Exception:
            model_name = "large-v3"
            device = "CPU"
            compute_type = "default"
    elif isinstance(config_or_service, WhisperRuntimeConfig):
        model_name = config_or_service.model_name
        device = config_or_service.device.upper()
        compute_type = config_or_service.compute_type
    elif isinstance(config_or_service, WhisperTranscriptionService):
        model_name = config_or_service.model_name
        device = str(config_or_service.device).upper()
        compute_type = config_or_service.compute_type
    else:
        raw_model = getattr(config_or_service, "model_name", "large-v3")
        raw_device = getattr(config_or_service, "device", "cpu")
        raw_compute = getattr(config_or_service, "compute_type", "default")

        model_name = raw_model if isinstance(raw_model, str) and raw_model else "large-v3"
        device = (raw_device if isinstance(raw_device, str) and raw_device else "cpu").upper()
        compute_type = raw_compute if isinstance(raw_compute, str) and raw_compute else "default"

    return f"{model_name} | {device} | {compute_type}"

