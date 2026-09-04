"""
Meeting Summary Foundation for Orbis Meeting AI (WP-004)

Provides a cloud-text-first, provider-neutral summary abstraction.
Consumes cleaned TranscriptionResult objects from WP-003, builds deterministic requests,
and validates structured meeting summary responses without external network calls.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

from orbis_meeting.transcription import TranscriptionResult


class SummaryError(RuntimeError):
    """Raised when meeting summary generation or validation fails."""
    pass


@dataclass(frozen=True)
class ActionItem:
    """Individual action item extracted from meeting summary."""
    task: str
    owner: Optional[str] = None
    due_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeetingSummaryResult:
    """Structured meeting summary output matching V1 output contract."""
    job_id: str
    language: str
    quick_summary: str
    full_summary: str
    decisions: List[str]
    action_items: List[ActionItem]
    risks: List[str]
    follow_up: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "language": self.language,
            "quick_summary": self.quick_summary,
            "full_summary": self.full_summary,
            "decisions": list(self.decisions),
            "action_items": [item.to_dict() for item in self.action_items],
            "risks": list(self.risks),
            "follow_up": list(self.follow_up),
        }


@dataclass(frozen=True)
class SummaryRequest:
    """Minimal text payload sent to summary provider."""
    job_id: str
    language: str
    transcript_text: str
    prompt_instructions: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SummaryProvider(ABC):
    """Provider-neutral boundary for meeting summarization engines."""

    @abstractmethod
    def summarize(self, request: SummaryRequest) -> Dict[str, Any]:
        """Execute summarization request and return raw response dict."""
        pass


def build_summary_prompt(language: str) -> str:
    """
    Build concise, deterministic prompt instructions for meeting summarization.
    """
    return (
        "You are an executive meeting assistant. Summarize the provided meeting transcript.\n"
        "RULES:\n"
        "1. Do not fabricate or hallucinate any information not present in the transcript.\n"
        "2. Use only the supplied transcript content.\n"
        "3. Preserve all exact names, dates, numbers, and technical terms.\n"
        "4. If an action item task has no explicit owner, set owner to null.\n"
        "5. If an action item task has no explicit due date, set due_date to null.\n"
        "6. Decisions must be explicitly stated or strongly supported in the transcript.\n"
        "7. Return output strictly matching the JSON schema with keys: "
        "quick_summary, full_summary, decisions, action_items, risks, follow_up.\n"
        "8. Return JSON output directly. Do not include reasoning steps, commentary, or markdown formatting."
    )


def parse_and_validate_summary_response(
    job_id: str,
    language: str,
    raw_response: Any,
) -> MeetingSummaryResult:
    """
    Validate raw provider response dict and construct MeetingSummaryResult.
    Rejects missing fields, wrong types, empty strings, or malformed payloads.
    """
    if not isinstance(raw_response, dict):
        raise SummaryError(
            f"Provider response for job_id '{job_id}' must be a dictionary, got {type(raw_response).__name__}."
        )

    quick_summary = raw_response.get("quick_summary")
    if not isinstance(quick_summary, str) or not quick_summary.strip():
        raise SummaryError(f"Invalid or missing 'quick_summary' for job_id '{job_id}'. Must be a non-empty string.")

    full_summary = raw_response.get("full_summary")
    if not isinstance(full_summary, str) or not full_summary.strip():
        raise SummaryError(f"Invalid or missing 'full_summary' for job_id '{job_id}'. Must be a non-empty string.")

    decisions_raw = raw_response.get("decisions")
    if not isinstance(decisions_raw, list) or not all(isinstance(item, str) for item in decisions_raw):
        raise SummaryError(f"Invalid 'decisions' for job_id '{job_id}'. Must be a list of strings.")

    action_items_raw = raw_response.get("action_items")
    if not isinstance(action_items_raw, list):
        raise SummaryError(f"Invalid 'action_items' for job_id '{job_id}'. Must be a list of objects.")

    action_items: List[ActionItem] = []
    for idx, item in enumerate(action_items_raw):
        if not isinstance(item, dict):
            raise SummaryError(f"Invalid ActionItem at index {idx} for job_id '{job_id}'. Must be a dict.")

        task = item.get("task")
        if not isinstance(task, str) or not task.strip():
            raise SummaryError(f"ActionItem at index {idx} for job_id '{job_id}' missing valid 'task' string.")

        owner = item.get("owner")
        if owner is not None and not isinstance(owner, str):
            raise SummaryError(f"ActionItem 'owner' at index {idx} for job_id '{job_id}' must be str or None.")

        due_date = item.get("due_date")
        if due_date is not None and not isinstance(due_date, str):
            raise SummaryError(f"ActionItem 'due_date' at index {idx} for job_id '{job_id}' must be str or None.")

        action_items.append(
            ActionItem(
                task=task.strip(),
                owner=owner.strip() if owner and owner.strip() else None,
                due_date=due_date.strip() if due_date and due_date.strip() else None,
            )
        )

    risks_raw = raw_response.get("risks")
    if not isinstance(risks_raw, list) or not all(isinstance(item, str) for item in risks_raw):
        raise SummaryError(f"Invalid 'risks' for job_id '{job_id}'. Must be a list of strings.")

    follow_up_raw = raw_response.get("follow_up")
    if not isinstance(follow_up_raw, list) or not all(isinstance(item, str) for item in follow_up_raw):
        raise SummaryError(f"Invalid 'follow_up' for job_id '{job_id}'. Must be a list of strings.")

    return MeetingSummaryResult(
        job_id=job_id,
        language=language,
        quick_summary=quick_summary.strip(),
        full_summary=full_summary.strip(),
        decisions=[d.strip() for d in decisions_raw if isinstance(d, str) and d.strip()],
        action_items=action_items,
        risks=[r.strip() for r in risks_raw if isinstance(r, str) and r.strip()],
        follow_up=[f.strip() for f in follow_up_raw if isinstance(f, str) and f.strip()],
    )


class MeetingSummaryService:
    """
    Service orchestrating provider-neutral summary generation and validation.
    """

    def __init__(self, provider: SummaryProvider):
        if not isinstance(provider, SummaryProvider):
            raise SummaryError("Provider must be an instance of SummaryProvider.")
        self.provider = provider

    def summarize(self, transcript_result: TranscriptionResult) -> MeetingSummaryResult:
        """
        Generate a validated MeetingSummaryResult from a cleaned TranscriptionResult.
        """
        if not isinstance(transcript_result, TranscriptionResult):
            raise SummaryError("Input must be a valid TranscriptionResult instance.")

        if not transcript_result.full_text or not transcript_result.full_text.strip():
            raise SummaryError(f"Cannot generate summary for empty transcript in job_id '{transcript_result.job_id}'.")

        prompt_instructions = build_summary_prompt(transcript_result.language)

        request = SummaryRequest(
            job_id=transcript_result.job_id,
            language=transcript_result.language,
            transcript_text=transcript_result.full_text,
            prompt_instructions=prompt_instructions,
        )

        try:
            raw_response = self.provider.summarize(request)
        except SummaryError:
            raise
        except Exception as e:
            raise SummaryError(
                f"Summary provider execution failed for job_id '{transcript_result.job_id}': {e}"
            ) from e

        return parse_and_validate_summary_response(
            job_id=transcript_result.job_id,
            language=transcript_result.language,
            raw_response=raw_response,
        )
