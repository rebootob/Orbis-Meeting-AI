"""
Manual AI Handoff Foundation for Orbis Meeting AI (WP-005B)

Generates AI-ready text payloads combining template focus, prompt rules, schema, and transcript.
Accepts, extracts, and validates manually pasted AI JSON responses using WP-004 contracts.
Zero network or API dependencies.
"""

import json
import re
from typing import Dict, Any, Optional, Union

from orbis_meeting.transcription import TranscriptionResult
from orbis_meeting.summary import (
    MeetingSummaryResult,
    SummaryError,
    build_summary_prompt,
    parse_and_validate_summary_response,
)


class ManualHandoffError(ValueError):
    """Raised when manual AI payload generation or JSON import validation fails."""
    pass


SUMMARY_TEMPLATES: Dict[str, str] = {
    "General Meeting": (
        "TEMPLATE FOCUS: General Meeting\n"
        "- Emphasize overall discussion topics, key decisions, action items, risks, and follow-up steps."
    ),
    "Management Meeting": (
        "TEMPLATE FOCUS: Management Meeting\n"
        "- Emphasize executive priorities, major strategic decisions, KPI/business impacts (if explicitly stated), risks, and item ownership."
    ),
    "Project Meeting": (
        "TEMPLATE FOCUS: Project Meeting\n"
        "- Emphasize project progress, blockers, technical decisions, milestone targets, action items, and dependencies."
    ),
    "Problem Solving / RCA": (
        "TEMPLATE FOCUS: Problem Solving / RCA\n"
        "- Emphasize problem definition, facts/evidence, root causes (if supported), immediate containment actions, corrective/preventive actions, owners, and due dates."
    ),
}


def build_manual_ai_payload(
    transcript_input: Union[TranscriptionResult, str],
    template_name: str = "General Meeting",
    language: str = "th",
) -> str:
    """
    Build a single deterministic AI-ready text payload for pasting into ChatGPT, Gemini, or Claude.

    :param transcript_input: TranscriptionResult object or full transcript text.
    :param template_name: One of the supported template focus names.
    :param language: Language code ("th", "en", etc.).
    :return: Formatted text payload string.
    """
    if isinstance(transcript_input, TranscriptionResult):
        transcript_text = transcript_input.full_text
        lang = transcript_input.language
    elif isinstance(transcript_input, str):
        transcript_text = transcript_input
        lang = language
    else:
        raise ManualHandoffError("Input must be a TranscriptionResult instance or transcript string.")

    if not transcript_text or not transcript_text.strip():
        raise ManualHandoffError("Cannot generate AI payload for empty transcript text.")

    template_focus = SUMMARY_TEMPLATES.get(template_name, SUMMARY_TEMPLATES["General Meeting"])
    base_instructions = build_summary_prompt(lang)

    return (
        "==================================================\n"
        "ORBIS MEETING AI — MANUAL SUMMARY REQUEST\n"
        "==================================================\n\n"
        f"Selected Template: {template_name}\n"
        f"{template_focus}\n\n"
        "INSTRUCTIONS & RULES:\n"
        f"{base_instructions}\n\n"
        "==================================================\n"
        "CLEANED TRANSCRIPT CONTENT:\n"
        "==================================================\n"
        f"{transcript_text.strip()}\n"
    )


def extract_json_payload(raw_text: str) -> str:
    """
    Extract raw JSON string from potentially markdown-wrapped text.

    Supports raw JSON, ```json ... ```, or ``` ... ``` code blocks.
    """
    if not raw_text or not raw_text.strip():
        raise ManualHandoffError("Pasted AI result is empty. Please paste valid JSON.")

    cleaned = raw_text.strip()

    # Match ```json ... ``` or ``` ... ``` markdown blocks
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    else:
        # Fall back to finding first '{' and last '}'
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and start < end:
            cleaned = cleaned[start:end + 1].strip()

    if not cleaned:
        raise ManualHandoffError("Could not locate valid JSON structure in pasted text.")

    return cleaned


def import_manual_ai_result(
    raw_input_text: str,
    job_id: str = "manual_job",
    language: str = "th",
) -> MeetingSummaryResult:
    """
    Parse and validate manually pasted AI JSON response into a MeetingSummaryResult.

    :param raw_input_text: Raw text pasted by user (JSON or markdown-wrapped JSON).
    :param job_id: Associated job_id.
    :param language: Associated language code.
    :return: Validated MeetingSummaryResult object.
    """
    json_str = extract_json_payload(raw_input_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ManualHandoffError(f"Invalid JSON format: {e}") from e

    try:
        return parse_and_validate_summary_response(
            job_id=job_id,
            language=language,
            raw_response=data,
        )
    except SummaryError as e:
        raise ManualHandoffError(f"Schema Validation Failure: {e}") from e
