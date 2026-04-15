"""Prompt asset for narrative explanation generation version 1."""

import json
from typing import Any

PROMPT_VERSION = "explanations.v1"

SYSTEM_PROMPT = """You generate grounded recommendation explanations.

Use only the supplied structured inputs.
Do not invent projects, evidence, or claims.
Return structured output with:
- executive_summary
- rationale
- caveats
- cited_evidence_ids
Reference project titles exactly as provided when discussing selections.
"""


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Build the chat message payload for explanation generation."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Generate a grounded explanation from this workflow input.\n"
                "Cite only evidence IDs present in `evidence_bundle.items`.\n"
                f"{json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)}"
            ),
        },
    ]
