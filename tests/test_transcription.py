"""
Unit tests for WP-002 Local Whisper Transcription Foundation
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.audio_intake import validate_and_intake_audio, AudioJobMetadata
from orbis_meeting.transcription import (
    TranscriptionError,
    TranscriptionResult,
    TranscriptionSegment,
    WhisperTranscriptionService,
    ConfigErrorTranscriptionService,
    WhisperRuntimeConfig,
    WhisperRuntimeConfigError,
    load_whisper_runtime_config_from_environment,
    build_transcription_service_from_environment,
    format_whisper_runtime_status,
)


class MockSegment:
    def __init__(self, start: float, end: float, text: str):
        self.start = start
        self.end = end
        self.text = text


class MockInfo:
    def __init__(self, language: str):
        self.language = language


class MockWhisperModel:
    def __init__(self, segments=None, language="th", raise_on_transcribe=False, return_invalid_info=False):
        self.segments = segments if segments is not None else [
            MockSegment(0.0, 4.5, "สวัสดีครับ"),
            MockSegment(4.5, 9.0, "การประชุมวันนี้"),
        ]
        self.language = language
        self.raise_on_transcribe = raise_on_transcribe
        self.return_invalid_info = return_invalid_info

    def transcribe(self, audio_path: str, **kwargs):
        if self.raise_on_transcribe:
            raise RuntimeError("Simulated engine transcription failure")
        if self.return_invalid_info:
            return iter(self.segments), None
        lang = kwargs.get("language") or self.language
        return iter(self.segments), MockInfo(language=lang)


class TestTranscription(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.sample_audio = self.test_dir / "sample_meeting.wav"
        self.sample_audio.write_bytes(b"dummy wav audio content 12345")
        self.job_metadata = validate_and_intake_audio(self.sample_audio)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ac04_ac05_ac06_service_configuration(self):
        service = WhisperTranscriptionService(
            model_name="medium",
            device="cuda",
            compute_type="float16",
            model_backend=MockWhisperModel(),
        )
        self.assertEqual(service.model_name, "medium")
        self.assertEqual(service.device, "cuda")
        self.assertEqual(service.compute_type, "float16")

    def test_thai_result_mapping(self):
        mock_model = MockWhisperModel(
            segments=[
                MockSegment(0.0, 3.0, "สวัสดีครับท่านประธาน"),
                MockSegment(3.1, 7.5, "ขอเปิดการประชุม"),
            ],
            language="th",
        )
        service = WhisperTranscriptionService(model_backend=mock_model)
        result = service.transcribe(self.job_metadata, language="th")

        self.assertIsInstance(result, TranscriptionResult)
        self.assertEqual(result.language, "th")
        self.assertEqual(result.full_text, "สวัสดีครับท่านประธาน ขอเปิดการประชุม")
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].start, 0.0)
        self.assertEqual(result.segments[0].end, 3.0)
        self.assertEqual(result.segments[0].text, "สวัสดีครับท่านประธาน")

    def test_english_result_mapping(self):
        mock_model = MockWhisperModel(
            segments=[
                MockSegment(0.0, 2.5, "Welcome to the meeting."),
                MockSegment(2.5, 6.0, "Let's review the agenda."),
            ],
            language="en",
        )
        service = WhisperTranscriptionService(model_backend=mock_model)
        result = service.transcribe(self.job_metadata, language="en")

        self.assertEqual(result.language, "en")
        self.assertEqual(result.full_text, "Welcome to the meeting. Let's review the agenda.")
        self.assertEqual(len(result.segments), 2)

    def test_auto_language_detection(self):
        mock_model = MockWhisperModel(
            segments=[MockSegment(0.0, 5.0, "Automatic detection test")],
            language="en",
        )
        service = WhisperTranscriptionService(model_backend=mock_model)
        # Passing language=None triggers automatic language detection
        result = service.transcribe(self.job_metadata, language=None)

        self.assertEqual(result.language, "en")
        self.assertEqual(result.full_text, "Automatic detection test")

    def test_job_id_propagation(self):
        mock_model = MockWhisperModel()
        service = WhisperTranscriptionService(model_backend=mock_model)
        result = service.transcribe(self.job_metadata)

        self.assertEqual(result.job_id, self.job_metadata.job_id)

    def test_raw_path_input(self):
        mock_model = MockWhisperModel()
        service = WhisperTranscriptionService(model_backend=mock_model)
        result = service.transcribe(self.sample_audio)

        self.assertEqual(result.job_id, self.job_metadata.job_id)

    def test_original_audio_unchanged(self):
        content = self.sample_audio.read_bytes()
        initial_hash = hashlib.sha256(content).hexdigest()
        initial_stat = self.sample_audio.stat()

        mock_model = MockWhisperModel()
        service = WhisperTranscriptionService(model_backend=mock_model)
        service.transcribe(self.job_metadata)

        post_content = self.sample_audio.read_bytes()
        post_hash = hashlib.sha256(post_content).hexdigest()
        post_stat = self.sample_audio.stat()

        self.assertEqual(post_content, content)
        self.assertEqual(post_hash, initial_hash)
        self.assertEqual(post_stat.st_size, initial_stat.st_size)

    def test_model_load_failure(self):
        class FailingModelFactoryService(WhisperTranscriptionService):
            def _get_model(self):
                raise TranscriptionError("Failed to load Whisper model 'large-v3': Model file corrupt")

        service = FailingModelFactoryService()
        with self.assertRaises(TranscriptionError) as ctx:
            service.transcribe(self.job_metadata)
        self.assertIn("Failed to load Whisper model", str(ctx.exception))

    def test_transcription_execution_failure(self):
        failing_model = MockWhisperModel(raise_on_transcribe=True)
        service = WhisperTranscriptionService(model_backend=failing_model)
        with self.assertRaises(TranscriptionError) as ctx:
            service.transcribe(self.job_metadata)
        self.assertIn("Transcription execution failed", str(ctx.exception))

    def test_empty_result_rejection(self):
        empty_model = MockWhisperModel(segments=[])
        service = WhisperTranscriptionService(model_backend=empty_model)
        with self.assertRaises(TranscriptionError) as ctx:
            service.transcribe(self.job_metadata)
        self.assertIn("resulted in empty text", str(ctx.exception))

    def test_invalid_segment_timestamp_rejection(self):
        invalid_model = MockWhisperModel(segments=[MockSegment(10.0, 5.0, "Invalid timestamps")])
        service = WhisperTranscriptionService(model_backend=invalid_model)
        with self.assertRaises(TranscriptionError) as ctx:
            service.transcribe(self.job_metadata)
        self.assertIn("Invalid timestamp segment", str(ctx.exception))

    def test_invalid_info_rejection(self):
        invalid_info_model = MockWhisperModel(return_invalid_info=True)
        service = WhisperTranscriptionService(model_backend=invalid_info_model)
        with self.assertRaises(TranscriptionError) as ctx:
            service.transcribe(self.job_metadata)
        self.assertIn("invalid metadata info", str(ctx.exception))

    def test_missing_audio_file_for_job_rejection(self):
        missing_job = AudioJobMetadata(
            job_id="dummy_job_id",
            original_path=str(self.test_dir / "non_existent.mp3"),
            filename="non_existent.mp3",
            extension=".mp3",
            file_size_bytes=100,
        )
        service = WhisperTranscriptionService(model_backend=MockWhisperModel())
        with self.assertRaises(TranscriptionError) as ctx:
            service.transcribe(missing_job)
        self.assertIn("does not exist", str(ctx.exception))


class TestWhisperRuntimeConfig(unittest.TestCase):

    def test_default_environment_variables(self):
        """Test default Whisper config when environment variables are unset."""
        env_dict = os.environ.copy()
        env_dict.pop("ORBIS_WHISPER_MODEL", None)
        env_dict.pop("ORBIS_WHISPER_DEVICE", None)
        env_dict.pop("ORBIS_WHISPER_COMPUTE_TYPE", None)
        with patch.dict(os.environ, env_dict, clear=True):
            config = load_whisper_runtime_config_from_environment()
            self.assertEqual(config.model_name, "large-v3")
            self.assertEqual(config.device, "cpu")
            self.assertEqual(config.compute_type, "default")
            self.assertEqual(format_whisper_runtime_status(config), "large-v3 | CPU | default")

    def test_custom_environment_variables_and_whitespace_trimming(self):
        """Test loading custom environment variables with whitespace trimming."""
        custom_env = {
            "ORBIS_WHISPER_MODEL": "  medium  ",
            "ORBIS_WHISPER_DEVICE": " CUDA ",
            "ORBIS_WHISPER_COMPUTE_TYPE": " float16 ",
        }
        with patch.dict(os.environ, custom_env):
            config = load_whisper_runtime_config_from_environment()
            self.assertEqual(config.model_name, "medium")
            self.assertEqual(config.device, "cuda")
            self.assertEqual(config.compute_type, "float16")
            self.assertEqual(format_whisper_runtime_status(config), "medium | CUDA | float16")

    def test_invalid_device_raises_config_error(self):
        """Test rejection of unsupported or invalid device string."""
        with patch.dict(os.environ, {"ORBIS_WHISPER_DEVICE": "tpu"}):
            with self.assertRaises(WhisperRuntimeConfigError) as ctx:
                load_whisper_runtime_config_from_environment()
            self.assertIn("Supported devices are 'cpu' and 'cuda'", str(ctx.exception))

    def test_empty_model_raises_config_error(self):
        """Test rejection of explicitly set empty or whitespace-only model string."""
        with patch.dict(os.environ, {"ORBIS_WHISPER_MODEL": "   "}):
            with self.assertRaises(WhisperRuntimeConfigError) as ctx:
                load_whisper_runtime_config_from_environment()
            self.assertIn("ORBIS_WHISPER_MODEL environment variable cannot be empty", str(ctx.exception))

    def test_empty_compute_type_raises_config_error(self):
        """Test rejection of explicitly set empty compute type string."""
        with patch.dict(os.environ, {"ORBIS_WHISPER_COMPUTE_TYPE": ""}):
            with self.assertRaises(WhisperRuntimeConfigError) as ctx:
                load_whisper_runtime_config_from_environment()
            self.assertIn("ORBIS_WHISPER_COMPUTE_TYPE environment variable cannot be empty", str(ctx.exception))

    def test_build_service_with_dependency_injection(self):
        """Test building service from env with mock backend injection."""
        custom_env = {
            "ORBIS_WHISPER_MODEL": "small",
            "ORBIS_WHISPER_DEVICE": "cpu",
            "ORBIS_WHISPER_COMPUTE_TYPE": "int8",
        }
        mock_backend = MockWhisperModel()
        with patch.dict(os.environ, custom_env):
            service = build_transcription_service_from_environment(model_backend=mock_backend)
            self.assertEqual(service.model_name, "small")
            self.assertEqual(service.device, "cpu")
            self.assertEqual(service.compute_type, "int8")
            self.assertEqual(service._model, mock_backend)
            self.assertEqual(format_whisper_runtime_status(service), "small | CPU | int8")

    def test_lazy_loading_preserved_no_downloads(self):
        """Test that building service from environment does not trigger model loading or downloads."""
        service = build_transcription_service_from_environment(model_backend=None)
        # Internal model backend must remain None until transcribe() is executed
        self.assertIsNone(service._model)

    def test_config_error_transcription_service_raises_transcription_error(self):
        """Test that ConfigErrorTranscriptionService raises bounded TranscriptionError on transcribe()."""
        service = ConfigErrorTranscriptionService("Invalid ORBIS_WHISPER_DEVICE 'tpu'")
        self.assertEqual(format_whisper_runtime_status(service), "Configuration Error — Invalid ORBIS_WHISPER_DEVICE 'tpu'")

        with patch.dict("sys.modules"):
            # Ensure faster_whisper is not imported/loaded during transcription attempt
            sys.modules.pop("faster_whisper", None)
            with self.assertRaises(TranscriptionError) as ctx:
                service.transcribe("dummy_path.wav")
            self.assertIn("Whisper configuration error: Invalid ORBIS_WHISPER_DEVICE 'tpu'", str(ctx.exception))
            self.assertNotIn("faster_whisper", sys.modules)

    def test_format_whisper_runtime_status_with_invalid_environment(self):
        """Test that format_whisper_runtime_status reports Configuration Error instead of fallback default when env is invalid."""
        with patch.dict(os.environ, {"ORBIS_WHISPER_DEVICE": "tpu"}):
            status = format_whisper_runtime_status()
            self.assertTrue(status.startswith("Configuration Error — "))
            self.assertIn("tpu", status)
            self.assertNotEqual(status, "large-v3 | CPU | default")


if __name__ == "__main__":
    unittest.main()

