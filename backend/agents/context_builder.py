"""
Context Builder Agent — enriches sender information.

Uses claude-haiku to determine:
  - Relationship type (vip, close_contact, work_contact, acquaintance, stranger, bot, newsletter)
  - Estimated reply rate
  - Context summary (who this person is)

Prompts from Integration Spec Section 2.1.
"""
import json
import logging
from typing import Optional

import anthropic

from backend.agents.state import MessageState
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """
You are a relationship intelligence agent. Analyze communication patterns
and determine the sender's relationship with the user.
Respond with valid JSON only. No preamble.
"""

USER_PROMPT = """
SENDER INFO:
- Name: {sender_name}
- Identifier: {sender_identifier}
- Platform: {platform}
- Email: {sender_email}

PAST INTERACTIONS (last 20):
{interaction_history}

USER REPLY BEHAVIOR:
- Total messages: {total_messages}
- Times replied: {reply_count}
- Avg reply time: {avg_reply_hours}h
- Last interaction: {last_interaction_days} days ago

Return JSON:
{{
  "relationship_type": "vip|close_contact|work_contact|acquaintance|stranger|bot|newsletter",
  "reply_rate": 0.0,
  "context_summary": "one sentence who this person is",
  "is_likely_important": true
}}
"""


async def build_context(
    state: MessageState,
    interaction_history: Optional[list[str]] = None,
    reply_count: int = 0,
    total_messages: int = 0,
    avg_reply_hours: float = 0.0,
) -> MessageState:
    """
    Enrich the sender context using Claude Haiku.
    Falls back to rule-based classification on failure.
    """
    try:
        history_text = "\n".join(interaction_history or ["No prior interactions found."])

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT.format(
                    sender_name=state.sender.name,
                    sender_identifier=state.sender.id,
                    sender_email=state.sender.email or "unknown",
                    platform=state.platform,
                    interaction_history=history_text,
                    total_messages=total_messages,
                    reply_count=reply_count,
                    avg_reply_hours=avg_reply_hours,
                    last_interaction_days=state.sender.last_interaction_days or "unknown",
                ),
            }],
        )

        result = json.loads(response.content[0].text)

        state.sender.relationship = result.get("relationship_type", "stranger")
        state.sender.historical_reply_rate = float(result.get("reply_rate", 0.0))
        state.sender.context_summary = result.get("context_summary", "")
        state.sender.is_vip = result.get("is_likely_important", False)

        # Append context to enrichment note
        if result.get("context_summary"):
            state.ai_enrichment.context_note = result["context_summary"]

        logger.info(
            f"Context built for sender {state.sender.name}: "
            f"relationship={state.sender.relationship}, vip={state.sender.is_vip}"
        )

    except anthropic.APIError as e:
        logger.warning(f"Anthropic API error in context builder: {e}")
        _fallback_context(state)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse context builder response: {e}")
        _fallback_context(state)
    except Exception as e:
        logger.error(f"Unexpected error in context builder: {e}")
        _fallback_context(state)

    return state


def _fallback_context(state: MessageState) -> None:
    """Rule-based fallback when AI is unavailable."""
    # Simple heuristics
    if state.sender.email and any(
        domain in (state.sender.email or "")
        for domain in ["@gmail.com", "@outlook.com", "@yahoo.com"]
    ):
        state.sender.relationship = "acquaintance"
    elif state.sender.email and any(
        keyword in (state.sender.email or "").lower()
        for keyword in ["noreply", "no-reply", "notifications", "mailer"]
    ):
        state.sender.relationship = "bot"
    else:
        state.sender.relationship = "stranger"

    state.ai_enrichment.context_note = "Context built using fallback rules (AI unavailable)"
