"""
Unit tests for WP-001 Local Audio Intake Foundation
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src/ is in python path for importing orbis_meeting
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.audio_intake import (
    AudioIntakeError,
    AudioJobMetadata,
    validate_and_intake_audio,
)


class TestAudioIntake(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_sample_file(self, filename: str, content: bytes = b"dummy audio content") -> Path:
        file_path = self.test_dir / filename
        file_path.write_bytes(content)
        return file_path

    def test_ac02_valid_mp3_accepted(self):
        sample = self._create_sample_file("meeting.mp3")
        meta = validate_and_intake_audio(sample)
        self.assertIsInstance(meta, AudioJobMetadata)
        self.assertEqual(meta.filename, "meeting.mp3")
        self.assertEqual(meta.extension, ".mp3")
        self.assertGreater(meta.file_size_bytes, 0)

    def test_ac03_valid_wav_accepted(self):
        sample = self._create_sample_file("meeting.wav")
        meta = validate_and_intake_audio(sample)
        self.assertEqual(meta.extension, ".wav")

    def test_ac04_valid_m4a_accepted(self):
        sample = self._create_sample_file("meeting.m4a")
        meta = validate_and_intake_audio(sample)
        self.assertEqual(meta.extension, ".m4a")

    def test_ac05_case_insensitive_extension(self):
        for name in ["meeting.MP3", "meeting.WAV", "meeting.M4A"]:
            sample = self._create_sample_file(name)
            meta = validate_and_intake_audio(sample)
            self.assertEqual(meta.extension, Path(name).suffix.lower())

    def test_ac06_missing_file_rejected(self):
        missing_path = self.test_dir / "non_existent.mp3"
        with self.assertRaises(AudioIntakeError) as ctx:
            validate_and_intake_audio(missing_path)
        self.assertIn("does not exist", str(ctx.exception))

    def test_ac06_empty_path_rejected(self):
        with self.assertRaises(AudioIntakeError):
            validate_and_intake_audio("")
        with self.assertRaises(AudioIntakeError):
            validate_and_intake_audio(None)

    def test_ac07_directory_path_rejected(self):
        dir_path = self.test_dir / "subfolder"
        dir_path.mkdir()
        with self.assertRaises(AudioIntakeError) as ctx:
            validate_and_intake_audio(dir_path)
        self.assertIn("not a regular file", str(ctx.exception))

    def test_ac08_unsupported_extension_rejected(self):
        for invalid_name in ["video.mp4", "notes.txt", "audio.flac", "script.py"]:
            sample = self._create_sample_file(invalid_name)
            with self.assertRaises(AudioIntakeError) as ctx:
                validate_and_intake_audio(sample)
            self.assertIn("Unsupported audio file extension", str(ctx.exception))

    def test_ac09_zero_byte_file_rejected(self):
        empty_file = self._create_sample_file("empty.mp3", content=b"")
        with self.assertRaises(AudioIntakeError) as ctx:
            validate_and_intake_audio(empty_file)
        self.assertIn("empty (0 bytes)", str(ctx.exception))

    def test_ac10_metadata_fields(self):
        content = b"sample audio bytes for metadata check"
        sample = self._create_sample_file("test.mp3", content=content)
        meta = validate_and_intake_audio(sample)

        self.assertTrue(hasattr(meta, "job_id"))
        self.assertTrue(hasattr(meta, "original_path"))
        self.assertTrue(hasattr(meta, "filename"))
        self.assertTrue(hasattr(meta, "extension"))
        self.assertTrue(hasattr(meta, "file_size_bytes"))

        self.assertEqual(meta.filename, "test.mp3")
        self.assertEqual(meta.extension, ".mp3")
        self.assertEqual(meta.file_size_bytes, len(content))
        self.assertEqual(meta.original_path, str(sample.resolve()))

    def test_ac11_job_id_deterministic(self):
        content = b"deterministic test content 12345"
        sample1 = self._create_sample_file("test1.mp3", content=content)
        sample2 = self._create_sample_file("test2.mp3", content=content)

        meta1 = validate_and_intake_audio(sample1)
        meta2 = validate_and_intake_audio(sample2)

        expected_hash = hashlib.sha256(content).hexdigest()
        self.assertEqual(meta1.job_id, expected_hash)
        self.assertEqual(meta2.job_id, expected_hash)
        self.assertEqual(meta1.job_id, meta2.job_id)

    def test_ac12_original_file_unchanged(self):
        content = b"original binary content - read-only test"
        sample = self._create_sample_file("original.wav", content=content)

        initial_stat = sample.stat()
        initial_hash = hashlib.sha256(content).hexdigest()

        # Run intake validation
        meta = validate_and_intake_audio(sample)

        post_stat = sample.stat()
        post_content = sample.read_bytes()
        post_hash = hashlib.sha256(post_content).hexdigest()

        # Verify file content and stat remain unchanged
        self.assertEqual(post_content, content)
        self.assertEqual(post_hash, initial_hash)
        self.assertEqual(post_stat.st_size, initial_stat.st_size)
        self.assertEqual(post_stat.st_mtime, initial_stat.st_mtime)


if __name__ == "__main__":
    unittest.main()
