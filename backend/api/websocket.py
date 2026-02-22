"""
WebSocket manager for live feed updates.

From Architecture doc Section 5.5:
  WS /ws/feed?token={jwt_token}

  Server -> Client events:
    new_message      — new message arrived and processed
    priority_updated — priority score changed (e.g., from decay)
    sync_status      — platform sync status (syncing|done|error)

  Client -> Server events:
    mark_read        — mark a message as read
    snooze           — snooze a message until a given time
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from backend.core.security import decode_token
from backend.core.database import get_db_context
from backend.models.database import Message

logger = logging.getLogger(__name__)

router = APIRouter()


class WebSocketManager:
    """
    Manages active WebSocket connections per user.
    Supports pushing events to specific users or broadcasting.
    """

    def __init__(self):
        # user_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info(f"WebSocket connected for user {user_id} (total: {len(self._connections[user_id])})")

    def disconnect(self, user_id: str, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws != websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info(f"WebSocket disconnected for user {user_id}")

    async def push_to_user(self, user_id: str, event: str, data: dict):
        """Push an event to all connections for a specific user."""
        if user_id not in self._connections:
            return

        message = json.dumps({"event": event, "data": data})
        dead_connections = []

        for ws in self._connections[user_id]:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(user_id, ws)

    async def broadcast(self, event: str, data: dict):
        """Broadcast an event to all connected users."""
        message = json.dumps({"event": event, "data": data})
        for user_id, connections in list(self._connections.items()):
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    self.disconnect(user_id, ws)

    def get_connected_users(self) -> list[str]:
        """Return list of user IDs with active connections."""
        return list(self._connections.keys())

    def get_connection_count(self, user_id: str) -> int:
        """Return number of active connections for a user."""
        return len(self._connections.get(user_id, []))


# Singleton instance
ws_manager = WebSocketManager()


@router.websocket("/ws/feed")
async def feed_websocket(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint for live feed updates.
    Authenticated via JWT token in query parameter.
    """
    # Validate token
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # Connect
    await ws_manager.connect(user_id, websocket)

    try:
        # Listen for client events
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                event = data.get("event")

                if event == "mark_read":
                    await _handle_mark_read(user_id, data.get("message_id"))

                elif event == "snooze":
                    await _handle_snooze(
                        user_id,
                        data.get("message_id"),
                        data.get("until"),
                    )

                elif event == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"event": "error", "data": {"message": "Invalid JSON"}})
                )

    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        ws_manager.disconnect(user_id, websocket)


async def _handle_mark_read(user_id: str, message_id: Optional[str]):
    """Handle mark_read event from client."""
    if not message_id:
        return

    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(Message).where(
                    Message.id == message_id,
                    Message.user_id == user_id,
                )
            )
            message = result.scalar_one_or_none()
            if message:
                message.is_read = True
                await db.flush()
    except Exception as e:
        logger.error(f"Failed to mark message read: {e}")


async def _handle_snooze(user_id: str, message_id: Optional[str], until: Optional[str]):
    """Handle snooze event from client."""
    if not message_id or not until:
        return

    try:
        snooze_time = datetime.fromisoformat(until.replace("Z", "+00:00"))
        if snooze_time.tzinfo is None:
            snooze_time = snooze_time.replace(tzinfo=timezone.utc)

        async with get_db_context() as db:
            result = await db.execute(
                select(Message).where(
                    Message.id == message_id,
                    Message.user_id == user_id,
                )
            )
            message = result.scalar_one_or_none()
            if message:
                message.snoozed_until = snooze_time
                await db.flush()
    except Exception as e:
        logger.error(f"Failed to snooze message: {e}")
