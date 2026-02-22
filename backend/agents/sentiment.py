"""
Sentiment Agent — detects emotional tone in messages.

Uses claude-haiku to detect:
  positive | neutral | tense | urgent | distressed

Flags tense/distressed messages so the Draft Reply Agent
can approach them with care.

Prompts from Integration Spec Section 2.3.
"""
import json
import logging

import anthropic

from backend.agents.state import MessageState
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """
You detect emotional tone in messages to help users approach
sensitive conversations appropriately.
Respond with JSON only.
"""

USER_PROMPT = """
MESSAGE: {message_text}
SENDER: {sender_name} ({relationship_type})
PLATFORM: {platform}

Tone options:
- positive: Warm, appreciative, excited
- neutral: Factual, professional, routine
- tense: Frustrated, disappointed, formal complaint
- urgent: Panicked, overwhelmed, needs immediate help
- distressed: Significant distress or crisis signals

Return JSON:
{{
  "sentiment": "positive|neutral|tense|urgent|distressed",
  "is_complaint": false,
  "needs_careful_response": false,
  "suggested_approach": "one sentence on how to reply"
}}
"""


async def detect_sentiment(state: MessageState) -> MessageState:
    """
    Detect emotional tone using Claude Haiku.
    Falls back to keyword-based detection on failure.
    """
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT.format(
                    message_text=state.content_text[:2000],
                    sender_name=state.sender.name,
                    relationship_type=state.sender.relationship,
                    platform=state.platform,
                ),
            }],
        )

        result = json.loads(response.content[0].text)

        sentiment = result.get("sentiment", "neutral")
        if sentiment not in ("positive", "neutral", "tense", "urgent", "distressed"):
            sentiment = "neutral"

        state.ai_enrichment.sentiment = sentiment
        state.ai_enrichment.is_complaint = result.get("is_complaint", False)
        state.ai_enrichment.needs_careful_response = result.get("needs_careful_response", False)
        state.ai_enrichment.suggested_approach = result.get("suggested_approach", "")

        logger.info(
            f"Sentiment for message {state.id}: {sentiment}, "
            f"careful={state.ai_enrichment.needs_careful_response}"
        )

    except anthropic.APIError as e:
        logger.warning(f"Anthropic API error in sentiment agent: {e}")
        _fallback_sentiment(state)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse sentiment response: {e}")
        _fallback_sentiment(state)
    except Exception as e:
        logger.error(f"Unexpected error in sentiment agent: {e}")
        _fallback_sentiment(state)

    return state


def _fallback_sentiment(state: MessageState) -> None:
    """Keyword-based sentiment fallback."""
    content_lower = state.content_text.lower()

    distressed_keywords = ["help", "please help", "emergency", "crisis", "can't take",
                           "desperate", "struggling", "worried sick"]
    urgent_keywords = ["asap", "immediately", "right now", "can't wait", "time is running out"]
    tense_keywords = ["disappointed", "frustrated", "unacceptable", "complaint",
                      "not happy", "terrible", "worst", "angry", "furious"]
    positive_keywords = ["thank you", "thanks", "great", "awesome", "love", "appreciate",
                         "excellent", "wonderful", "happy"]

    if any(kw in content_lower for kw in distressed_keywords):
        state.ai_enrichment.sentiment = "distressed"
        state.ai_enrichment.needs_careful_response = True
        state.ai_enrichment.suggested_approach = "Respond with empathy and offer concrete help"
    elif any(kw in content_lower for kw in urgent_keywords):
        state.ai_enrichment.sentiment = "urgent"
        state.ai_enrichment.needs_careful_response = True
        state.ai_enrichment.suggested_approach = "Respond quickly and directly"
    elif any(kw in content_lower for kw in tense_keywords):
        state.ai_enrichment.sentiment = "tense"
        state.ai_enrichment.is_complaint = True
        state.ai_enrichment.needs_careful_response = True
        state.ai_enrichment.suggested_approach = "Acknowledge their concern before addressing the issue"
    elif any(kw in content_lower for kw in positive_keywords):
        state.ai_enrichment.sentiment = "positive"
    else:
        state.ai_enrichment.sentiment = "neutral"
