"""Helpers for compact observability payload summaries."""

from typing import Any


def summarize_node_output(output: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary of a node output for tracing."""

    summary: dict[str, Any] = {}
    for key, value in output.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        elif isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = sorted(value.keys())
    return summary
