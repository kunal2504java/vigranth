"""
Classifier Agent — tags messages with priority labels and scores.

Uses claude-haiku to classify messages as:
  urgent | action | fyi | social | spam

And assigns a priority_score from 0.0 to 1.0.

Prompts from Integration Spec Section 2.2.
Score guide from PRD Section 6.2.
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
You are a message priority classifier.
Respond with valid JSON only.
"""

USER_PROMPT = """
SENDER: {relationship_type} | reply rate: {reply_rate} | VIP: {is_vip}
PLATFORM: {platform}
TIME: {timestamp}

MESSAGE:
{message_text}

LABELS:
- urgent: Requires response within hours, time-sensitive
- action: Requires response, not immediately critical
- fyi: Informational, no response needed
- social: Casual, low professional priority
- spam: Unsolicited, promotional, low value

SCORE GUIDE:
- 0.9-1.0: Urgent from VIP (investor, boss, client emergency)
- 0.7-0.89: Action from known contact
- 0.5-0.69: Action from stranger OR fyi from VIP
- 0.3-0.49: Social from known contact
- 0.0-0.29: Newsletter, bot, spam

Return JSON:
{{
  "label": "urgent|action|fyi|social|spam",
  "priority_score": 0.0,
  "time_sensitive": true,
  "reasoning": "one sentence max"
}}
"""


async def classify_message(state: MessageState) -> MessageState:
    """
    Classify a message using Claude Haiku.
    Falls back to rule-based classification on failure.
    """
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT.format(
                    relationship_type=state.sender.relationship,
                    reply_rate=state.sender.historical_reply_rate,
                    is_vip=state.sender.is_vip,
                    platform=state.platform,
                    timestamp=state.timestamp,
                    message_text=state.content_text[:2000],  # truncate for token limits
                ),
            }],
        )

        result = json.loads(response.content[0].text)

        label = result.get("label", "fyi")
        if label not in ("urgent", "action", "fyi", "social", "spam"):
            label = "fyi"

        score = float(result.get("priority_score", 0.0))
        score = max(0.0, min(1.0, score))  # clamp to valid range

        state.ai_enrichment.priority_label = label
        state.ai_enrichment.priority_score = score
        state.ai_enrichment.time_sensitive = result.get("time_sensitive", False)
        state.ai_enrichment.classification_reasoning = result.get("reasoning", "")

        # Append reasoning to context note
        reasoning = result.get("reasoning", "")
        if reasoning:
            existing = state.ai_enrichment.context_note
            state.ai_enrichment.context_note = (
                f"{existing} | {reasoning}" if existing else reasoning
            )

        logger.info(
            f"Classified message {state.id}: label={label}, score={score:.2f}"
        )

    except anthropic.APIError as e:
        logger.warning(f"Anthropic API error in classifier: {e}")
        _fallback_classify(state)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse classifier response: {e}")
        _fallback_classify(state)
    except Exception as e:
        logger.error(f"Unexpected error in classifier: {e}")
        _fallback_classify(state)

    return state


def _fallback_classify(state: MessageState) -> None:
    """
    Rule-based fallback classification.
    Uses the priority scoring weights from PRD Section 6.2:
      Sender Relationship: 30%, Urgency Keywords: 20%, Time Sensitivity: 15%,
      Historical Response Rate: 15%, Thread Activity: 10%, Sentiment: 10%
    """
    score = 0.0
    label = "fyi"
    content_lower = state.content_text.lower()

    # Sender relationship weight (30%)
    relationship_scores = {
        "vip": 0.30,
        "close_contact": 0.24,
        "work_contact": 0.18,
        "acquaintance": 0.12,
        "stranger": 0.06,
        "bot": 0.02,
        "newsletter": 0.01,
    }
    score += relationship_scores.get(state.sender.relationship, 0.06)

    # Urgency keywords (20%)
    urgent_keywords = ["asap", "urgent", "deadline", "today", "help", "call me",
                       "immediately", "critical", "emergency", "important"]
    keyword_hits = sum(1 for kw in urgent_keywords if kw in content_lower)
    score += min(0.20, keyword_hits * 0.05)

    # Historical response rate (15%)
    score += state.sender.historical_reply_rate * 0.15

    # VIP boost
    if state.sender.is_vip:
        score += 0.15

    # Clamp
    score = max(0.0, min(1.0, score))

    # Determine label from score
    if score >= 0.85:
        label = "urgent"
    elif score >= 0.60:
        label = "action"
    elif score >= 0.30:
        label = "fyi"
    else:
        # Check for spam/social signals
        spam_keywords = ["unsubscribe", "click here", "limited time", "offer", "deal"]
        if any(kw in content_lower for kw in spam_keywords):
            label = "spam"
            score = min(score, 0.15)
        else:
            label = "social"

    state.ai_enrichment.priority_label = label
    state.ai_enrichment.priority_score = round(score, 3)
    state.ai_enrichment.classification_reasoning = "Classified using rule-based fallback"
