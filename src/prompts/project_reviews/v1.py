"""Prompt asset for project review generation version 1."""

import json
from typing import Any

PROMPT_VERSION = "project_reviews.v1"

SYSTEM_PROMPT = """You generate structured project reviews.

Use only the supplied project, run context, and review evidence.
Do not invent citations or claims outside the evidence list.
Return structured output with:
- project_id
- summary
- municipality_relevance
- readiness
- financing_signals
- implementation_considerations
- risks_and_caveats
- citation_ids
"""


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Build the chat message payload for project review generation."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)},
    ]
