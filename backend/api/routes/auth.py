from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from user_agents import parse as parse_user_agent

from ..database import get_db
from ..models.database import User, UserRole, OrgMember, OrgRole, Organization, DepartmentMember, Department
from ..models.schemas import (
    LoginRequest, TokenResponse, ChangePasswordRequest,
    LinkTelegramRequest, UserResponse, UserCreate,
    RefreshTokenResponse, RefreshRequest, SessionResponse, SessionsListResponse, LogoutAllResponse
)
from ..services.auth import (
    authenticate_user, create_access_token, get_current_user,
    hash_password, verify_password,
    create_refresh_token, validate_refresh_token, revoke_refresh_token,
    revoke_all_user_tokens, rotate_refresh_token, get_user_sessions,
    get_refresh_token_record, create_short_lived_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, _hash_token,
    org_membership_priority
)
from ..services.password_policy import validate_password
from ..limiter import limiter
from ..config import settings
from ..services.hr_stages import DEFAULT_ORG_STAGES as _HR_DEFAULT_ORG_STAGES

router = APIRouter()


def is_secure_context(request: Request) -> bool:
    """Determine if the request is in a secure HTTPS context.

    Checks:
    1. X-Forwarded-Proto header (set by Railway and most proxies)
    2. Request URL scheme
    3. Falls back to settings.cookie_secure
    """
    # Check X-Forwarded-Proto header (most reliable behind proxy)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    if forwarded_proto == "https":
        return True
    if forwarded_proto == "http":
        return False

    # Check request scheme
    if request.url.scheme == "https":
        return True

    # Fall back to settings
    return settings.cookie_secure


def _get_device_name(request: Request) -> str:
    """Extract a user-friendly device name from User-Agent header using user-agents library."""
    user_agent_str = request.headers.get("user-agent", "")
    if not user_agent_str:
        return "Unknown Device"

    ua = parse_user_agent(user_agent_str)

    # Build device name from parsed data
    if ua.is_mobile:
        if ua.device.family and ua.device.family != "Other":
            return ua.device.family  # e.g., "iPhone", "Samsung Galaxy"
        return "Mobile Device"
    elif ua.is_tablet:
        if ua.device.family and ua.device.family != "Other":
            return ua.device.family  # e.g., "iPad"
        return "Tablet"
    elif ua.is_pc:
        browser = ua.browser.family  # e.g., "Chrome", "Firefox", "Safari"
        if browser and browser != "Other":
            return f"{browser} Browser"
        return "Desktop Browser"
    elif ua.is_bot:
        return "Bot"

    return "Unknown Device"


def _get_client_ip(request: Request) -> str:
    """Адрес клиента — одно правило с лимитами (limiter.client_ip, TRUSTED_PROXY_HOPS)."""
    from ..limiter import client_ip
    return client_ip(request)


