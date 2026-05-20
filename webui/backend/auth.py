"""webui/backend/auth.py — JWT authentication helpers and user store."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

USERS_FILE = Path(".agentsdk") / "users.json"

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    """Return the username from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        return username
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserInDB(BaseModel):
    username: str
    hashed_password: str
    created_at: datetime


# ---------------------------------------------------------------------------
# UserStore — JSON file backed
# ---------------------------------------------------------------------------

class UserStore:
    def _load(self) -> dict[str, dict]:
        if not USERS_FILE.exists():
            return {}
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        USERS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def add_user(self, username: str, password: str) -> UserInDB:
        data = self._load()
        if username in data:
            raise ValueError(f"Username '{username}' is already taken.")
        user = UserInDB(
            username=username,
            hashed_password=hash_password(password),
            created_at=datetime.now(timezone.utc),
        )
        data[username] = user.model_dump()
        self._save(data)
        return user

    def get_user(self, username: str) -> Optional[UserInDB]:
        data = self._load()
        raw = data.get(username)
        if raw is None:
            return None
        return UserInDB(**raw)

    def verify_login(self, username: str, password: str) -> bool:
        user = self.get_user(username)
        if user is None:
            return False
        return verify_password(password, user.hashed_password)


user_store = UserStore()

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    username = decode_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
