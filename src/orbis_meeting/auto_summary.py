"""
Automatic Local Summary Engine for Orbis Meeting AI (WP-009 & WP-009-R1)

Local-first, provider-neutral automatic AI summarization using local subprocess commands
(e.g., local Ollama CLI, custom script, or test doubles).
Zero cloud API dependencies by default.
Runtime configurable via environment variables without source code changes.
"""

import os
import json
import subprocess
from typing import Sequence, Optional, Any, Dict, Tuple
from pathlib import Path

from orbis_meeting.summary import MeetingSummaryResult, SummaryError, parse_and_validate_summary_response
from orbis_meeting.manual_handoff import build_manual_ai_payload, ManualHandoffError


class AutomaticSummaryError(RuntimeError):
    """Raised when local automatic AI summary generation or validation fails."""
    pass


def parse_automatic_summary_response(
    raw_response: str,
    job_id: str = "auto_job",
    language: str = "th",
) -> MeetingSummaryResult:
    """
    Parse and validate raw JSON response string strictly for machine-to-machine automatic mode.

    Rules:
    - Must be a raw JSON object string.
    - Surrounding whitespace is stripped.
    - First character after stripping MUST be '{'.
    - Last character after stripping MUST be '}'.
    - Fenced code blocks (```json ... ```) or surrounding prose are strictly REJECTED.
    - JSON root MUST be an object/dict.
    - WP-004 schema validation is reused via parse_and_validate_summary_response.
    """
    if not raw_response or not isinstance(raw_response, str) or not raw_response.strip():
        raise AutomaticSummaryError("Automatic AI summary response is empty.")

    cleaned = raw_response.strip()

    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        raise AutomaticSummaryError(
            "Automatic AI result must contain raw JSON object text starting with '{' and ending with '}'."
        )

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AutomaticSummaryError(f"Invalid JSON format: {e}") from e

    if not isinstance(data, dict):
        raise AutomaticSummaryError("Automatic AI JSON root must be an object/dict.")

    try:
        return parse_and_validate_summary_response(
            job_id=job_id,
            language=language,
            raw_response=data,
        )
    except SummaryError as e:
        raise AutomaticSummaryError(f"Schema Validation Failure: {e}") from e


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
            summary_res = parse_automatic_summary_response(
                raw_response=raw_response,
                job_id=job_id,
                language=lang,
            )
            return summary_res
        except AutomaticSummaryError:
            raise
        except Exception as e:
            raise AutomaticSummaryError(f"Failed to parse/validate AI summary result: {e}") from e


def build_auto_summary_service_from_environment(
    env: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[AutomaticSummaryService], str]:
    """
    Build AutomaticSummaryService from environment variables without modifying source code.

    Env vars:
    - ORBIS_SUMMARY_COMMAND_JSON: JSON array of argv strings e.g. '["ollama", "run", "qwen3:8b"]'
    - ORBIS_SUMMARY_TIMEOUT_SECONDS: Optional float > 0 (default 300.0)
    - ORBIS_SUMMARY_MAX_INPUT_CHARS: Optional int > 0

    Returns:
    (service_or_none, engine_status_string)
    Status strings:
    - "Summary Engine: Manual Only" (when env var is absent or empty)
    - "Summary Engine: Local Automatic Ready" (when successfully configured)
    - "Summary Engine: Configuration Error — <detail>" (when env config is malformed)
    """
    if env is None:
        env = dict(os.environ)

    cmd_json = env.get("ORBIS_SUMMARY_COMMAND_JSON")
    if cmd_json is None or not cmd_json.strip():
        return None, "Summary Engine: Manual Only"

    try:
        command_list = json.loads(cmd_json.strip())
    except Exception as e:
        return None, f"Summary Engine: Configuration Error — ORBIS_SUMMARY_COMMAND_JSON is invalid JSON: {e}"

    if not isinstance(command_list, list):
        return None, "Summary Engine: Configuration Error — ORBIS_SUMMARY_COMMAND_JSON must be a JSON array."

    if not command_list:
        return None, "Summary Engine: Configuration Error — ORBIS_SUMMARY_COMMAND_JSON array cannot be empty."

    for item in command_list:
        if not isinstance(item, str):
            return None, f"Summary Engine: Configuration Error — All argv items in ORBIS_SUMMARY_COMMAND_JSON must be strings."

    timeout_seconds = 300.0
    raw_timeout = env.get("ORBIS_SUMMARY_TIMEOUT_SECONDS")
    if raw_timeout is not None and raw_timeout.strip():
        try:
            val = float(raw_timeout.strip())
            if val <= 0:
                return None, "Summary Engine: Configuration Error — ORBIS_SUMMARY_TIMEOUT_SECONDS must be a positive number."
            timeout_seconds = val
        except ValueError:
            return None, "Summary Engine: Configuration Error — ORBIS_SUMMARY_TIMEOUT_SECONDS must be a valid number."

    max_input_chars = None
    raw_max_chars = env.get("ORBIS_SUMMARY_MAX_INPUT_CHARS")
    if raw_max_chars is not None and raw_max_chars.strip():
        try:
            val = int(raw_max_chars.strip())
            if val <= 0:
                return None, "Summary Engine: Configuration Error — ORBIS_SUMMARY_MAX_INPUT_CHARS must be a positive integer."
            max_input_chars = val
        except ValueError:
            return None, "Summary Engine: Configuration Error — ORBIS_SUMMARY_MAX_INPUT_CHARS must be a valid integer."

    try:
        provider = LocalCommandSummaryProvider(
            command=command_list,
            timeout_seconds=timeout_seconds,
            max_input_chars=max_input_chars,
        )
        service = AutomaticSummaryService(provider=provider)
        return service, "Summary Engine: Local Automatic Ready"
    except Exception as e:
        return None, f"Summary Engine: Configuration Error — {e}"