@router.post("/login", response_model=TokenResponse)
# Лимита попыток входа нет — решение владельца (24.10.2026): вход не должен
# запирать человека. До этого «20/мин» на деле считалось одним на всю компанию
# (адрес прокси Saturn), см. api/limiter.py.
async def login(
    request: Request,
    response: Response,
    login_request: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    from datetime import datetime, timedelta

    # Блокировка аккаунта после неудачных попыток УБРАНА по требованию: она запирала
    # HR-пользователей на 15 минут (частый кейс — забытый/автозаполненный пароль),
    # что для внутреннего инструмента мешало больше, чем защищало. Проверка lockout и
    # накрутка счётчика с локом после 5 попыток удалены. Колонки
    # failed_login_attempts/locked_until в БД оставлены (просто не читаются на входе);
    # успешный вход ниже их обнуляет, снимая любой ранее выставленный лок.
    authenticated_user = await authenticate_user(db, login_request.email, login_request.password)

    if not authenticated_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful login - reset failed attempts counter
    authenticated_user.failed_login_attempts = 0
    authenticated_user.locked_until = None
    await db.commit()

    # Create short-lived access token (15 minutes)
    access_token = create_short_lived_access_token(
        user_id=authenticated_user.id,
        token_version=authenticated_user.token_version
    )

    # Create long-lived refresh token (7 days)
    device_name = _get_device_name(request)
    ip_address = _get_client_ip(request)
    refresh_token = await create_refresh_token(
        db,
        user_id=authenticated_user.id,
        device_name=device_name,
        ip_address=ip_address
    )

    # Determine if we should use secure flag based on request context
    use_secure = is_secure_context(request)

    # Set httpOnly cookie for access token (XSS protection)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # Not accessible via JavaScript - prevents XSS attacks
        secure=use_secure,  # Only send over HTTPS when in secure context
        samesite="lax",  # CSRF protection
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 15 minutes
        path="/"
    )

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,  # Not accessible via JavaScript
        secure=use_secure,  # Only send over HTTPS when in secure context
        samesite="lax",  # CSRF protection
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 7 days
        path="/api/auth"  # Only sent to auth endpoints (reduces attack surface)
    )

    # Get org membership and role (+ is_readonly — «Наблюдатель»)
    org_role = None
    is_readonly = False
    scope_vacancy_ids: list[int] = []
    org_member_result = await db.execute(
        select(OrgMember.role, OrgMember.is_readonly, OrgMember.scope_vacancy_ids).where(OrgMember.user_id == authenticated_user.id).order_by(*org_membership_priority())
    )
    org_member = org_member_result.first()
    if org_member:
        org_role = org_member[0].value
        is_readonly = bool(org_member[1])
        # Скоуп по воронкам: фронту нужен, чтобы честно подписать баннер
        # наблюдателя («доступ только к выбранным воронкам»).
        scope_vacancy_ids = [int(v) for v in (org_member[2] or [])]

    # Get department membership
    department_id = None
    department_name = None
    department_role = None
    dept_result = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id == authenticated_user.id)
    )
    dept_rows = dept_result.all()
    department_names: list[str] = []
    if dept_rows:
        first_member, first_dept = dept_rows[0]
        department_id = first_dept.id
        department_name = first_dept.name
        department_role = first_member.role.value if first_member.role else None
        department_names = [d.name for _, d in dept_rows]

    # Return access token + user info in response body (needed by Chrome extension)
    # Cookies are also set above for browser-based auth
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        # Расширению отдаём refresh-токен в теле (для silent-refresh из
        # chrome.storage). Вебу — нет, у него httpOnly-кука.
        refresh_token=refresh_token if login_request.include_refresh else None,
        user=UserResponse(
            id=authenticated_user.id, email=authenticated_user.email, name=authenticated_user.name,
            role=authenticated_user.role.value,
            org_role=org_role,
            is_readonly=is_readonly,
            scope_vacancy_ids=scope_vacancy_ids,
            department_id=department_id,
            department_name=department_name,
            department_role=department_role,
            department_names=department_names,
            telegram_id=authenticated_user.telegram_id,
            telegram_username=authenticated_user.telegram_username,
            is_active=authenticated_user.is_active, created_at=authenticated_user.created_at,
            chats_count=0,  # Skip lazy loading for login
            must_change_password=authenticated_user.must_change_password or False
        )
    )


# Registration disabled - only superadmin can create users via /api/users
# @router.post("/register", response_model=TokenResponse)
# async def register(request: UserCreate, db: AsyncSession = Depends(get_db)):
#     ...


@router.post("/register")
@limiter.limit("3/minute")
async def register(request: Request):
    """Public registration is disabled. Contact superadmin to create an account."""
    raise HTTPException(
        status_code=403,
        detail="Регистрация отключена. Обратитесь к администратору для создания аккаунта."
    )


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
):
    """Logout user by clearing cookies and revoking the refresh token."""
    # Revoke the refresh token if present
    if refresh_token:
        await revoke_refresh_token(db, refresh_token)

    # Clear both cookies
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/auth")

    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=RefreshTokenResponse)
