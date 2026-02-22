"""
Webhook endpoints for receiving realtime events from platforms.

Each platform pushes events to these endpoints:
  POST /webhooks/gmail     — Gmail Pub/Sub push notifications
  POST /webhooks/slack     — Slack Events API
  POST /webhooks/telegram/{user_id} — Telegram Bot API
"""
import base64
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request, HTTPException

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/gmail")
async def gmail_webhook(request: Request):
    """
    Handle Gmail push notifications via Pub/Sub.
    Triggered when new mail arrives in user's inbox.
    """
    try:
        data = await request.json()
        encoded = data.get("message", {}).get("data", "")
        if not encoded:
            return {"ok": True}

        payload = json.loads(base64.b64decode(encoded))
        user_email = payload.get("emailAddress", "")
        history_id = payload.get("historyId", "")

        logger.info(f"Gmail webhook: email={user_email}, historyId={history_id}")

        # Trigger async sync task
        from backend.tasks.sync import sync_platform_for_user
        sync_platform_for_user.delay(
            user_email=user_email,
            platform="gmail",
            history_id=history_id,
        )

        return {"ok": True}

    except Exception as e:
        logger.error(f"Gmail webhook error: {e}")
        return {"ok": True}  # Always return 200 to prevent retries


@router.post("/slack")
async def slack_webhook(request: Request):
    """
    Handle Slack Events API.
    Supports URL verification challenge and message events.
    """
    body = await request.json()

    # URL verification (one-time setup)
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    # Validate Slack request signature
    if not await _verify_slack_signature(request):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    event = body.get("event", {})

    # Skip bot messages
    if event.get("bot_id"):
        return {"ok": True}

    if event.get("type") in ("message", "app_mention"):
        # Skip message subtypes (edits, deletes, etc.) except thread replies
        subtype = event.get("subtype")
        if subtype and subtype not in ("thread_broadcast",):
            return {"ok": True}

        logger.info(
            f"Slack webhook: channel={event.get('channel')}, "
            f"user={event.get('user')}, ts={event.get('ts')}"
        )

        # Trigger async processing
        from backend.tasks.sync import process_webhook_message
        process_webhook_message.delay(
            platform="slack",
            raw_data={
                "user": event.get("user", ""),
                "channel": event.get("channel", ""),
                "text": event.get("text", ""),
                "ts": event.get("ts", ""),
                "thread_ts": event.get("thread_ts"),
                "team": body.get("team_id", ""),
            },
        )

    return {"ok": True}


@router.post("/telegram/{user_id}")
async def telegram_webhook(user_id: str, request: Request):
    """
    Handle Telegram Bot API webhook updates.
    Each user has their own webhook URL for message delivery.
    """
    try:
        update = await request.json()
        message = update.get("message") or update.get("edited_message")

        if not message:
            return {"ok": True}

        # Skip non-text messages for now
        if not message.get("text"):
            return {"ok": True}

        logger.info(
            f"Telegram webhook: user_id={user_id}, "
            f"chat_id={message.get('chat', {}).get('id')}, "
            f"from={message.get('from', {}).get('username')}"
        )

        from backend.tasks.sync import process_webhook_message
        process_webhook_message.delay(
            platform="telegram",
            raw_data={
                "user_id": user_id,
                "from": message.get("from", {}),
                "chat": message.get("chat", {}),
                "text": message.get("text", ""),
                "date": message.get("date", 0),
                "message_id": message.get("message_id", 0),
            },
        )

        return {"ok": True}

    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"ok": True}


# --- Helpers ---

async def _verify_slack_signature(request: Request) -> bool:
    """
    Verify Slack request signature using HMAC-SHA256.
    Returns True if valid, False otherwise.
    """
    try:
        signing_secret = settings.SLACK_CLIENT_SECRET
        if not signing_secret:
            logger.warning("Slack signing secret not configured, skipping verification")
            return True

        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")

        body = await request.body()
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"

        expected = "v0=" + hmac.HMAC(
            signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    except Exception as e:
        logger.warning(f"Slack signature verification failed: {e}")
        return False
