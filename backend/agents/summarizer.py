"""
Thread Summarizer Agent — condenses long threads into actionable bullet points.

Uses claude-haiku for speed.
Prompts from Integration Spec Section 2.5.

Triggered when a thread has > 5 messages.
"""
import json
import logging
from typing import Optional

import anthropic

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """
You summarize conversation threads into actionable bullet points.
Respond with JSON only.
"""

USER_PROMPT = """
PLATFORM: {platform}
PARTICIPANTS: {participants}
MESSAGES ({message_count} total):
{messages}

Return JSON:
{{
  "key_points": ["max 3 bullets of what was discussed/decided"],
  "action_items": ["any actions requested or agreed to"],
  "current_status": "one sentence where things stand",
  "next_step": "what user needs to do, or null"
}}
"""


async def summarize_thread(
    platform: str,
    participants: list[str],
    messages: list[str],
) -> Optional[dict]:
    """
    Summarize a thread into key points, action items, status, and next steps.
    Returns None on failure.
    """
    if len(messages) < 3:
        return None

    try:
        messages_text = "\n---\n".join(messages[-20:])  # last 20 messages max

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT.format(
                    platform=platform,
                    participants=", ".join(participants),
                    message_count=len(messages),
                    messages=messages_text,
                ),
            }],
        )

        result = json.loads(response.content[0].text)

        summary = {
            "key_points": result.get("key_points", [])[:3],
            "action_items": result.get("action_items", []),
            "current_status": result.get("current_status", ""),
            "next_step": result.get("next_step"),
        }

        logger.info(f"Thread summarized: {len(summary['key_points'])} key points")
        return summary

    except anthropic.APIError as e:
        logger.warning(f"Anthropic API error in summarizer: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse summarizer response: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in summarizer: {e}")
        return None