@limiter.limit("30/minute")
async def refresh_access_token(
    request: Request,
    response: Response,
    body: Optional[RefreshRequest] = None,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
):
    """Refresh the access token using a valid refresh token.

    This endpoint:
    1. Validates the refresh token from httpOnly cookie ИЛИ из тела (расширение)
    2. Rotates the refresh token (old one is revoked, new one is issued)
    3. Issues a new short-lived access token

    SECURITY: Token rotation prevents replay attacks and allows detection
    of token theft (if a revoked token is presented).
    """
    # Источник refresh-токена: тело (расширение, без кук) приоритетнее куки.
    # Если токен пришёл из тела — новые токены вернём в теле, иначе только в куках.
    body_token = body.refresh_token if (body and body.refresh_token) else None
    token_from_body = body_token is not None
    refresh_token = body_token or refresh_token

    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token not provided"
        )

    # Get device/IP info for the new token
    device_name = _get_device_name(request)
    ip_address = _get_client_ip(request)

    # Rotate the refresh token (revokes old, creates new)
    result = await rotate_refresh_token(
        db,
        old_token=refresh_token,
        device_name=device_name,
        ip_address=ip_address
    )

    if not result:
        # Token was invalid, expired, or already revoked (potential theft)
        # Clear cookies as a security measure
        response.delete_cookie(key="access_token", path="/")
        response.delete_cookie(key="refresh_token", path="/api/auth")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token"
        )

    new_refresh_token, user_id = result

    # Get user for token_version
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        # User was deactivated
        response.delete_cookie(key="access_token", path="/")
        response.delete_cookie(key="refresh_token", path="/api/auth")
        raise HTTPException(
            status_code=401,
            detail="User account is inactive"
        )

    # Create new short-lived access token
    access_token = create_short_lived_access_token(
        user_id=user.id,
        token_version=user.token_version
    )

    # Determine secure flag
    use_secure = is_secure_context(request)

    # Set new access token cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=use_secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )

    # Set new refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=use_secure,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/auth"
    )

    return RefreshTokenResponse(
        message="Token refreshed successfully",
        # Только для расширения (refresh пришёл из тела) — иначе None, веб берёт
        # обновлённые токены из кук.
        access_token=access_token if token_from_body else None,
        refresh_token=new_refresh_token if token_from_body else None,
    )


@router.post("/logout-all", response_model=LogoutAllResponse)
async def logout_all_sessions(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Revoke all refresh tokens for the current user.

    This logs out the user from all devices/sessions.
    Use this when:
    - User suspects their account was compromised
    - User wants to log out from all devices
    - Password was changed and all sessions should be invalidated
    """
    revoked_count = await revoke_all_user_tokens(db, user.id)

    # Also clear the current session's cookies
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/auth")

    return LogoutAllResponse(
        message=f"Successfully logged out from {revoked_count} session(s)",
        revoked_count=revoked_count
    )


@router.get("/sessions", response_model=SessionsListResponse)
async def get_active_sessions(
    refresh_token: Optional[str] = Cookie(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of all active sessions for the current user.

    Returns information about all devices/browsers where the user is logged in.
    Useful for security audit and managing sessions.
    """
    sessions = await get_user_sessions(db, user.id)

    # Determine which session is the current one
    current_token_hash = _hash_token(refresh_token) if refresh_token else None

    session_responses = []
    for session in sessions:
        is_current = (current_token_hash == session.token_hash) if current_token_hash else False
        session_responses.append(SessionResponse(
            id=session.id,
            device_name=session.device_name,
            ip_address=session.ip_address,
            created_at=session.created_at,
            expires_at=session.expires_at,
            is_current=is_current
        ))

    return SessionsListResponse(
        sessions=session_responses,
        total=len(session_responses)
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get org membership and role (+ is_readonly — «Наблюдатель»)
    org_role = None
    is_readonly = False
    scope_vacancy_ids: list[int] = []
    org_member_result = await db.execute(
        select(OrgMember.role, OrgMember.is_readonly, OrgMember.scope_vacancy_ids).where(OrgMember.user_id == user.id).order_by(*org_membership_priority())
    )
    org_member = org_member_result.first()
    if org_member:
        org_role = org_member[0].value
        is_readonly = bool(org_member[1])
        # Скоуп по воронкам: фронту нужен, чтобы честно подписать баннер
        # наблюдателя («доступ только к выбранным воронкам»).
        scope_vacancy_ids = [int(v) for v in (org_member[2] or [])]

    # Get department membership
    department_id = None
    department_name = None
    department_role = None
    dept_result = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id == user.id)
    )
    dept_rows = dept_result.all()
    department_names: list[str] = []
    if dept_rows:
        first_member, first_dept = dept_rows[0]
        department_id = first_dept.id
        department_name = first_dept.name
        department_role = first_member.role.value if first_member.role else None
        department_names = [d.name for _, d in dept_rows]

    return UserResponse(
        id=user.id, email=user.email, name=user.name,
        role=user.role.value,
        org_role=org_role,
        is_readonly=is_readonly,
        scope_vacancy_ids=scope_vacancy_ids,
        department_id=department_id,
        department_name=department_name,
        department_role=department_role,
        department_names=department_names,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        is_active=user.is_active, created_at=user.created_at,
        chats_count=0,  # Skip lazy loading
        must_change_password=user.must_change_password or False
    )


