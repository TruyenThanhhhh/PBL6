import hashlib
import hmac
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import warnings
try:
    import authlib.deprecate
    warnings.simplefilter('ignore', authlib.deprecate.AuthlibDeprecationWarning)
except ImportError:
    pass

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.responses import RedirectResponse
from urllib.parse import urlsplit, urlunsplit

from app.config import (
    APP_SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    SESSION_HTTPS_ONLY,
)
from app.database import get_db_connection

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)
google_state_signer = URLSafeTimedSerializer(APP_SECRET_KEY, salt="pbl6-google-oauth-state")
GOOGLE_STATE_COOKIE = "pbl6_google_oauth_state"
GOOGLE_STATE_COOKIE_PATH = "/api/v1/auth/google/callback"
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
TOKEN_LIFETIME = timedelta(hours=24)
TOKEN_LIFETIME_REMEMBER = timedelta(days=7)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^[0-9+\-\s().]{7,20}$")

USER_SELECT_COLUMNS = (
    "id, email, first_name, last_name, name, phone, organization, "
    "role_title, avatar_url, created_at, last_login_at"
)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(default="", max_length=80, description="Tên gọi")
    last_name: str = Field(default="", max_length=80, description="Họ và tên đệm")
    name: Optional[str] = Field(default=None, max_length=160, description="Họ và tên đầy đủ")
    phone: str = Field(default="", max_length=30, description="Số điện thoại liên hệ")
    organization: str = Field(default="", max_length=160, description="Trường học / Cơ quan / Tổ chức")
    role_title: str = Field(default="", max_length=80, description="Vai trò (Sinh viên, Giảng viên, Kỹ sư...)")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = Field(default=True)


class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=80)
    last_name: Optional[str] = Field(default=None, max_length=80)
    name: Optional[str] = Field(default=None, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=30)
    organization: Optional[str] = Field(default=None, max_length=160)
    role_title: Optional[str] = Field(default=None, max_length=80)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


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


def _compose_names(
    first_name: str,
    last_name: str,
    explicit_name: Optional[str],
    fallback_email: str,
) -> tuple[str, str, str]:
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    en = (explicit_name or "").strip()

    if fn or ln:
        full_name = f"{ln} {fn}".strip()
        if not fn and ln:
            parts = ln.split()
            if len(parts) > 1:
                fn = parts[-1]
                ln = " ".join(parts[:-1])
        return fn, ln, full_name

    if en:
        parts = en.split()
        if len(parts) == 1:
            return parts[0], "", parts[0]
        return parts[-1], " ".join(parts[:-1]), en

    fallback = fallback_email.split("@", 1)[0]
    return fallback, "", fallback


def _public_user(row) -> Dict[str, Any]:
    keys = row.keys() if hasattr(row, "keys") else {}
    return {
        "id": row["id"],
        "email": row["email"],
        "first_name": (row["first_name"] if "first_name" in keys else "") or "",
        "last_name": (row["last_name"] if "last_name" in keys else "") or "",
        "name": row["name"] or "",
        "phone": (row["phone"] if "phone" in keys else "") or "",
        "organization": (row["organization"] if "organization" in keys else "") or "",
        "role_title": (row["role_title"] if "role_title" in keys else "") or "",
        "avatar_url": (row["avatar_url"] if "avatar_url" in keys else "") or "",
        "created_at": (row["created_at"] if "created_at" in keys else "") or "",
    }


