"""
Unified Enrichment Agent — replaces the separate Context Builder,
Classifier, and Sentiment agents with a single Claude Haiku call.

One API call per message instead of three.
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
You are a message enrichment agent. Analyze a message and its sender context.
Respond with valid JSON only. No preamble.
"""

USER_PROMPT = """
SENDER: {sender_name} ({sender_identifier}) on {platform}
EMAIL: {sender_email}
PAST INTERACTIONS ({total_messages} total, {reply_count} replied):
{interaction_history}

MESSAGE:
{message_text}

Return JSON with ALL of these fields:
{{
  "relationship_type": "vip|close_contact|work_contact|acquaintance|stranger|bot|newsletter",
  "reply_rate": 0.0,
  "context_summary": "one sentence who this person is",
  "is_likely_important": true,
  "label": "urgent|action|fyi|social|spam",
  "priority_score": 0.0,
  "time_sensitive": false,
  "reasoning": "one sentence on priority",
  "sentiment": "positive|neutral|tense|urgent|distressed",
  "is_complaint": false,
  "needs_careful_response": false,
  "suggested_approach": "one sentence on how to reply"
}}

LABEL GUIDE:
- urgent: Requires response within hours, time-sensitive
- action: Requires response, not immediately critical
- fyi: Informational, no response needed
- social: Casual, low professional priority
- spam: Unsolicited, promotional

SCORE GUIDE:
- 0.9-1.0: Urgent from VIP
- 0.7-0.89: Action from known contact
- 0.5-0.69: Action from stranger or fyi from VIP
- 0.3-0.49: Social from known contact
- 0.0-0.29: Newsletter, bot, spam
"""


async def enrich_message(
    state: MessageState,
    interaction_history: Optional[list[str]] = None,
    reply_count: int = 0,
    total_messages: int = 0,
) -> MessageState:
    """
    Enrich a message with sender context, classification, and sentiment
    using a single Claude Haiku call. Falls back to rule-based logic on failure.
    """
    try:
        history_text = "\n".join(interaction_history or ["No prior interactions."])

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT.format(
                    sender_name=state.sender.name,
                    sender_identifier=state.sender.id,
                    sender_email=state.sender.email or "unknown",
                    platform=state.platform,
                    total_messages=total_messages,
                    reply_count=reply_count,
                    interaction_history=history_text,
                    message_text=state.content_text[:2000],
                ),
            }],
        )

        from backend.agents import extract_json
        result = extract_json(response.content[0].text)

        # Sender context
        state.sender.relationship = result.get("relationship_type", "stranger")
        state.sender.historical_reply_rate = float(result.get("reply_rate", 0.0))
        state.sender.context_summary = result.get("context_summary", "")
        state.sender.is_vip = result.get("is_likely_important", False)

        # Classification
        label = result.get("label", "fyi")
        if label not in ("urgent", "action", "fyi", "social", "spam"):
            label = "fyi"
        score = float(result.get("priority_score", 0.0))
        score = max(0.0, min(1.0, score))

        state.ai_enrichment.priority_label = label
        state.ai_enrichment.priority_score = score
        state.ai_enrichment.time_sensitive = result.get("time_sensitive", False)
        state.ai_enrichment.classification_reasoning = result.get("reasoning", "")

        # Sentiment
        sentiment = result.get("sentiment", "neutral")
        if sentiment not in ("positive", "neutral", "tense", "urgent", "distressed"):
            sentiment = "neutral"
        state.ai_enrichment.sentiment = sentiment
        state.ai_enrichment.is_complaint = result.get("is_complaint", False)
        state.ai_enrichment.needs_careful_response = result.get("needs_careful_response", False)
        state.ai_enrichment.suggested_approach = result.get("suggested_approach", "")

        # Context note
        context = result.get("context_summary", "")
        reasoning = result.get("reasoning", "")
        if context and reasoning:
            state.ai_enrichment.context_note = f"{context} | {reasoning}"
        elif context or reasoning:
            state.ai_enrichment.context_note = context or reasoning

        logger.info(
            f"Enriched message {state.id}: label={label} score={score:.2f} "
            f"sentiment={sentiment} relationship={state.sender.relationship}"
        )

    except anthropic.APIError as e:
        logger.warning(f"Anthropic API error in enrichment: {e}")
        _fallback_enrich(state, interaction_history, reply_count, total_messages)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse enrichment response: {e}")
        _fallback_enrich(state, interaction_history, reply_count, total_messages)
    except Exception as e:
        logger.error(f"Unexpected error in enrichment: {e}")
        _fallback_enrich(state, interaction_history, reply_count, total_messages)

    return state


