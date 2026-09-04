"""
Unit tests for WP-006 Local Export Package Module
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Ensure src/ is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbis_meeting.audio_intake import AudioJobMetadata, validate_and_intake_audio
from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment
from orbis_meeting.summary import MeetingSummaryResult, ActionItem
from orbis_meeting.export_package import (
    ExportPackageError,
    sanitize_folder_component,
    build_summary_markdown,
    build_audio_reference,
    export_meeting_package,
)
from orbis_meeting.ui import OrbisMeetingController


class TestExportPackageModule(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

        # Create sample audio file
        self.audio_file = self.output_dir / "test_meeting.mp3"
        self.audio_file.write_bytes(b"dummy audio binary data for WP-006 testing 12345")

        self.metadata = validate_and_intake_audio(self.audio_file)

        self.transcript_result = TranscriptionResult(
            job_id=self.metadata.job_id,
            language="th",
            full_text="สวัสดีครับ วันนี้เราประชุมเรื่อง Kintone API และ PLAUD Sync",
            segments=[
                TranscriptionSegment(
                    start=0.0,
                    end=5.0,
                    text="สวัสดีครับ วันนี้เราประชุมเรื่อง Kintone API และ PLAUD Sync",
                )
            ],
        )

        self.summary_result = MeetingSummaryResult(
            job_id=self.metadata.job_id,
            language="th",
            title='ประชุม Kintone API & "PLAUD" <Sync>: Q3/2026',
            quick_summary="สรุปการประชุมพัฒนา Kintone API และระบบ PLAUD Audio",
            key_topics=["Kintone API", "PLAUD Audio Sync"],
            full_summary="รายละเอียดการหารือเกี่ยวกับสถาปัตยกรรมระบบ Kintone API...",
            decisions=["อนุมัติแผนการเชื่อมต่อ API"],
            action_items=[
                ActionItem(task="เขียน unit test | API", owner="สมชาย", due_date="2026-09-15"),
                ActionItem(task="จัดทำเอกสาร\nบรรทัดใหม่", owner=None, due_date=None),
            ],
            risks=["ความล่าช้าจากเครือข่าย"],
            follow_up=["นัดหมายประชุมอีกครั้งสัปดาห์หน้า"],
        )

        self.fixed_datetime = datetime(2026, 9, 4, 15, 30)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sanitize_folder_component(self):
        # Invalid Windows chars replaced
        self.assertEqual(
            sanitize_folder_component('Supplier <Quality>: "Review" / Test \\ | ? *'),
            "Supplier_Quality_Review_Test",
        )
        # Empty title fallback
        self.assertEqual(sanitize_folder_component(""), "Meeting")
        self.assertEqual(sanitize_folder_component("   ??? :::   "), "Meeting")
        self.assertEqual(sanitize_folder_component(None), "Meeting")
        # Unicode Thai preservation
        self.assertEqual(
            sanitize_folder_component("การประชุม Kintone API"),
            "การประชุม_Kintone_API",
        )

    def test_build_summary_markdown_rendering(self):
        md = build_summary_markdown(self.summary_result)
        self.assertIn('# ประชุม Kintone API & "PLAUD" <Sync>: Q3/2026', md)
        self.assertIn("## Quick Summary", md)
        self.assertIn("สรุปการประชุมพัฒนา Kintone API", md)
        self.assertIn("## Key Topics", md)
        self.assertIn("- Kintone API", md)
        self.assertIn("## Decisions", md)
        self.assertIn("- อนุมัติแผนการเชื่อมต่อ API", md)
        self.assertIn("## Action Items", md)
        self.assertIn("| Task | Owner | Due Date |", md)
        # Pipe escaped as \| and newline replaced with space
        self.assertIn(r"เขียน unit test \| API", md)
        self.assertIn("สมชาย", md)
        self.assertIn("2026-09-15", md)
        self.assertIn("จัดทำเอกสาร บรรทัดใหม่", md)
        self.assertIn("- | -", md)
        self.assertIn("## Risks / Issues", md)
        self.assertIn("- ความล่าช้าจากเครือข่าย", md)
        self.assertIn("## Follow-up", md)
        self.assertIn("- นัดหมายประชุมอีกครั้งสัปดาห์หน้า", md)

    def test_build_summary_markdown_empty_placeholders(self):
        empty_summary = MeetingSummaryResult(
            job_id="job_empty",
            language="th",
            title="Empty Summary",
            quick_summary="Quick summary",
            key_topics=[],
            full_summary="Full summary",
            decisions=[],
            action_items=[],
            risks=[],
            follow_up=[],
        )
        md = build_summary_markdown(empty_summary)
        self.assertIn("No key topics identified.", md)
        self.assertIn("No explicit decisions recorded.", md)
        self.assertIn("No action items recorded.", md)
        self.assertIn("No risks/issues identified.", md)
        self.assertIn("No follow-up items recorded.", md)

    def test_export_meeting_package_success_and_files_generated(self):
        result = export_meeting_package(
            output_parent=self.output_dir,
            metadata=self.metadata,
            transcript_result=self.transcript_result,
            summary_result=self.summary_result,
            template_name="General Meeting",
            exported_at=self.fixed_datetime,
        )

        self.assertTrue(result.package_dir.exists())
        self.assertTrue(result.package_dir.is_dir())
        self.assertTrue(result.summary_path.exists())
        self.assertTrue(result.transcript_path.exists())
        self.assertTrue(result.ai_ready_path.exists())
        self.assertTrue(result.audio_reference_path.exists())

        # Folder name includes timestamp prefix and safe title
        self.assertTrue(result.package_dir.name.startswith("2026-09-04_1530_"))
        self.assertIn("Kintone_API", result.package_dir.name)

        # 1. Summary.md content
        summary_content = result.summary_path.read_text(encoding="utf-8")
        self.assertIn('# ประชุม Kintone API & "PLAUD" <Sync>: Q3/2026', summary_content)
        self.assertIn("สรุปการประชุมพัฒนา Kintone API", summary_content)

        # 2. Transcript.txt content
        transcript_content = result.transcript_path.read_text(encoding="utf-8")
        self.assertEqual(transcript_content, self.transcript_result.full_text)

        # 3. AI_SUMMARY_READY.md content
        ai_ready_content = result.ai_ready_path.read_text(encoding="utf-8")
        self.assertIn("TEMPLATE FOCUS: General Meeting", ai_ready_content)
        self.assertIn("สวัสดีครับ วันนี้เราประชุมเรื่อง Kintone API", ai_ready_content)
        self.assertNotIn(self.metadata.original_path, ai_ready_content)

        # 4. audio_reference.json content
        audio_ref_content = json.loads(result.audio_reference_path.read_text(encoding="utf-8"))
        self.assertEqual(audio_ref_content["job_id"], self.metadata.job_id)
        self.assertEqual(audio_ref_content["original_filename"], "test_meeting.mp3")
        self.assertEqual(audio_ref_content["extension"], ".mp3")
        self.assertEqual(audio_ref_content["file_size_bytes"], self.metadata.file_size_bytes)
        self.assertEqual(audio_ref_content["sha256"], self.metadata.job_id)
        self.assertEqual(audio_ref_content["source_path"], self.metadata.original_path)

    def test_original_audio_unmodified_and_not_copied(self):
        initial_content = self.audio_file.read_bytes()

        result = export_meeting_package(
            output_parent=self.output_dir,
            metadata=self.metadata,
            transcript_result=self.transcript_result,
            summary_result=self.summary_result,
            exported_at=self.fixed_datetime,
        )

        # Original file intact
        self.assertEqual(self.audio_file.read_bytes(), initial_content)

        # No audio file in exported directory
        exported_files = [f.name for f in result.package_dir.iterdir()]
        self.assertNotIn("test_meeting.mp3", exported_files)
        self.assertEqual(
            set(exported_files),
            {"Summary.md", "Transcript.txt", "AI_SUMMARY_READY.md", "audio_reference.json"},
        )

    def test_overwrite_protection_creates_unique_sibling_directory(self):
        res1 = export_meeting_package(
            output_parent=self.output_dir,
            metadata=self.metadata,
            transcript_result=self.transcript_result,
            summary_result=self.summary_result,
            exported_at=self.fixed_datetime,
        )

        res2 = export_meeting_package(
            output_parent=self.output_dir,
            metadata=self.metadata,
            transcript_result=self.transcript_result,
            summary_result=self.summary_result,
            exported_at=self.fixed_datetime,
        )

        self.assertNotEqual(res1.package_dir, res2.package_dir)
        self.assertTrue(res1.package_dir.exists())
        self.assertTrue(res2.package_dir.exists())
        self.assertTrue(res2.package_dir.name.endswith("_2"))

    def test_invalid_destination_rejection(self):
        non_existent = self.output_dir / "non_existent_folder"
        with self.assertRaises(ExportPackageError) as ctx:
            export_meeting_package(
                output_parent=non_existent,
                metadata=self.metadata,
                transcript_result=self.transcript_result,
                summary_result=self.summary_result,
            )
        self.assertIn("does not exist", str(ctx.exception))


class TestUIControllerExportIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

        self.sample_mp3 = self.output_dir / "test_audio.mp3"
        self.sample_mp3.write_bytes(b"dummy mp3 content 12345")

        self.controller = OrbisMeetingController()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_package_requires_all_session_data(self):
        # 1. Ready state - missing metadata
        with self.assertRaises(ExportPackageError) as ctx1:
            self.controller.export_meeting_package(self.output_dir)
        self.assertIn("metadata, transcript, and summary must all be completed first", str(ctx1.exception))

        # 2. Audio selected - missing transcript and summary
        self.controller.select_audio_file(self.sample_mp3)
        with self.assertRaises(ExportPackageError) as ctx2:
            self.controller.export_meeting_package(self.output_dir)
        self.assertIn("metadata, transcript, and summary must all be completed first", str(ctx2.exception))

    def test_export_package_success_when_session_complete(self):
        self.controller.select_audio_file(self.sample_mp3)
        self.controller.current_transcript_result = TranscriptionResult(
            job_id=self.controller.current_metadata.job_id,
            language="th",
            full_text="ข้อความทดสอบ",
            segments=[],
        )
        self.controller.current_summary_result = MeetingSummaryResult(
            job_id=self.controller.current_metadata.job_id,
            language="th",
            title="สรุปการประชุม",
            quick_summary="สรุปสั้น",
            key_topics=["หัวข้อ 1"],
            full_summary="สรุปยาว",
            decisions=["การตัดสินใจ 1"],
            action_items=[],
            risks=[],
            follow_up=[],
        )

        res = self.controller.export_meeting_package(self.output_dir)
        self.assertIsNotNone(res)
        self.assertTrue(res.package_dir.exists())
        self.assertTrue(res.summary_path.exists())


if __name__ == "__main__":
    unittest.main()
