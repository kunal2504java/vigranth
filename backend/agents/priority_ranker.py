"""
Priority Ranker Agent — computes the final priority score.

This agent runs AFTER Context Builder, Classifier, and Sentiment agents.
It combines all signals with the weighted formula from PRD Section 6.2:

  Signal                   | Weight
  Sender Relationship      | 30%
  Explicit Urgency Keywords| 20%
  Time Sensitivity         | 15%
  Historical Response Rate | 15%
  Thread Activity          | 10%
  Sentiment Intensity      | 10%

This is a deterministic agent (no LLM call) — it applies the weighted
scoring formula to the enrichments already on the MessageState.
"""
import logging
from datetime import datetime, timezone

from backend.agents.state import MessageState

logger = logging.getLogger(__name__)

# Weight configuration
WEIGHTS = {
    "sender_relationship": 0.30,
    "urgency_keywords": 0.20,
    "time_sensitivity": 0.15,
    "historical_response_rate": 0.15,
    "thread_activity": 0.10,
    "sentiment_intensity": 0.10,
}

# Relationship tier scores (normalized 0-1)
RELATIONSHIP_SCORES = {
    "vip": 1.0,
    "close_contact": 0.8,
    "work_contact": 0.65,
    "acquaintance": 0.4,
    "stranger": 0.2,
    "bot": 0.05,
    "newsletter": 0.02,
}

# Sentiment intensity scores
SENTIMENT_SCORES = {
    "distressed": 1.0,
    "urgent": 0.9,
    "tense": 0.7,
    "neutral": 0.3,
    "positive": 0.2,
}

# Urgency keywords
URGENCY_KEYWORDS = [
    "asap", "urgent", "deadline", "today", "help", "call me",
    "immediately", "critical", "emergency", "important", "breaking",
    "time-sensitive", "overdue", "expires", "final notice",
]


async def compute_priority(
    state: MessageState,
    thread_message_count: int = 1,
    thread_recent_replies: int = 0,
) -> MessageState:
    """
    Compute the final weighted priority score.
    This runs after all other enrichment agents have populated the state.
    """
    scores = {}

    # 1. Sender Relationship (30%)
    relationship = state.sender.relationship
    scores["sender_relationship"] = RELATIONSHIP_SCORES.get(relationship, 0.2)

    # 2. Explicit Urgency Keywords (20%)
    content_lower = state.content_text.lower()
    keyword_hits = sum(1 for kw in URGENCY_KEYWORDS if kw in content_lower)
    scores["urgency_keywords"] = min(1.0, keyword_hits * 0.25)

    # 3. Time Sensitivity (15%) — decay based on message age
    scores["time_sensitivity"] = _compute_time_decay(state.timestamp)

    # 4. Historical Response Rate (15%)
    scores["historical_response_rate"] = state.sender.historical_reply_rate

    # 5. Thread Activity (10%)
    if thread_message_count > 1:
        # More active threads score higher
        activity = min(1.0, (thread_recent_replies / max(thread_message_count, 1)))
        scores["thread_activity"] = max(0.3, activity)
    else:
        scores["thread_activity"] = 0.1

    # 6. Sentiment Intensity (10%)
    sentiment = state.ai_enrichment.sentiment
    scores["sentiment_intensity"] = SENTIMENT_SCORES.get(sentiment, 0.3)

    # Compute weighted sum
    final_score = sum(
        scores[signal] * WEIGHTS[signal]
        for signal in WEIGHTS
    )

    # VIP override: ensure VIP messages never fall below 0.60
    if state.sender.is_vip:
        final_score = max(final_score, 0.60)

    # Clamp to [0.0, 1.0]
    final_score = round(max(0.0, min(1.0, final_score)), 3)

    # Determine final label based on score thresholds from PRD Section 6.3
    if final_score >= 0.85:
        label = "urgent"
    elif final_score >= 0.60:
        label = "action"
    elif final_score >= 0.30:
        label = "fyi"
    else:
        # Preserve spam/social labels if classifier set them
        if state.ai_enrichment.priority_label in ("spam", "social"):
            label = state.ai_enrichment.priority_label
        else:
            label = "social"

    # Update state
    state.ai_enrichment.priority_score = final_score
    state.ai_enrichment.priority_label = label

    logger.info(
        f"Priority ranked message {state.id}: score={final_score}, label={label} "
        f"(signals: {scores})"
    )

    return state


def _compute_time_decay(timestamp_str: str) -> float:
    """
    Messages older than 24hrs decay in score.
    Fresh messages (< 1hr) get full score, then linear decay to 0 at 48hrs.
    """
    try:
        if "T" in timestamp_str:
            msg_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            msg_time = datetime.fromisoformat(timestamp_str)

        if msg_time.tzinfo is None:
            msg_time = msg_time.replace(tzinfo=timezone.utc)

        age_hours = (datetime.now(timezone.utc) - msg_time).total_seconds() / 3600

        if age_hours < 1:
            return 1.0
        elif age_hours < 24:
            return 1.0 - (age_hours / 48)
        elif age_hours < 48:
            return max(0.1, 1.0 - (age_hours / 48))
        else:
            return 0.05
    except (ValueError, TypeError):
        return 0.5  # default if timestamp parsing fails
