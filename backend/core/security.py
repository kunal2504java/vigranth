"""
Security utilities:
  - JWT token creation & validation
  - AES-256 encryption for OAuth tokens at rest
  - Password hashing (for future local accounts)
"""
import os
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.core.config import get_settings

settings = get_settings()

# --- Password hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- JWT ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=settings.JWT_EXPIRY_HOURS)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a longer-lived refresh token (7 days)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises on invalid/expired."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    """FastAPI dependency: extract user_id from the Bearer token."""
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    return user_id


# --- AES-256-GCM encryption for OAuth tokens at rest ---

def _get_aes_key() -> bytes:
    """Derive a 32-byte AES key from the config encryption key."""
    raw = settings.ENCRYPTION_KEY.encode("utf-8")
    return hashlib.sha256(raw).digest()


def encrypt_token(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM. Returns base64-encoded nonce+ciphertext."""
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Concatenate nonce + ciphertext, base64 encode
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_token(encrypted: str) -> str:
    """Decrypt an AES-256-GCM encrypted token."""
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted.encode("utf-8"))
    nonce = raw[:12]
    ciphertext = raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