@router.get("/telegram-link")
async def get_telegram_link(user: User = Depends(get_current_user)):
    """Возвращает статус привязки Telegram + deep-link для подключения.

    Telegram-боты не могут писать первыми тем, кто им не написал /start —
    из-за этого юзер не получает уведомления, пока сам не нажмёт start.
    Этот эндпоинт даёт фронту всё нужное чтобы показать баннер
    'Подключите Telegram-бота' с готовой ссылкой.
    """
    bot_username = (settings.telegram_bot_username or "").lstrip("@")
    is_linked = user.telegram_id is not None
    link_url = (
        f"https://t.me/{bot_username}?start=bind_{user.id}"
        if bot_username and not is_linked
        else None
    )
    return {
        "is_linked": is_linked,
        "telegram_id": user.telegram_id,
        "telegram_username": user.telegram_username,
        "bot_username": bot_username or None,
        "link_url": link_url,
    }


# ============================================================
# Org-level stage configuration (kanban labels & colors)
# ============================================================

# Если у орги ещё нет своей конфигурации, отдаём этапы из общего справочника
# (services/hr_stages.py) — те же, что колонки воронки.
DEFAULT_ORG_STAGES = _HR_DEFAULT_ORG_STAGES
ALLOWED_STAGE_KEYS = {s["key"] for s in DEFAULT_ORG_STAGES}


async def _get_user_org_or_404(user: User, db: AsyncSession) -> Organization:
    res = await db.execute(
        select(Organization).join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user.id).limit(1)
    )
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


def _read_org_stages(org: Organization) -> list[dict]:
    """Возвращает stage_config из settings либо дефолты."""
    settings_data = org.settings or {}
    cfg = settings_data.get("stage_config")
    if isinstance(cfg, list) and cfg:
        # Убедимся что все ключи известные — фильтруем неизвестные.
        return [s for s in cfg if isinstance(s, dict) and s.get("key") in ALLOWED_STAGE_KEYS]
    return [dict(s) for s in DEFAULT_ORG_STAGES]


