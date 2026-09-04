"""
Automatic Local Summary Engine for Orbis Meeting AI (WP-009)

Local-first, provider-neutral automatic AI summarization using local subprocess commands
(e.g., local Ollama CLI, custom script, or test doubles).
Zero cloud API dependencies by default.
"""

import subprocess
from typing import Sequence, Optional, Any
from pathlib import Path

from orbis_meeting.summary import MeetingSummaryResult
from orbis_meeting.manual_handoff import build_manual_ai_payload, import_manual_ai_result, ManualHandoffError


class AutomaticSummaryError(RuntimeError):
    """Raised when local automatic AI summary generation or validation fails."""
    pass


class LocalCommandSummaryProvider:
    """
    Executes a local command/CLI (e.g. ['ollama', 'run', 'llama3']) via subprocess
    without shell=True. Sends the prompt payload via stdin and returns raw stdout.
    """

    def __init__(
        self,
        command: Sequence[str],
        timeout_seconds: float = 300.0,
        max_input_chars: Optional[int] = None,
    ):
        if not command:
            raise ValueError("Command sequence cannot be empty.")
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.max_input_chars = max_input_chars

    def generate(self, prompt: str) -> str:
        if self.max_input_chars is not None and len(prompt) > self.max_input_chars:
            raise AutomaticSummaryError(
                f"Input prompt length ({len(prompt)} chars) exceeds max_input_chars limit ({self.max_input_chars})."
            )

        try:
            res = subprocess.run(
                self.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as e:
            raise AutomaticSummaryError(
                f"Local summary command timed out after {self.timeout_seconds} seconds."
            ) from e
        except FileNotFoundError as e:
            raise AutomaticSummaryError(
                f"Local summary executable not found: {self.command[0]}"
            ) from e
        except Exception as e:
            raise AutomaticSummaryError(
                f"Failed to execute local summary command: {e}"
            ) from e

        if res.returncode != 0:
            err_msg = res.stderr.strip() if res.stderr else f"Exit code {res.returncode}"
            raise AutomaticSummaryError(
                f"Local summary command returned non-zero exit code {res.returncode}: {err_msg}"
            )

        output = res.stdout.strip()
        if not output:
            raise AutomaticSummaryError("Local summary command returned empty output.")

        return output


class AutomaticSummaryService:
    """
    Orchestrates building summary prompt payload, invoking summary provider,
    and importing/validating the resulting JSON into a MeetingSummaryResult.
    """

    def __init__(
        self,
        provider: Optional[Any] = None,
        template_name: str = "General Meeting",
        language: str = "th",
    ):
        self.provider = provider
        self.template_name = template_name
        self.language = language

    def summarize(
        self,
        transcript_text: str,
        job_id: str = "auto_job",
        template_name: Optional[str] = None,
        language: Optional[str] = None,
    ) -> MeetingSummaryResult:
        if not self.provider:
            raise AutomaticSummaryError("No summary provider configured.")

        tmpl = template_name or self.template_name
        lang = language or self.language

        try:
            payload = build_manual_ai_payload(
                transcript_input=transcript_text,
                template_name=tmpl,
                language=lang,
            )
        except ManualHandoffError as e:
            raise AutomaticSummaryError(f"Failed to build summary prompt: {e}") from e

        try:
            raw_response = self.provider.generate(payload)
        except AutomaticSummaryError:
            raise
        except Exception as e:
            raise AutomaticSummaryError(f"Provider generation failed: {e}") from e

        try:
            summary_res = import_manual_ai_result(
                raw_input_text=raw_response,
                job_id=job_id,
                language=lang,
            )
            return summary_res
        except ManualHandoffError as e:
            raise AutomaticSummaryError(f"Failed to parse/validate AI summary result: {e}") from e
