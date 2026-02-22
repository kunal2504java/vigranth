"""
Draft Reply Agent — generates platform-appropriate reply drafts.

Uses claude-sonnet for quality (this is user-facing content).
Tone profiles from PRD Section 6.4 and Integration Spec Section 2.4.

Key rules:
  - Match platform communication style
  - Address the actual question/request
  - Sound human (never "Certainly!" or "Of course!")
  - Return ONLY the reply text
"""
import logging
from typing import Optional

import anthropic

from backend.agents.state import MessageState
from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Tone profiles from Integration Spec Section 2.4
TONE_PROFILES = {
    "gmail": "Professional email. Proper greeting with name. Full sentences. Formal sign-off. Max 150 words.",
    "slack": "Slack. No greeting. Under 3 sentences. Casual-professional. Emoji ok if appropriate.",
    "telegram": "Telegram. Short and direct. Warm if known, neutral if stranger. 1-3 sentences.",
    "discord": "Discord. Community casual. 1-2 sentences. Use @name if channel reply.",
    "whatsapp": "WhatsApp. Personal and warm. Short sentences. Natural spoken language. 1-3 sentences.",
}

SYSTEM_PROMPT = """
You draft messages on behalf of users across communication platforms.

Rules:
1. Match the platform's communication style exactly
2. Address the actual question/request — not a generic reply
3. Sound human — never start with "Certainly!" or "Of course!"
4. Return ONLY the reply text, nothing else
"""

USER_PROMPT = """
PLATFORM: {platform}
TONE: {tone}
SENDER: {sender_name} ({relationship})
SENTIMENT: {sentiment}
{careful_note}

THREAD (newest last):
{thread_history}

MESSAGE TO REPLY:
{message}
"""


async def generate_draft(
    state: MessageState,
    thread_context: Optional[list[str]] = None,
) -> str:
    """
    Generate an AI draft reply using Claude Sonnet.
    Returns the draft text, or a fallback message on failure.
    """
    try:
        platform = state.platform if isinstance(state.platform, str) else state.platform.value
        tone = TONE_PROFILES.get(platform, TONE_PROFILES["gmail"])

        # Build careful note for tense/distressed messages
        careful_note = ""
        if state.ai_enrichment.sentiment in ("tense", "distressed"):
            careful_note = (
                "NOTE: This message has a tense/distressed tone. "
                "Be empathetic and careful. "
            )
            if state.ai_enrichment.suggested_approach:
                careful_note += f"Suggested approach: {state.ai_enrichment.suggested_approach}"

        # Build thread history
        thread_text = "No prior messages in thread."
        if thread_context:
            thread_text = "\n".join(thread_context[-5:])  # last 5 messages

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_PROMPT.format(
                    platform=platform,
                    tone=tone,
                    sender_name=state.sender.name,
                    relationship=state.sender.relationship,
                    sentiment=state.ai_enrichment.sentiment,
                    careful_note=careful_note,
                    thread_history=thread_text,
                    message=state.content_text[:3000],
                ),
            }],
        )

        draft = response.content[0].text.strip()
        logger.info(f"Draft generated for message {state.id} ({platform}): {len(draft)} chars")
        return draft

    except anthropic.APIError as e:
        logger.error(f"Anthropic API error in draft reply agent: {e}")
        return _fallback_draft(state)
    except Exception as e:
        logger.error(f"Unexpected error in draft reply agent: {e}")
        return _fallback_draft(state)


def _fallback_draft(state: MessageState) -> str:
    """Generate a minimal placeholder draft when AI is unavailable."""
    platform = state.platform if isinstance(state.platform, str) else state.platform.value
    sender = state.sender.name

    templates = {
        "gmail": f"Hi {sender},\n\nThank you for your message. I'll review this and get back to you shortly.\n\nBest regards",
        "slack": f"Thanks for the heads up — let me look into this and get back to you.",
        "telegram": f"Got it, will follow up on this.",
        "discord": f"@{sender} noted, will check on this",
        "whatsapp": f"Hey {sender}, thanks for reaching out! Let me get back to you on this.",
    }

    return templates.get(platform, templates["gmail"])
