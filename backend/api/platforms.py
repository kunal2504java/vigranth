"""
Platform Management API — connect, disconnect, and view platform status.

Endpoints (from Architecture doc Section 5.4):
  GET    /api/v1/platforms                    — list all platforms and status
  POST   /api/v1/platforms/{platform}/connect — connect via auth code
  DELETE /api/v1/platforms/{platform}          — disconnect platform
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user_id
from backend.agents.state import PlatformStatus, ConnectRequest, ConnectResponse
from backend.adapters.registry import get_supported_platforms
from backend.models.database import PlatformCredential, SyncState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/platforms", tags=["platforms"])


@router.get("", response_model=list[PlatformStatus])
async def list_platforms(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all supported platforms with connection status."""
    # Get user's connected platforms
    result = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
        )
    )
    connected = {cred.platform: cred for cred in result.scalars().all()}

    # Get sync states
    sync_result = await db.execute(
        select(SyncState).where(SyncState.user_id == user_id)
    )
    sync_states = {s.platform: s for s in sync_result.scalars().all()}

    platforms = []
    for platform in get_supported_platforms():
        cred = connected.get(platform)
        sync = sync_states.get(platform)

        platforms.append(PlatformStatus(
            platform=platform,
            connected=cred is not None,
            last_sync=sync.last_sync_at.isoformat() if sync and sync.last_sync_at else None,
            platform_user_id=cred.platform_user_id if cred else None,
        ))

    return platforms


@router.post("/{platform}/connect", response_model=ConnectResponse)
async def connect_platform(
    platform: str,
    payload: ConnectRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Connect a platform using an authorization code.
    The actual OAuth flow happens in the auth endpoints;
    this endpoint handles direct code exchange for platforms
    that support it (e.g., Telegram bot token).
    """
    supported = get_supported_platforms()
    if platform not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform. Supported: {supported}",
        )

    # For Telegram, the auth_code is the bot token
    if platform == "telegram":
        from backend.core.security import encrypt_token
        result = await db.execute(
            select(PlatformCredential).where(
                PlatformCredential.user_id == user_id,
                PlatformCredential.platform == "telegram",
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_token = encrypt_token(payload.auth_code)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            cred = PlatformCredential(
                user_id=user_id,
                platform="telegram",
                access_token=encrypt_token(payload.auth_code),
            )
            db.add(cred)

        await db.flush()
        return ConnectResponse(success=True, platform_user_id="telegram-bot")

    # For other platforms, redirect to OAuth flow
    raise HTTPException(
        status_code=400,
        detail=f"Use /auth/{platform}/connect for OAuth-based platforms",
    )


@router.delete("/{platform}")
async def disconnect_platform(
    platform: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a platform and remove stored credentials."""
    result = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == platform,
        )
    )
    cred = result.scalar_one_or_none()

    if not cred:
        raise HTTPException(status_code=404, detail=f"Platform {platform} is not connected")

    await db.delete(cred)

    # Also clean up sync state
    sync_result = await db.execute(
        select(SyncState).where(
            SyncState.user_id == user_id,
            SyncState.platform == platform,
        )
    )
    sync = sync_result.scalar_one_or_none()
    if sync:
        await db.delete(sync)

    await db.flush()

    logger.info(f"User {user_id} disconnected {platform}")
    return {"success": True}