def _ensure_workspace(conn, user_id: str) -> str:
    row = conn.execute(
        "SELECT id FROM workspaces WHERE owner_user_id = ? ORDER BY created_at LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        return row["id"]
    # Gán workspace 'default' cho tài khoản đầu tiên nếu chưa có chủ sở hữu
    conn.execute(
        "UPDATE workspaces SET owner_user_id = ? WHERE id = 'default' AND owner_user_id IS NULL",
        (user_id,),
    )
    row = conn.execute(
        "SELECT id FROM workspaces WHERE owner_user_id = ? ORDER BY created_at LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        return row["id"]
    workspace_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO workspaces (id, name, description, category, icon, owner_user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (workspace_id, "Kho tri thức của tôi", "Không gian làm việc và lưu trữ tài liệu cá nhân", "Chung", "folder", user_id),
    )
    conn.execute(
        "INSERT INTO user_activities (id, workspace_id, activity_type, message) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), workspace_id, "workspace", "Khởi tạo không gian làm việc cá nhân"),
    )
    return workspace_id


def _issue_session(row, remember_me: bool = True) -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        workspace_id = _ensure_workspace(conn, row["id"])
        conn.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    lifetime = TOKEN_LIFETIME_REMEMBER if remember_me else TOKEN_LIFETIME
    token = jwt.encode(
        {"sub": row["id"], "iat": now, "exp": now + lifetime},
        APP_SECRET_KEY,
        algorithm="HS256",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _public_user(row),
        "workspace_id": workspace_id,
    }


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
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
        user = conn.execute(
            f"SELECT {USER_SELECT_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Tài khoản không còn tồn tại")
    return _public_user(user)


def get_current_user_optional(authorization: Optional[str] = Header(default=None)) -> Optional[Dict[str, Any]]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    try:
        payload = jwt.decode(token, APP_SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except Exception:
        return None
    conn = get_db_connection()
    try:
        user = conn.execute(
            f"SELECT {USER_SELECT_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _public_user(user) if user else None
    except Exception:
        return None
    finally:
        conn.close()


@router.post("/register", status_code=201)
def register(req: RegisterRequest):
    email = req.email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(status_code=422, detail="Địa chỉ email không hợp lệ")
    phone = req.phone.strip()
    if phone and not PHONE_PATTERN.fullmatch(phone):
        raise HTTPException(status_code=422, detail="Số điện thoại không hợp lệ")

    first_name, last_name, full_name = _compose_names(
        req.first_name, req.last_name, req.name, email
    )
    organization = req.organization.strip()
    role_title = req.role_title.strip()

    user_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (
                id, email, first_name, last_name, name,
                phone, organization, role_title, password_hash, last_login_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                user_id,
                email,
                first_name,
                last_name,
                full_name,
                phone,
                organization,
                role_title,
                _hash_password(req.password),
            ),
        )
        _ensure_workspace(conn, user_id)
        conn.commit()
        row = conn.execute(
            f"SELECT {USER_SELECT_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    except Exception as exc:
        conn.rollback()
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Email này đã được đăng ký") from exc
        raise
    finally:
        conn.close()
    return _issue_session(row)


@router.post("/login")
def login(req: LoginRequest):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (req.email.strip(),),
        ).fetchone()
    finally:
        conn.close()
    if not row or not _verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác")
    return _issue_session(row, remember_me=req.remember_me)


@router.get("/me")
def me(user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        workspace_id = _ensure_workspace(conn, user["id"])
        conn.commit()
    finally:
        conn.close()
    return {"user": user, "workspace_id": workspace_id}


@router.patch("/profile")
def update_profile(req: ProfileUpdateRequest, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        current = conn.execute(
            f"SELECT {USER_SELECT_COLUMNS} FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        first_name = req.first_name.strip() if req.first_name is not None else (current["first_name"] or "")
        last_name = req.last_name.strip() if req.last_name is not None else (current["last_name"] or "")
        phone = req.phone.strip() if req.phone is not None else (current["phone"] or "")
        if phone and not PHONE_PATTERN.fullmatch(phone):
            raise HTTPException(status_code=422, detail="Số điện thoại không hợp lệ")
        organization = req.organization.strip() if req.organization is not None else (current["organization"] or "")
        role_title = req.role_title.strip() if req.role_title is not None else (current["role_title"] or "")
        avatar_url = req.avatar_url.strip() if req.avatar_url is not None else (current["avatar_url"] or "")

        if req.first_name is not None or req.last_name is not None or req.name is not None:
            first_name, last_name, full_name = _compose_names(
                first_name, last_name, req.name, current["email"]
            )
        else:
            full_name = current["name"]

        conn.execute(
            """
            UPDATE users
            SET first_name = ?, last_name = ?, name = ?, phone = ?,
                organization = ?, role_title = ?, avatar_url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (first_name, last_name, full_name, phone, organization, role_title, avatar_url, user["id"]),
        )
        conn.commit()
        updated = conn.execute(
            f"SELECT {USER_SELECT_COLUMNS} FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
    finally:
        conn.close()
    return {"user": _public_user(updated), "message": "Đã cập nhật thông tin tài khoản"}


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, user: Dict[str, Any] = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
        if row["password_hash"] and not _verify_password(req.current_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không chính xác")
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (_hash_password(req.new_password), user["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"message": "Đã đổi mật khẩu thành công"}


@router.get("/google")
async def google_login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Đăng nhập Google chưa được cấu hình")
    callback_parts = urlsplit(GOOGLE_REDIRECT_URI)
    current_parts = urlsplit(str(request.base_url))
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if (current_parts.hostname != callback_parts.hostname
            and current_parts.hostname in loopback_hosts
            and callback_parts.hostname in loopback_hosts):
        canonical_login = urlunsplit((
            callback_parts.scheme,
            callback_parts.netloc,
            request.url.path,
            request.url.query,
            "",
        ))
        return RedirectResponse(canonical_login, status_code=307)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    response = await oauth.google.authorize_redirect(
        request, GOOGLE_REDIRECT_URI, state=state, nonce=nonce
    )
    response.set_cookie(
        GOOGLE_STATE_COOKIE,
        google_state_signer.dumps({"state": state, "nonce": nonce}),
        max_age=600,
        httponly=True,
        secure=SESSION_HTTPS_ONLY,
        samesite="lax",
        path=GOOGLE_STATE_COOKIE_PATH,
    )
    return response


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    stage = "đổi authorization code lấy token"
    try:
        state = request.query_params.get("state", "")
        signed_flow = request.cookies.get(GOOGLE_STATE_COOKIE, "")
        try:
            flow_data = google_state_signer.loads(signed_flow, max_age=600)
        except (BadSignature, SignatureExpired) as exc:
            logger.error("Google OAuth thiếu cookie state hợp lệ (%s)", type(exc).__name__)
            response = RedirectResponse(url=f"{request.base_url}?auth_error=google_auth_failed", status_code=303)
            response.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_COOKIE_PATH)
            return response
        if not state or not secrets.compare_digest(state, str(flow_data.get("state", ""))):
            logger.error("Google OAuth state trên callback không khớp state cookie")
            response = RedirectResponse(url=f"{request.base_url}?auth_error=google_auth_failed", status_code=303)
            response.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_COOKIE_PATH)
            return response

        await oauth.google.framework.set_state_data(
            request.session, state,
            {"redirect_uri": GOOGLE_REDIRECT_URI, "nonce": flow_data["nonce"]},
        )
        token = await oauth.google.authorize_access_token(request)
        stage = "lấy hồ sơ Google"
        profile = token.get("userinfo") or await oauth.google.userinfo(token=token)
    except Exception as exc:
        logger.error("Google OAuth thất bại ở bước %s (%s)", stage, type(exc).__name__)
        response = RedirectResponse(url=f"{request.base_url}?auth_error=google_auth_failed", status_code=303)
        response.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_COOKIE_PATH)
        return response
    email = str(profile.get("email", "")).strip().lower()
    google_sub = str(profile.get("sub", ""))
    if not email or not google_sub or not profile.get("email_verified"):
        logger.warning("Google OAuth hoàn tất nhưng profile thiếu email/sub hoặc email chưa xác minh")
        response = RedirectResponse(url=f"{request.base_url}?auth_error=google_profile_invalid", status_code=303)
        response.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_COOKIE_PATH)
        return response

    given_name = str(profile.get("given_name") or "").strip()
    family_name = str(profile.get("family_name") or "").strip()
    picture = str(profile.get("picture") or "").strip()
    first_name, last_name, full_name = _compose_names(
        given_name, family_name, profile.get("name"), email
    )

    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE google_sub = ? OR email = ? COLLATE NOCASE",
            (google_sub, email),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users
                SET google_sub = ?,
                    first_name = COALESCE(NULLIF(first_name, ''), ?),
                    last_name = COALESCE(NULLIF(last_name, ''), ?),
                    name = ?,
                    avatar_url = COALESCE(NULLIF(avatar_url, ''), ?),
                    last_login_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (google_sub, first_name, last_name, full_name or row["name"], picture, row["id"]),
            )
            user_id = row["id"]
        else:
            user_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO users (
                    id, email, first_name, last_name, name, avatar_url, google_sub, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, email, first_name, last_name, full_name, picture, google_sub),
            )
        _ensure_workspace(conn, user_id)
        conn.commit()
        row = conn.execute(
            f"SELECT {USER_SELECT_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    session = _issue_session(row)
    response = RedirectResponse(url=f"{request.base_url}#access_token={session['access_token']}")
    response.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_COOKIE_PATH)
    return response
