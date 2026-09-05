"""
Ollama Structured Local Summary Adapter for Orbis Meeting AI (WP-013)

Provides a minimal, safe local adapter allowing LocalCommandSummaryProvider
to obtain strict machine-to-machine JSON from Ollama via local HTTP API.

Workflow:
1. Reads summary prompt from UTF-8 stdin.
2. Sends HTTP POST request to local Ollama API (http://127.0.0.1:11434/api/generate)
   with think=false, stream=false, temperature=0, and Orbis JSON Schema.
3. Extracts model response string from Ollama envelope JSON.
4. Outputs raw model response to stdout (no markdown, no logs, no prose).
5. Errors written to stderr with non-zero exit status code.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Dict, Any, Optional

OLLAMA_LOCAL_ENDPOINT = "http://127.0.0.1:11434/api/generate"

ORBIS_SUMMARY_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "quick_summary": {"type": "string"},
        "key_topics": {
            "type": "array",
            "items": {"type": "string"},
        },
        "full_summary": {"type": "string"},
        "decisions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                },
                "required": ["task"],
            },
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
        },
        "follow_up": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "title",
        "quick_summary",
        "key_topics",
        "full_summary",
        "decisions",
        "action_items",
        "risks",
        "follow_up",
    ],
}


def query_ollama_structured_api(
    prompt: str,
    model: str = "qwen3:4b",
    timeout: float = 300.0,
    schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Send prompt to local Ollama HTTP API with structured JSON Schema enforcement.
    Returns raw response string extracted from Ollama envelope.
    """
    if not prompt or not prompt.strip():
        raise ValueError("Input prompt cannot be empty.")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
        },
        "format": schema if schema is not None else ORBIS_SUMMARY_JSON_SCHEMA,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_LOCAL_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(f"Ollama API HTTP {e.code} error: {e.reason}. Detail: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to local Ollama API at {OLLAMA_LOCAL_ENDPOINT}: {e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"Error querying local Ollama API: {e}") from e

    try:
        envelope = json.loads(resp_body)
    except Exception as e:
        raise RuntimeError(f"Invalid JSON envelope from Ollama API: {e}") from e

    if not isinstance(envelope, dict):
        raise RuntimeError("Ollama API envelope must be a JSON object.")

    response_text = envelope.get("response")
    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("Ollama API response field is missing or empty.")

    return response_text.strip()


def main(args_list: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ollama Structured Local Summary Adapter for Orbis Meeting AI"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen3:4b",
        help="Ollama model name (default: qwen3:4b)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="HTTP request timeout in seconds",
    )

    args = parser.parse_args(args_list)

    try:
        if hasattr(sys.stdin, "buffer"):
            prompt_bytes = sys.stdin.buffer.read()
            prompt = prompt_bytes.decode("utf-8", errors="replace")
        else:
            prompt = sys.stdin.read()
    except Exception as e:
        sys.stderr.write(f"Error reading prompt from stdin: {e}\n")
        return 1

    if not prompt or not prompt.strip():
        sys.stderr.write("Error: Prompt read from stdin is empty.\n")
        return 1

    try:
        result_json_str = query_ollama_structured_api(
            prompt=prompt,
            model=args.model,
            timeout=args.timeout,
        )
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(result_json_str.encode("utf-8"))
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(result_json_str)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