def _fallback_enrich(
    state: MessageState,
    interaction_history: Optional[list[str]],
    reply_count: int,
    total_messages: int,
) -> None:
    """Combined rule-based fallback for all three enrichment signals."""
    content_lower = state.content_text.lower()

    # --- Sender relationship ---
    email = state.sender.email or ""
    if any(kw in email.lower() for kw in ["noreply", "no-reply", "notifications", "mailer"]):
        state.sender.relationship = "bot"
    elif total_messages > 10:
        reply_rate = reply_count / total_messages if total_messages else 0.0
        state.sender.historical_reply_rate = reply_rate
        state.sender.relationship = "close_contact" if reply_rate > 0.5 else "work_contact"
    else:
        state.sender.relationship = "stranger"

    # --- Classification ---
    urgent_keywords = ["asap", "urgent", "deadline", "today", "help", "immediately",
                       "critical", "emergency", "important", "call me"]
    spam_keywords = ["unsubscribe", "click here", "limited time", "offer", "deal"]

    score = 0.0
    relationship_scores = {
        "vip": 0.30, "close_contact": 0.24, "work_contact": 0.18,
        "acquaintance": 0.12, "stranger": 0.06, "bot": 0.02, "newsletter": 0.01,
    }
    score += relationship_scores.get(state.sender.relationship, 0.06)

    keyword_hits = sum(1 for kw in urgent_keywords if kw in content_lower)
    score += min(0.20, keyword_hits * 0.05)
    score += state.sender.historical_reply_rate * 0.15
    if state.sender.is_vip:
        score += 0.15
    score = max(0.0, min(1.0, score))

    if score >= 0.85:
        label = "urgent"
    elif score >= 0.60:
        label = "action"
    elif score >= 0.30:
        label = "fyi"
    elif any(kw in content_lower for kw in spam_keywords):
        label = "spam"
        score = min(score, 0.15)
    else:
        label = "social"

    state.ai_enrichment.priority_label = label
    state.ai_enrichment.priority_score = round(score, 3)
    state.ai_enrichment.classification_reasoning = "Rule-based fallback"

    # --- Sentiment ---
    distressed_kw = ["please help", "emergency", "crisis", "desperate", "struggling"]
    urgent_kw = ["asap", "immediately", "right now", "can't wait"]
    tense_kw = ["disappointed", "frustrated", "unacceptable", "complaint", "angry"]
    positive_kw = ["thank you", "thanks", "great", "awesome", "appreciate", "excellent"]

    if any(kw in content_lower for kw in distressed_kw):
        state.ai_enrichment.sentiment = "distressed"
        state.ai_enrichment.needs_careful_response = True
        state.ai_enrichment.suggested_approach = "Respond with empathy and offer concrete help"
    elif any(kw in content_lower for kw in urgent_kw):
        state.ai_enrichment.sentiment = "urgent"
        state.ai_enrichment.needs_careful_response = True
        state.ai_enrichment.suggested_approach = "Respond quickly and directly"
    elif any(kw in content_lower for kw in tense_kw):
        state.ai_enrichment.sentiment = "tense"
        state.ai_enrichment.is_complaint = True
        state.ai_enrichment.needs_careful_response = True
        state.ai_enrichment.suggested_approach = "Acknowledge their concern before addressing the issue"
    elif any(kw in content_lower for kw in positive_kw):
        state.ai_enrichment.sentiment = "positive"
    else:
        state.ai_enrichment.sentiment = "neutral"

    state.ai_enrichment.context_note = "Enriched using rule-based fallback (AI unavailable)"
