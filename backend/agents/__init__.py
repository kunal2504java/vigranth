"""
Agent pipeline utilities.
"""
import json
import re


def extract_json(text: str) -> dict:
    """
    Extract JSON from an LLM response that may be wrapped in markdown fences.

    Handles:
      - Plain JSON: {"key": "value"}
      - Fenced JSON: ```json\n{"key": "value"}\n```
      - Fenced without language tag: ```\n{"key": "value"}\n```
      - JSON with leading/trailing whitespace or text
    """
    # Try direct parse first (cheapest path)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Last resort: find first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Nothing worked — raise so callers fall through to their fallback
    raise json.JSONDecodeError("No valid JSON found in response", text, 0)