@router.get("/org-stages")
async def get_org_stages(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Текущая конфигурация этапов воронки для орги (или дефолты)."""
    org = await _get_user_org_or_404(user, db)
    return {"stages": _read_org_stages(org)}


# (Редактор «Настройка этапов» убран из UI — этапы зафиксированы на каноне
# DEFAULT_ORG_STAGES; PUT /org-stages удалён. GET остаётся: его читают и
# «Все кандидаты», и воронка для подписей этапов.)


# (Система «шаблонов статусов» удалена: была мёртвой — сохранялась в
# settings['status_templates'], который никто не читал. Реальные этапы воронки
# конфигурируются через stage_config / org-stages выше.)


@router.post("/change-password")
@limiter.limit("3/minute")
async def change_password(
    request: Request,
    password_request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(password_request.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Wrong current password")

    # Validate new password
    is_valid, error_message = validate_password(password_request.new_password, user.email)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    user.password_hash = hash_password(password_request.new_password)
    # Only invalidate tokens if this is a voluntary password change
    # If must_change_password was True (admin reset), user just logged in with fresh token
    # so we don't need to invalidate it
    if not user.must_change_password:
        user.token_version += 1
    # Clear the must_change_password flag if it was set
    user.must_change_password = False
    await db.commit()
    return {"message": "Password changed"}


@router.post("/link-telegram")
async def link_telegram(
    request: LinkTelegramRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check if telegram_id already used
    result = await db.execute(
        select(User).where(User.telegram_id == request.telegram_id, User.id != user.id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Telegram ID already linked")

    user.telegram_id = request.telegram_id
    user.telegram_username = request.telegram_username
    await db.commit()
    return {"message": "Telegram linked"}


# ---------------------------------------------------------------------------
# Telegram Mini App
# ---------------------------------------------------------------------------

class TelegramWebAppLogin(BaseModel):
    init_data: str = Field(min_length=1, description="window.Telegram.WebApp.initData")


@router.post("/telegram-webapp")
@limiter.limit("20/minute")
async def telegram_webapp_login(
    request: Request,
    response: Response,
    data: TelegramWebAppLogin,
    db: AsyncSession = Depends(get_db),
):
    """Вход в Telegram Mini App по подписанному initData.

    Пароля здесь нет и быть не может: личность подтверждает Telegram своей
    подписью. Мы её проверяем (HMAC на производном от токена бота ключе),
    достаём telegram_id и находим уже существующего пользователя.

    Аккаунты тут НЕ создаются: самозаписи в системе нет (см. ТЗ — онбординг
    только админом или по инвайту). Непривязанный Telegram получает 403 с
    понятной инструкцией, а не молчаливый отказ.
    """
    from ..services.telegram_webapp import (
        parse_and_verify, extract_telegram_id, InitDataError,
    )

    try:
        parsed = parse_and_verify(data.init_data, settings.telegram_bot_token or "")
    except InitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    telegram_id = extract_telegram_id(parsed)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="В initData нет пользователя")

    user = (await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=403,
            detail="Этот Telegram не привязан к аккаунту",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт отключён")

    access_token = create_short_lived_access_token(
        user_id=user.id, token_version=user.token_version,
    )
    refresh_token = await create_refresh_token(
        db, user_id=user.id,
        device_name="Telegram Mini App",
        ip_address=_get_client_ip(request),
    )
    await db.commit()

    use_secure = is_secure_context(request)
    response.set_cookie(
        key="access_token", value=access_token, httponly=True,
        secure=use_secure, samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True,
        secure=use_secure, samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, path="/api/auth",
    )

    org_role = (await db.execute(
        select(OrgMember.role).where(OrgMember.user_id == user.id).order_by(*org_membership_priority()).limit(1)
    )).scalar_one_or_none()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id, "email": user.email, "name": user.name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "org_role": org_role.value if org_role is not None and hasattr(org_role, "value") else org_role,
            "telegram_id": user.telegram_id,
            "telegram_username": user.telegram_username,
            "is_active": user.is_active,
        },
    }


class TelegramWebAppBind(BaseModel):
    init_data: str = Field(min_length=1, description="window.Telegram.WebApp.initData")
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.post("/telegram-webapp-bind")
@limiter.limit("5/minute")
async def telegram_webapp_bind(
    request: Request,
    response: Response,
    data: TelegramWebAppBind,
    db: AsyncSession = Depends(get_db),
):
    """Привязать текущий Telegram к аккаунту прямо из Mini App.

    Нужен тем, у кого привязки ещё нет: до этого единственным путём была
    одноразовая ссылка из личного кабинета, а кнопки для неё в вебе нет —
    человек оказывался в тупике.

    Личность подтверждается ДВАЖДЫ: подписью Telegram (она даёт достоверный
    telegram_id — подделать нельзя) и паролем от аккаунта. Это строго
    надёжнее отключённой команды /bind, которая привязывала кого угодно к
    любому аккаунту, зная только email.
    """
    from ..services.telegram_webapp import (
        parse_and_verify, extract_telegram_id, InitDataError,
    )

    try:
        parsed = parse_and_verify(data.init_data, settings.telegram_bot_token or "")
    except InitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    telegram_id = extract_telegram_id(parsed)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="В initData нет пользователя")

    # Пароль проверяем ПОСЛЕ подписи: без валидного initData сюда не пройти,
    # поэтому эндпоинт нельзя использовать как площадку для перебора паролей.
    user = await authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверная почта или пароль")

    # Этот Telegram уже занят другим аккаунтом — молча «переезжать» нельзя,
    # иначе один человек увёл бы у другого доступ к боту.
    other = (await db.execute(
        select(User).where(User.telegram_id == telegram_id, User.id != user.id)
    )).scalar_one_or_none()
    if other:
        raise HTTPException(
            status_code=409,
            detail="Этот Telegram уже привязан к другому аккаунту. Отвяжите его там.",
        )

    user = await db.merge(user)
    user.telegram_id = telegram_id
    tg_username = (parsed.get("user") or {}).get("username") if isinstance(parsed.get("user"), dict) else None
    if tg_username:
        user.telegram_username = tg_username
    user.telegram_bind_token = None
    user.telegram_bind_expires = None

    access_token = create_short_lived_access_token(
        user_id=user.id, token_version=user.token_version,
    )
    refresh_token = await create_refresh_token(
        db, user_id=user.id,
        device_name="Telegram Mini App",
        ip_address=_get_client_ip(request),
    )
    await db.commit()

    use_secure = is_secure_context(request)
    response.set_cookie(
        key="access_token", value=access_token, httponly=True,
        secure=use_secure, samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True,
        secure=use_secure, samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, path="/api/auth",
    )

    org_role = (await db.execute(
        select(OrgMember.role).where(OrgMember.user_id == user.id).order_by(*org_membership_priority()).limit(1)
    )).scalar_one_or_none()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id, "email": user.email, "name": user.name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "org_role": org_role.value if org_role is not None and hasattr(org_role, "value") else org_role,
            "telegram_id": user.telegram_id,
            "telegram_username": user.telegram_username,
            "is_active": user.is_active,
        },
    }


class BindLinkRequest(BaseModel):
    # Для кого выпустить ссылку. Пусто — себе. Чужому можно только админу
    # своей организации: сотрудник мог принять приглашение и не привязать
    # Telegram, и без этого пути у него не осталось бы никакого способа.
    user_id: Optional[int] = None


@router.post("/telegram-bind-link")
@limiter.limit("5/minute")
async def create_telegram_bind_link(
    request: Request,
    payload: Optional[BindLinkRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Одноразовая ссылка для привязки Telegram.

    Единственный безопасный путь привязки: запросить её может только уже
    авторизованный пользователь (себе) либо админ организации (сотруднику).
    Ссылка гаснет после первого использования. Прежние способы (/bind по email
    и /start bind_<id>) не требовали подтверждения вообще и позволяли забрать
    чужой аккаунт.
    """
    import secrets as _secrets
    from datetime import datetime as _dt, timedelta as _td

    target_id = payload.user_id if payload else None

    if target_id is None or target_id == current_user.id:
        target = await db.merge(current_user)
        ttl_minutes = 15
    else:
        # Выдача чужой ссылки — фактически передача доступа к аккаунту,
        # поэтому проверяем и права, и общую организацию.
        actor_org_ids = set((await db.execute(
            select(OrgMember.org_id).where(OrgMember.user_id == current_user.id)
        )).scalars().all())
        is_admin = current_user.role == UserRole.superadmin or bool((await db.execute(
            select(OrgMember.id).where(
                OrgMember.user_id == current_user.id,
                OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
            ).limit(1)
        )).scalar_one_or_none())
        if not is_admin:
            raise HTTPException(403, "Только администратор может выдать ссылку сотруднику")

        target = (await db.execute(
            select(User).where(User.id == target_id)
        )).scalar_one_or_none()
        if not target:
            raise HTTPException(404, "Пользователь не найден")
        if not target.is_active:
            raise HTTPException(400, "Аккаунт отключён")

        if current_user.role != UserRole.superadmin:
            target_org_ids = set((await db.execute(
                select(OrgMember.org_id).where(OrgMember.user_id == target_id)
            )).scalars().all())
            if not (actor_org_ids & target_org_ids):
                raise HTTPException(403, "Сотрудник не из вашей организации")

        # Сотрудник пойдёт по ссылке не сию секунду — её ещё надо переслать
        ttl_minutes = 60 * 24

    token = _secrets.token_urlsafe(32)
    target.telegram_bind_token = token
    target.telegram_bind_expires = _dt.utcnow() + _td(minutes=ttl_minutes)
    await db.commit()

    bot_username = (settings.telegram_bot_username or "").lstrip("@")
    link = f"https://t.me/{bot_username}?start={token}" if bot_username else None

    return {
        "token": token,
        "link": link,
        "user_id": target.id,
        "expires_in_minutes": ttl_minutes,
        "hint": f"Ссылка одноразовая и действует {ttl_minutes} мин.",
    }


@router.delete("/telegram-bind")
async def unbind_telegram(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отвязать Telegram от своего аккаунта."""
    current_user = await db.merge(current_user)
    current_user.telegram_id = None
    current_user.telegram_username = None
    current_user.telegram_bind_token = None
    current_user.telegram_bind_expires = None
    await db.commit()
    return {"ok": True}
