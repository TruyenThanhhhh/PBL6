import hashlib
import hmac
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse

from app.config import APP_SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
from app.database import get_db_connection

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)
oauth = OAuth()
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

PASSWORD_ITERATIONS = 310_000
TOKEN_LIFETIME = timedelta(hours=12)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        iterations, salt_hex, digest_hex = stored.split("$", 2)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _public_user(row) -> Dict[str, str]:
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def _ensure_workspace(conn, user_id: str) -> str:
    row = conn.execute("SELECT id FROM workspaces WHERE owner_user_id = ? ORDER BY created_at LIMIT 1",
                       (user_id,)).fetchone()
    if row:
        return row["id"]
    # Preserve the pre-auth prototype's local documents for the first account only.
    conn.execute("UPDATE workspaces SET owner_user_id = ? WHERE id = 'default' AND owner_user_id IS NULL",
                 (user_id,))
    row = conn.execute("SELECT id FROM workspaces WHERE owner_user_id = ? ORDER BY created_at LIMIT 1",
                       (user_id,)).fetchone()
    if row:
        return row["id"]
    workspace_id = str(uuid.uuid4())
    conn.execute("INSERT INTO workspaces (id, name, description, owner_user_id) VALUES (?, ?, ?, ?)",
                 (workspace_id, "Kho tri thức của tôi", "Workspace cá nhân", user_id))
    return workspace_id


def _issue_session(row) -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        workspace_id = _ensure_workspace(conn, row["id"])
        conn.commit()
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": row["id"], "iat": now, "exp": now + TOKEN_LIFETIME},
                       APP_SECRET_KEY, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "user": _public_user(row),
            "workspace_id": workspace_id}


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Vui lòng đăng nhập")
    token = authorization[7:].strip()
    try:
        payload = jwt.decode(token, APP_SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn") from exc
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Tài khoản không còn tồn tại")
    return dict(user)


@router.post("/register", status_code=201)
def register(req: Credentials):
    email = req.email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(status_code=422, detail="Email không hợp lệ")
    user_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (id, email, name, password_hash) VALUES (?, ?, ?, ?)",
                     (user_id, email, email.split("@", 1)[0], _hash_password(req.password)))
        _ensure_workspace(conn, user_id)
        conn.commit()
        row = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception as exc:
        conn.rollback()
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Email này đã được đăng ký") from exc
        raise
    finally:
        conn.close()
    return _issue_session(row)


@router.post("/login")
def login(req: Credentials):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (req.email.strip(),)).fetchone()
    finally:
        conn.close()
    if not row or not _verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác")
    return _issue_session(row)


@router.get("/me")
def me(user: Dict[str, str] = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        workspace_id = _ensure_workspace(conn, user["id"])
        conn.commit()
    finally:
        conn.close()
    return {"user": user, "workspace_id": workspace_id}


@router.get("/google")
async def google_login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Đăng nhập Google chưa được cấu hình")
    return await oauth.google.authorize_redirect(request, GOOGLE_REDIRECT_URI)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    stage = "đổi authorization code lấy token"
    try:
        token = await oauth.google.authorize_access_token(request)
        stage = "lấy hồ sơ Google"
        profile = token.get("userinfo") or await oauth.google.userinfo(token=token)
    except Exception as exc:
        # Avoid logging the callback URL or exception text: both can contain OAuth credentials.
        logger.error("Google OAuth thất bại ở bước %s (%s)", stage, type(exc).__name__)
        return RedirectResponse(url=f"{request.base_url}?auth_error=google_auth_failed", status_code=303)
    email = str(profile.get("email", "")).strip().lower()
    google_sub = str(profile.get("sub", ""))
    if not email or not google_sub or not profile.get("email_verified"):
        logger.warning("Google OAuth hoàn tất nhưng profile thiếu email/sub hoặc email chưa xác minh")
        return RedirectResponse(url=f"{request.base_url}?auth_error=google_profile_invalid", status_code=303)

    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE google_sub = ? OR email = ? COLLATE NOCASE",
                           (google_sub, email)).fetchone()
        if row:
            conn.execute("UPDATE users SET google_sub = ?, name = ? WHERE id = ?",
                         (google_sub, profile.get("name") or row["name"], row["id"]))
            user_id = row["id"]
        else:
            user_id = str(uuid.uuid4())
            conn.execute("INSERT INTO users (id, email, name, google_sub) VALUES (?, ?, ?, ?)",
                         (user_id, email, profile.get("name") or email.split("@", 1)[0], google_sub))
        _ensure_workspace(conn, user_id)
        conn.commit()
        row = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    session = _issue_session(row)
    return RedirectResponse(url=f"{request.base_url}#access_token={session['access_token']}")
