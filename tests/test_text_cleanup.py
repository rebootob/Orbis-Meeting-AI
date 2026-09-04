"""
Unit tests for WP-003 Thai Cleanup & Company Dictionary Foundation
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment
from orbis_meeting.text_cleanup import (
    TextCleanupError,
    TextCleanupService,
    load_company_dictionary,
    normalize_whitespace,
    apply_dictionary_replacement,
    validate_dictionary_idempotency,
)


class TestTextCleanup(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.sample_result = TranscriptionResult(
            job_id="test_job_12345",
            language="th",
            full_text="  สวัสดีครับ   คินโทน   และ   คิวเอโฮล  ",
            segments=[
                TranscriptionSegment(start=0.0, end=3.5, text="  สวัสดีครับ   คินโทน  "),
                TranscriptionSegment(start=3.5, end=7.0, text="  และ   คิวเอโฮล  "),
            ],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_whitespace_normalization(self):
        self.assertEqual(normalize_whitespace("  hello   world  "), "hello world")
        self.assertEqual(normalize_whitespace("\tสวัสดี \n\n  ครับ  "), "สวัสดี ครับ")
        self.assertEqual(normalize_whitespace(""), "")

    def test_thai_english_preservation(self):
        text = "สวัสดีครับ Meeting Code 123 Date 2026-09-04"
        self.assertEqual(normalize_whitespace(text), text)

    def test_dictionary_replacement(self):
        dictionary = {"คินโทน": "Kintone", "คิวเอโฮล": "QA HOLD"}
        service = TextCleanupService(dictionary=dictionary)

        cleaned = service.clean_transcript(self.sample_result)
        self.assertEqual(cleaned.segments[0].text, "สวัสดีครับ Kintone")
        self.assertEqual(cleaned.segments[1].text, "และ QA HOLD")
        self.assertEqual(cleaned.full_text, "สวัสดีครับ Kintone และ QA HOLD")

    def test_overlapping_dictionary_keys_precedence(self):
        # Longer key "คิวเอโฮล" must be matched before shorter key "คิวเอ"
        dictionary = {"คิวเอ": "QA", "คิวเอโฮล": "QA HOLD"}
        text = "การประชุม คิวเอโฮล วันนี้"

        result = apply_dictionary_replacement(text, dictionary)
        self.assertEqual(result, "การประชุม QA HOLD วันนี้")
        self.assertNotIn("QAโฮล", result)

    def test_idempotency_across_passes(self):
        dictionary = {"คินโทน": "Kintone", "คิวเอโฮล": "QA HOLD"}
        service = TextCleanupService(dictionary=dictionary)

        first_pass = service.clean_transcript(self.sample_result)
        second_pass = service.clean_transcript(first_pass)

        self.assertEqual(first_pass.full_text, second_pass.full_text)
        self.assertEqual(first_pass.segments, second_pass.segments)

    def test_non_recursive_same_pass_replacement(self):
        # In a single pass, generated replacement text ("BETA") must not be recursively replaced by a key "BETA"
        # Using apply_dictionary_replacement directly on raw text:
        dictionary = {"ALPHA": "BETA", "OTHER": "GAMMA"}
        input_text = "ALPHA OTHER"

        result = apply_dictionary_replacement(input_text, dictionary)
        self.assertEqual(result, "BETA GAMMA")

    def test_unsafe_chained_dictionary_rejected(self):
        # Mappings where a replacement value contains a source key must raise TextCleanupError
        unsafe_dict1 = {"A": "B", "B": "C"}
        with self.assertRaises(TextCleanupError) as ctx1:
            validate_dictionary_idempotency(unsafe_dict1)
        self.assertIn("Unsafe dictionary mapping detected", str(ctx1.exception))

        unsafe_dict2 = {"คิวเอ": "QA", "QA": "Quality Assurance"}
        with self.assertRaises(TextCleanupError) as ctx2:
            TextCleanupService(dictionary=unsafe_dict2)
        self.assertIn("Unsafe dictionary mapping detected", str(ctx2.exception))

    def test_timestamps_and_order_preserved(self):
        service = TextCleanupService(dictionary={"คินโทน": "Kintone"})
        cleaned = service.clean_transcript(self.sample_result)

        self.assertEqual(len(cleaned.segments), len(self.sample_result.segments))
        for original_seg, cleaned_seg in zip(self.sample_result.segments, cleaned.segments):
            self.assertEqual(original_seg.start, cleaned_seg.start)
            self.assertEqual(original_seg.end, cleaned_seg.end)

    def test_original_input_object_unmutated(self):
        original_full_text = self.sample_result.full_text
        original_seg0_text = self.sample_result.segments[0].text

        service = TextCleanupService(dictionary={"คินโทน": "Kintone"})
        service.clean_transcript(self.sample_result)

        self.assertEqual(self.sample_result.full_text, original_full_text)
        self.assertEqual(self.sample_result.segments[0].text, original_seg0_text)

    def test_empty_dictionary_behavior(self):
        service = TextCleanupService(dictionary={})
        cleaned = service.clean_transcript(self.sample_result)

        self.assertEqual(cleaned.segments[0].text, "สวัสดีครับ คินโทน")
        self.assertEqual(cleaned.segments[1].text, "และ คิวเอโฮล")

    def test_missing_dictionary_file_behavior(self):
        non_existent = self.test_dir / "missing.json"
        with self.assertRaises(TextCleanupError) as ctx:
            load_company_dictionary(non_existent)
        self.assertIn("file not found", str(ctx.exception))

    def test_malformed_dictionary_file_behavior(self):
        malformed_path = self.test_dir / "malformed.json"
        malformed_path.write_text("{invalid json file", encoding="utf-8")

        with self.assertRaises(TextCleanupError) as ctx:
            load_company_dictionary(malformed_path)
        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_invalid_dictionary_structure_behavior(self):
        invalid_struct_path = self.test_dir / "list_dict.json"
        invalid_struct_path.write_text("[\"item1\", \"item2\"]", encoding="utf-8")

        with self.assertRaises(TextCleanupError) as ctx:
            load_company_dictionary(invalid_struct_path)
        self.assertIn("must be a JSON object", str(ctx.exception))

    def test_invalid_input_type(self):
        service = TextCleanupService(dictionary={})
        with self.assertRaises(TextCleanupError):
            service.clean_transcript("not a TranscriptionResult")

    def test_default_config_dictionary_file_exists(self):
        # Verify committed config/company_dictionary.json is loadable, valid JSON, and passes idempotency validation
        dict_data = load_company_dictionary("config/company_dictionary.json")
        self.assertIsInstance(dict_data, dict)
        self.assertIn("คินโทน", dict_data)
        self.assertEqual(dict_data["คินโทน"], "Kintone")


if __name__ == "__main__":
    unittest.main()
