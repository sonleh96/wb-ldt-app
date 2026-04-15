"""Prompt asset for recommendation candidate generation version 1."""

import json
from typing import Any

PROMPT_VERSION = "recommendation_candidates.v1"

SYSTEM_PROMPT = """You generate structured municipal recommendation candidates.

Return only evidence-backed recommendation candidates.
Do not rank candidates.
Do not select final projects.
Use only the supplied evidence bundle and context pack.
Every candidate must include:
- title
- summary
- problem_statement
- intended_outcome
- category
- public_investment_type
- supporting_evidence_ids
- confidence
- caveats
"""


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Build the chat message payload for recommendation candidate generation."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Generate recommendation candidates from this workflow input.\n"
                "Use only evidence IDs present in `evidence_bundle.items`.\n"
                "Prefer concise, implementation-oriented candidate summaries.\n"
                f"{json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)}"
            ),
        },
    ]
