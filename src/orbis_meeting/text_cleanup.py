"""
Thai Cleanup & Company Dictionary Foundation for Orbis Meeting AI (WP-003)

Provides deterministic text cleanup, whitespace normalization, and company dictionary
term replacement for TranscriptionResult objects without modifying timestamps or original inputs.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from orbis_meeting.transcription import TranscriptionResult, TranscriptionSegment


class TextCleanupError(ValueError):
    """Raised when text cleanup or dictionary loading fails."""
    pass


def load_company_dictionary(dictionary_path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """
    Load company dictionary mappings from a JSON file.

    :param dictionary_path: Path to dictionary JSON file. If None, defaults to config/company_dictionary.json.
    :return: Dictionary mapping original term -> replacement term.
    """
    if dictionary_path is None:
        default_path = Path("config/company_dictionary.json")
        if not default_path.exists():
            return {}
        path = default_path
    else:
        path = Path(dictionary_path)
        if not path.exists():
            raise TextCleanupError(f"Company dictionary file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise TextCleanupError(f"Invalid JSON in company dictionary file '{path}': {e}") from e
    except Exception as e:
        raise TextCleanupError(f"Failed to read company dictionary file '{path}': {e}") from e

    if not isinstance(data, dict):
        raise TextCleanupError(f"Company dictionary content in '{path}' must be a JSON object.")

    cleaned_dict: Dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise TextCleanupError(f"Invalid entry in company dictionary '{path}': keys and values must be strings.")
        if k:
            cleaned_dict[k] = v

    return cleaned_dict


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and trim leading/trailing space."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def apply_dictionary_replacement(text: str, dictionary: Dict[str, str]) -> str:
    """
    Apply dictionary replacements deterministically.
    Longer matching keys take precedence over shorter keys.
    """
    if not text or not dictionary:
        return text

    sorted_keys = sorted(dictionary.keys(), key=len, reverse=True)

    result = text
    for key in sorted_keys:
        val = dictionary[key]
        if key in result:
            result = result.replace(key, val)

    return result


class TextCleanupService:
    """
    Deterministic transcript cleanup service.
    Normalizes whitespace and applies company dictionary term replacements.
    """

    def __init__(self, dictionary: Optional[Dict[str, str]] = None, dictionary_path: Optional[Union[str, Path]] = None):
        if dictionary is not None:
            self.dictionary = dictionary
        else:
            self.dictionary = load_company_dictionary(dictionary_path)

    def clean_transcript(self, result: TranscriptionResult) -> TranscriptionResult:
        """
        Clean a TranscriptionResult without mutating the input object or altering segment timestamps.

        :param result: Input TranscriptionResult from WP-002.
        :return: New cleaned TranscriptionResult instance.
        """
        if not isinstance(result, TranscriptionResult):
            raise TextCleanupError("Input must be a valid TranscriptionResult instance.")

        cleaned_segments: List[TranscriptionSegment] = []

        for seg in result.segments:
            norm_text = normalize_whitespace(seg.text)
            final_text = apply_dictionary_replacement(norm_text, self.dictionary)

            if final_text:
                cleaned_segments.append(
                    TranscriptionSegment(
                        start=seg.start,
                        end=seg.end,
                        text=final_text,
                    )
                )

        full_text = " ".join(seg.text for seg in cleaned_segments).strip()

        return TranscriptionResult(
            job_id=result.job_id,
            language=result.language,
            full_text=full_text,
            segments=cleaned_segments,
        )
