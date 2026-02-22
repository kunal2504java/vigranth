"""
Redis Pub/Sub bridge for cross-process WebSocket notifications.

Problem: Celery workers run in separate processes and cannot access the
FastAPI process's in-memory WebSocket connections directly.

Solution: Workers publish events to Redis Pub/Sub channels.
The FastAPI process subscribes and relays events to WebSocket clients.

Channels:
  ws:user:{user_id}  — events targeted at a specific user
  ws:broadcast        — events for all connected users
"""
import json
import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Separate connection for pub/sub (can't reuse pooled connection)
_pub_client: Optional[aioredis.Redis] = None
_sub_client: Optional[aioredis.Redis] = None


async def get_pub_client() -> aioredis.Redis:
    global _pub_client
    if _pub_client is None:
        _pub_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pub_client


async def get_sub_client() -> aioredis.Redis:
    global _sub_client
    if _sub_client is None:
        _sub_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _sub_client


async def publish_to_user(user_id: str, event: str, data: dict):
    """
    Publish a WebSocket event for a specific user via Redis Pub/Sub.
    Called from Celery workers or any non-FastAPI process.
    """
    try:
        client = await get_pub_client()
        message = json.dumps({"event": event, "data": data})
        await client.publish(f"ws:user:{user_id}", message)
        logger.debug(f"Published {event} to ws:user:{user_id}")
    except Exception as e:
        logger.warning(f"Failed to publish to user {user_id}: {e}")


async def publish_broadcast(event: str, data: dict):
    """Publish a broadcast event to all connected users."""
    try:
        client = await get_pub_client()
        message = json.dumps({"event": event, "data": data})
        await client.publish("ws:broadcast", message)
    except Exception as e:
        logger.warning(f"Failed to publish broadcast: {e}")


async def start_subscriber(ws_manager):
    """
    Start a Redis Pub/Sub subscriber that relays events to WebSocket clients.
    Called during FastAPI startup. Runs as a background task.
    """
    try:
        client = await get_sub_client()
        pubsub = client.pubsub()

        # Subscribe to broadcast channel
        await pubsub.subscribe("ws:broadcast")
        logger.info("Redis Pub/Sub subscriber started (broadcast channel)")

        # Subscribe to user-specific channels dynamically
        # We'll use pattern-based subscription
        await pubsub.psubscribe("ws:user:*")
        logger.info("Redis Pub/Sub subscriber started (user channels)")

        async for message in pubsub.listen():
            if message["type"] in ("message", "pmessage"):
                try:
                    data = json.loads(message["data"])
                    event = data.get("event", "")
                    event_data = data.get("data", {})

                    if message["type"] == "pmessage":
                        # Pattern match: extract user_id from channel name
                        channel = message.get("channel", "")
                        if channel.startswith("ws:user:"):
                            user_id = channel.replace("ws:user:", "")
                            await ws_manager.push_to_user(user_id, event, event_data)
                    elif message["type"] == "message":
                        # Broadcast
                        await ws_manager.broadcast(event, event_data)

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Invalid pub/sub message: {e}")

    except asyncio.CancelledError:
        logger.info("Redis Pub/Sub subscriber shutting down")
    except Exception as e:
        logger.error(f"Redis Pub/Sub subscriber error: {e}")


async def close_pubsub():
    """Clean up pub/sub connections."""
    global _pub_client, _sub_client
    if _pub_client:
        await _pub_client.close()
    if _sub_client:
        await _sub_client.close()
