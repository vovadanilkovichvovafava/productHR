from datetime import datetime
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator
from .database import ChatType, UserRole, EntityType, EntityStatus, OrgRole, DeptRole


# Auth
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Расширение (chrome-extension) не умеет httpOnly-куки для кросс-сайтовых
    # POST → просит refresh-токен в теле ответа, чтобы хранить его в
    # chrome.storage и самому обновлять access. Веб этот флаг не шлёт.
    include_refresh: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"
    # Заполняется только при include_refresh=True (расширение). Для веба None —
    # там refresh лежит в httpOnly-куке и в тело не попадает.
    refresh_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate password complexity requirements."""
        from ..services.password_policy import validate_password
        is_valid, error_message = validate_password(v)
        if not is_valid:
            raise ValueError(error_message)
        return v


class LinkTelegramRequest(BaseModel):
    telegram_id: int
    telegram_username: Optional[str] = None


# Refresh Token Endpoints
class RefreshTokenResponse(BaseModel):
    """Response after successful token refresh."""
    message: str = "Token refreshed successfully"
    # Заполняются только при refresh из ТЕЛА (расширение); веб берёт новые токены
    # из обновлённых httpOnly-кук и эти поля игнорирует.
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):
    """Тело /api/auth/refresh для клиентов без кук (расширение)."""
    refresh_token: Optional[str] = None


class SessionResponse(BaseModel):
    """Information about an active session (refresh token)."""
    id: int
    device_name: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    expires_at: datetime
    is_current: bool = False  # True if this is the session making the request

    class Config:
        from_attributes = True


class SessionsListResponse(BaseModel):
    """List of active sessions for the current user."""
    sessions: List["SessionResponse"]
    total: int


class LogoutAllResponse(BaseModel):
    """Response after revoking all refresh tokens."""
    message: str
    revoked_count: int


# Users
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole = UserRole.admin  # Use enum for proper validation
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    department_id: Optional[int] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str, info) -> str:
        """Validate password complexity requirements."""
        from ..services.password_policy import validate_password
        # Get email from values if available for additional validation
        email = info.data.get('email') if info.data else None
        is_valid, error_message = validate_password(v, email)
        if not is_valid:
            raise ValueError(error_message)
        return v


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: Optional[str] = None  # Accept string, validate in route (superadmin, admin, sub_admin, member)
    org_role: Optional[str] = None  # OrgRole: owner, admin, hr, member
    dept_role: Optional[str] = None  # DeptRole: lead, sub_admin, member
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    is_active: Optional[bool] = None
    department_id: Optional[int] = None
    # Скоуп по воронкам (01.10.2026): какие вакансии видит наблюдатель. Пустой
    # список снимает ограничение (видит весь пул, как раньше).
    scope_vacancy_ids: Optional[List[int]] = None


class UserProfileUpdate(BaseModel):
    """Schema for users updating their own profile settings."""
    name: Optional[str] = None
    telegram_username: Optional[str] = None
    additional_emails: Optional[List[str]] = None
    additional_telegram_usernames: Optional[List[str]] = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: UserRole  # Use enum for consistency with database
    org_role: Optional[str] = None  # owner, admin, member
    is_readonly: bool = False  # «Наблюдатель»: видит всё, но не может ничего менять
    # Воронки, которыми ограничена видимость кандидатов (пусто — не ограничена).
    scope_vacancy_ids: List[int] = []
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    department_role: Optional[str] = None  # lead, sub_admin, member
    department_names: List[str] = []  # все департаменты, в которых состоит юзер
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    additional_emails: List[str] = []
    additional_telegram_usernames: List[str] = []
    is_active: bool
    created_at: datetime
    chats_count: int = 0
    must_change_password: bool = False

    class Config:
        from_attributes = True


# Chat Types
class ChatTypeInfo(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    color: str


class QuickAction(BaseModel):
    id: str
    label: str
    icon: str


class ChatTypeConfig(BaseModel):
    type_info: ChatTypeInfo
    quick_actions: List[QuickAction]
    suggested_questions: List[str]
    default_criteria: List[dict]


# Chats
class ChatResponse(BaseModel):
    id: int
    telegram_chat_id: int
    title: str
    custom_name: Optional[str]
    chat_type: ChatType = ChatType.hr  # Use enum for consistency
    custom_type_name: Optional[str] = None
    custom_type_description: Optional[str] = None
    owner_id: Optional[int]
    owner_name: Optional[str] = None
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    is_active: bool
    messages_count: int = 0
    participants_count: int = 0
    last_activity: Optional[datetime]
    created_at: datetime
    has_criteria: bool = False
    deleted_at: Optional[datetime] = None
    days_until_permanent_delete: Optional[int] = None
    # Permission fields for frontend
    is_mine: bool = False
    is_shared: bool = False
    access_level: Optional[str] = None  # 'view', 'edit', 'full' or None

    class Config:
        from_attributes = True


class ChatUpdate(BaseModel):
    custom_name: Optional[str] = None
    chat_type: Optional[ChatType] = None
    custom_type_name: Optional[str] = None
    custom_type_description: Optional[str] = None
    owner_id: Optional[int] = None
    entity_id: Optional[int] = None
    is_active: Optional[bool] = None


# Messages
class MessageResponse(BaseModel):
    id: int
    telegram_user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    content: str
    content_type: str
    file_id: Optional[str] = None  # Telegram file ID for images/documents
    file_path: Optional[str] = None  # Local file path for imported media
    file_name: Optional[str]
    document_metadata: Optional[dict] = None  # {file_type, pages_count, sheets, etc}
    parse_status: Optional[str] = None  # parsed, partial, failed
    parse_error: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class ParticipantResponse(BaseModel):
    telegram_user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    messages_count: int


# Criteria
class CriterionItem(BaseModel):
    name: str
    weight: int = Field(default=5, ge=1, le=10)  # 1-10
    description: Optional[str] = None
    category: Optional[str] = None  # basic, red_flag, green_flag


class CriteriaPresetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    criteria: List[CriterionItem]
    category: Optional[str] = None
    is_global: bool = False
    chat_type: Optional[str] = None  # For type-specific presets
    is_default: bool = False  # Mark as default for chat type


class CriteriaPresetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    criteria: List[dict]
    category: Optional[str]
    is_global: bool
    chat_type: Optional[str] = None
    is_default: bool = False
    created_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class ChatTypeDefaultCriteriaUpdate(BaseModel):
    """Update default criteria for a chat type."""
    criteria: List[CriterionItem]


class EntityTypeDefaultCriteriaUpdate(BaseModel):
    """Update default criteria for an entity type."""
    criteria: List[CriterionItem]


class ChatCriteriaUpdate(BaseModel):
    criteria: List[CriterionItem]


class ChatCriteriaResponse(BaseModel):
    id: int
    chat_id: int
    criteria: List[dict]
    updated_at: datetime

    class Config:
        from_attributes = True


# Entity Criteria
class EntityCriteriaUpdate(BaseModel):
    criteria: List[CriterionItem]


class EntityCriteriaResponse(BaseModel):
    id: int
    entity_id: int
    criteria: List[dict]
    updated_at: datetime

    class Config:
        from_attributes = True


# AI Chat
class AIMessageRequest(BaseModel):
    message: Optional[str] = None
    quick_action: Optional[str] = None  # full_analysis, red_flags, strengths, recommendation


class AIMessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime


class AIConversationResponse(BaseModel):
    id: int
    chat_id: int
    messages: List[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Analysis & Reports
class AnalyzeRequest(BaseModel):
    report_type: Literal["standard", "detailed", "summary"] = "standard"
    include_quotes: bool = True
    include_scores: bool = True
    include_red_flags: bool = True
    include_green_flags: bool = True
    include_recommendation: bool = True


class ReportRequest(BaseModel):
    format: str = "pdf"  # pdf, docx, markdown
    report_type: str = "standard"
    include_full_conversation: bool = False


class AnalysisResponse(BaseModel):
    id: int
    chat_id: int
    result: str
    report_type: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Stats
class StatsResponse(BaseModel):
    total_chats: int
    total_messages: int
    total_participants: int
    total_analyses: int
    active_chats: int
    messages_today: int
    messages_this_week: int
    activity_by_day: List[dict]
    messages_by_type: dict
    top_chats: List[dict]


# Update forward refs
TokenResponse.model_rebuild()
SessionsListResponse.model_rebuild()
