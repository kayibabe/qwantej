"""User authentication and session endpoints."""

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.api.security import require_authenticated_user
from app.database import get_db
from app.models import AuthEvent, User, UserSession
from app.services.auth import (
    create_session,
    hash_password,
    normalize_email,
    session_token_hash,
    verify_password,
)
from app.services.auth_rate_limit import enforce_auth_rate_limit
from app.services.auth_tokens import (
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    consume_token,
    issue_token,
)
from app.services.email_delivery import (
    send_password_reset_email,
    send_verification_email,
)


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=6, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = normalize_email(value)
        if "@" not in value or value.startswith("@"):  # Keep dependency-free validation conservative.
            raise ValueError("A valid email address is required")
        return value


class RegisterCredentials(LoginCredentials):
    username: str = Field(min_length=2, max_length=80)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = normalize_email(value)
        if "@" not in value or value.startswith("@"):
            raise ValueError("A valid email address is required")
        return value


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=8, max_length=256)


class EmailVerificationConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    plan: str
    account_status: str
    email_verified: bool


class AuthResponse(BaseModel):
    user: UserOut | None


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        plan=user.plan,
        account_status=user.account_status,
        email_verified=user.email_verified_at is not None,
    )


def _cookie_kwargs() -> dict:
    return {
        "key": settings.auth_cookie_name,
        "httponly": True,
        "secure": settings.app_env == "production",
        "samesite": "lax",
        "max_age": settings.auth_session_days * 86400,
        "path": "/",
    }


def _recovery_link(request: Request, path: str, token: str) -> str:
    base = settings.public_app_base_url.strip().rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/{path}?token={quote(token)}"


async def _revoke_sessions(db: AsyncSession, user_id: int, now: datetime) -> None:
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    for session in result.scalars().all():
        session.revoked_at = now


async def _record_event(request: Request, db: AsyncSession, *, user_id: int | None, email: str, event_type: str, success: bool, failure_reason: str | None = None) -> None:
    db.add(
        AuthEvent(
            user_id=user_id,
            email_attempted=email,
            event_type=event_type,
            success=success,
            failure_reason=failure_reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterCredentials, request: Request, response: Response, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if not settings.auth_allow_registration:
        raise HTTPException(status_code=404, detail="Registration is disabled")
    await enforce_auth_rate_limit(request, "register", settings.auth_register_rate_limit)
    email = normalize_email(payload.email)
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        await _record_event(request, db, user_id=existing.id, email=email, event_type="register", success=False, failure_reason="email_exists")
        await db.commit()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(username=payload.username.strip(), email=email, password_hash=hash_password(payload.password), role="user", plan="free", account_status="active")
    db.add(user)
    await db.flush()
    token = await create_session(db, user)
    verification_token = await issue_token(
        db,
        user.id,
        PURPOSE_EMAIL_VERIFICATION,
        settings.email_verification_token_hours * 60,
    )
    await _record_event(request, db, user_id=user.id, email=email, event_type="register", success=True)
    await db.commit()
    response.set_cookie(value=token, **_cookie_kwargs())
    background_tasks.add_task(
        send_verification_email,
        user.email,
        _recovery_link(request, "verify-email", verification_token),
    )
    return AuthResponse(user=_user_out(user))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginCredentials, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await enforce_auth_rate_limit(request, "login", settings.auth_login_rate_limit)
    email = normalize_email(payload.email)
    user = await db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(user.password_hash, payload.password):
        await _record_event(request, db, user_id=user.id if user else None, email=email, event_type="login", success=False, failure_reason="invalid_credentials")
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.account_status != "active":
        await _record_event(request, db, user_id=user.id, email=email, event_type="login", success=False, failure_reason="account_inactive")
        await db.commit()
        raise HTTPException(status_code=403, detail="Account is not active")
    user.last_login_at = datetime.now(timezone.utc)
    token = await create_session(db, user)
    await _record_event(request, db, user_id=user.id, email=email, event_type="login", success=True)
    await db.commit()
    response.set_cookie(value=token, **_cookie_kwargs())
    return AuthResponse(user=_user_out(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        session = await db.scalar(select(UserSession).where(UserSession.token_hash == session_token_hash(token)))
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await enforce_auth_rate_limit(request, "password-reset", 5)
    email = normalize_email(payload.email)
    user = await db.scalar(
        select(User).where(User.email == email, User.account_status == "active")
    )
    token = None
    if user is not None:
        token = await issue_token(
            db, user.id, PURPOSE_PASSWORD_RESET, settings.password_reset_token_minutes
        )
        await _record_event(
            request, db, user_id=user.id, email=email,
            event_type="password_reset_requested", success=True,
        )
    else:
        await _record_event(
            request, db, user_id=None, email=email,
            event_type="password_reset_requested", success=False,
            failure_reason="unknown_email",
        )
    await db.commit()
    if user is not None and token is not None:
        background_tasks.add_task(
            send_password_reset_email,
            user.email,
            _recovery_link(request, "reset-password", token),
        )
    return {"status": "accepted"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await enforce_auth_rate_limit(request, "password-reset-confirm", 10)
    record = await consume_token(db, payload.token, PURPOSE_PASSWORD_RESET)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired",
        )
    user = await db.get(User, record.user_id)
    if user is None or user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired",
        )
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.password)
    if user.email_verified_at is None:
        user.email_verified_at = now
    await _revoke_sessions(db, user.id, now)
    await _record_event(
        request, db, user_id=user.id, email=user.email,
        event_type="password_reset", success=True,
    )
    await db.commit()
    return {"status": "password_updated"}


@router.post("/email-verification/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    await enforce_auth_rate_limit(request, "email-verification", 5)
    if user.email_verified_at is not None:
        return {"status": "already_verified"}
    token = await issue_token(
        db,
        user.id,
        PURPOSE_EMAIL_VERIFICATION,
        settings.email_verification_token_hours * 60,
    )
    await db.commit()
    background_tasks.add_task(
        send_verification_email,
        user.email,
        _recovery_link(request, "verify-email", token),
    )
    return {"status": "accepted"}


@router.post("/email-verification/confirm")
async def confirm_email_verification(
    payload: EmailVerificationConfirm,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await enforce_auth_rate_limit(request, "email-verification-confirm", 10)
    record = await consume_token(db, payload.token, PURPOSE_EMAIL_VERIFICATION)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired",
        )
    user = await db.get(User, record.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired",
        )
    user.email_verified_at = datetime.now(timezone.utc)
    await _record_event(
        request, db, user_id=user.id, email=user.email,
        event_type="email_verified", success=True,
    )
    await db.commit()
    return {"status": "verified"}


@router.get("/me", response_model=AuthResponse)
async def me(user: User | None = Depends(require_authenticated_user)):
    return AuthResponse(user=_user_out(user) if user else None)
