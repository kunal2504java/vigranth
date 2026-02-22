"""
Auth API — user registration, login, token refresh, and OAuth callbacks.

Endpoints:
  POST /auth/register       — create account
  POST /auth/login          — get JWT tokens
  POST /auth/refresh        — refresh access token
  GET  /auth/{platform}/connect   — redirect to platform OAuth
  GET  /auth/{platform}/callback  — handle OAuth callback
"""
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.config import get_settings
from backend.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    encrypt_token,
    get_current_user_id,
)
from backend.agents.state import UserCreate, UserLogin, TokenResponse, UserResponse
from backend.models.database import User, PlatformCredential

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Registration & Login ---

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Check existing
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        name=payload.name or payload.email.split("@")[0],
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_EXPIRY_HOURS * 3600,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_EXPIRY_HOURS * 3600,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, db: AsyncSession = Depends(get_db)):
    """Refresh an access token using a refresh token."""
    body = await request.json()
    token = body.get("refresh_token")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token required")

    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Not a refresh token")

    user_id = payload.get("sub")

    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate: issue new access + refresh tokens
    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    new_refresh = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.JWT_EXPIRY_HOURS * 3600,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


# --- Gmail OAuth ---

@router.get("/gmail/connect")
async def gmail_connect(user_id: str = Depends(get_current_user_id)):
    """Redirect user to Google OAuth consent screen."""
    scopes = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify"
    oauth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={settings.GMAIL_CLIENT_ID}"
        f"&redirect_uri={settings.GMAIL_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={user_id}"
    )
    return RedirectResponse(url=oauth_url)


@router.get("/gmail/callback")
async def gmail_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback, exchange code for tokens."""
    user_id = state

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "redirect_uri": settings.GMAIL_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange code for tokens")

    tokens = response.json()

    # Store encrypted tokens
    result = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == "gmail",
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = encrypt_token(tokens["access_token"])
        existing.refresh_token = encrypt_token(tokens.get("refresh_token", ""))
        existing.token_expiry = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        cred = PlatformCredential(
            user_id=user_id,
            platform="gmail",
            access_token=encrypt_token(tokens["access_token"]),
            refresh_token=encrypt_token(tokens.get("refresh_token", "")),
            token_expiry=datetime.now(timezone.utc),
            scopes="gmail.readonly,gmail.send,gmail.modify",
        )
        db.add(cred)

    await db.flush()

    # Redirect to frontend success page
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/connect?platform=gmail&status=success")


# --- Slack OAuth ---

@router.get("/slack/connect")
async def slack_connect(user_id: str = Depends(get_current_user_id)):
    """Redirect user to Slack OAuth."""
    scopes = "channels:history,im:history,chat:write,users:read"
    oauth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.SLACK_REDIRECT_URI}"
        f"&state={user_id}"
    )
    return RedirectResponse(url=oauth_url)


@router.get("/slack/callback")
async def slack_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Slack OAuth callback."""
    user_id = state

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "code": code,
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "redirect_uri": settings.SLACK_REDIRECT_URI,
            },
        )

    data = response.json()
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {data.get('error')}")

    access_token = data.get("access_token", "")
    team_id = data.get("team", {}).get("id", "")

    result = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == "slack",
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = encrypt_token(access_token)
        existing.platform_user_id = team_id
        existing.updated_at = datetime.now(timezone.utc)
    else:
        cred = PlatformCredential(
            user_id=user_id,
            platform="slack",
            access_token=encrypt_token(access_token),
            platform_user_id=team_id,
            scopes="channels:history,im:history,chat:write,users:read",
        )
        db.add(cred)

    await db.flush()
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/connect?platform=slack&status=success")


# --- Discord OAuth ---

@router.get("/discord/connect")
async def discord_connect(user_id: str = Depends(get_current_user_id)):
    """Redirect user to Discord OAuth."""
    scopes = "bot identify messages.read"
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={settings.DISCORD_CLIENT_ID}"
        f"&redirect_uri={settings.DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={user_id}"
    )
    return RedirectResponse(url=oauth_url)


@router.get("/discord/callback")
async def discord_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Discord OAuth callback."""
    user_id = state

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://discord.com/api/oauth2/token",
            data={
                "code": code,
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "redirect_uri": settings.DISCORD_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Discord OAuth failed")

    tokens = response.json()

    result = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.user_id == user_id,
            PlatformCredential.platform == "discord",
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = encrypt_token(tokens["access_token"])
        existing.refresh_token = encrypt_token(tokens.get("refresh_token", ""))
        existing.updated_at = datetime.now(timezone.utc)
    else:
        cred = PlatformCredential(
            user_id=user_id,
            platform="discord",
            access_token=encrypt_token(tokens["access_token"]),
            refresh_token=encrypt_token(tokens.get("refresh_token", "")),
            scopes="bot,identify,messages.read",
        )
        db.add(cred)

    await db.flush()
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/connect?platform=discord&status=success")
