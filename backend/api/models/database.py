from datetime import datetime, time
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Enum as SQLEnum, Float,
    ForeignKey, Index, Integer, LargeBinary, String, Table, Text, JSON, Time, func, text, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum

# Optional pgvector support - graceful fallback if not installed
try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    Vector = None
    PGVECTOR_AVAILABLE = False


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    # Names must be lowercase to match PostgreSQL enum values
    superadmin = "superadmin"  # Platform-wide admin (can access all orgs)
    admin = "admin"            # Legacy: kept for backwards compatibility
    sub_admin = "sub_admin"    # Legacy: kept for backwards compatibility
    member = "member"          # Regular user (access determined by OrgRole and DeptRole)


class ChatType(str, enum.Enum):
    # Names must be lowercase to match PostgreSQL enum values
    work = "work"                # General work chat
    hr = "hr"                    # Candidate evaluation
    project = "project"          # Team project chat
    client = "client"            # Client communication
    contractor = "contractor"    # External contractor
    sales = "sales"              # Sales negotiations
    support = "support"          # Customer support
    custom = "custom"            # Custom user-defined type


class EntityType(str, enum.Enum):
    candidate = "candidate"
    client = "client"
    contractor = "contractor"
    lead = "lead"
    partner = "partner"
    custom = "custom"


class EntityStatus(str, enum.Enum):
    """Status/stage for entities (especially candidates)

    HR Pipeline stages: new → screening → practice → tech_practice → is_interview → offer → hired/rejected
    """
    # HR Pipeline stages (match ApplicationStage for consistency)
    new = "new"                   # Новый - just added
    screening = "screening"       # Скрининг - initial review
    practice = "practice"         # Практика - practical task/test
    tech_practice = "tech_practice"  # Тех-практика - technical practice
    is_interview = "is_interview" # ИС - final interview
    offer = "offer"               # Оффер - offer extended
    hired = "hired"               # Принят - accepted and hired
    probation = "probation"       # Практика - пробный период после оффера
    transferred = "transferred"   # Перешёл в отдел - оформлен в штат
    # Финал жизненного цикла в штате (доска «Статусы»). Раньше увольнение
    # хранилось только на Employee.is_active, без разделения уволен/уволился.
    dismissed = "dismissed"       # Уволен - по инициативе компании
    quit = "quit"                 # Уволился - по собственному
    rejected = "rejected"         # Отказ - rejected
    withdrawn = "withdrawn"       # Отозван - кандидат отозвал отклик
    reserve = "reserve"           # Резерв - отложен в резерв

    # General entity statuses (for clients, partners, etc.)
    interview = "interview"       # Legacy: interview stage
    active = "active"
    paused = "paused"
    churned = "churned"
    converted = "converted"
    ended = "ended"
    negotiation = "negotiation"


class VacancyStatus(str, enum.Enum):
    """Status of a job vacancy"""
    draft = "draft"                      # Not yet published (legacy, не показывается на UI)
    pending_review = "pending_review"    # На рассмотрении — заявка отправлена на апрув
    open = "open"                        # Actively hiring
    paused = "paused"                    # Temporarily paused
    closed = "closed"                    # Position filled
    cancelled = "cancelled"              # Cancelled/no longer needed


class ProjectStatus(str, enum.Enum):
    """Status of a project"""
    planning = "planning"        # Планирование
    active = "active"            # В разработке
    on_hold = "on_hold"          # На паузе
    completed = "completed"      # Завершён
    cancelled = "cancelled"      # Отменён


class TaskStatus(str, enum.Enum):
    """Status of a project task"""
    backlog = "backlog"          # Бэклог
    todo = "todo"                # К выполнению
    in_progress = "in_progress"  # В работе
    review = "review"            # На ревью
    done = "done"                # Готово
    cancelled = "cancelled"      # Отменено


class ProjectRole(str, enum.Enum):
    """Role of a user within a project"""
    manager = "manager"          # Менеджер проекта
    developer = "developer"      # Разработчик
    reviewer = "reviewer"        # Ревьюер
    observer = "observer"        # Наблюдатель


class TimeOffType(str, enum.Enum):
    vacation = "vacation"
    day_off = "day_off"
    sick_leave = "sick_leave"
    other = "other"


class TimeOffStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class BlockerStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"


class ApplicationStage(str, enum.Enum):
    """Pipeline stage for candidate application

    HR Pipeline (using existing PostgreSQL enum values with HR labels):
    applied (Новый) → screening (Скрининг) → phone_screen (Практика) →
    interview (Тех-практика) → assessment (ИС) → offer (Оффер) → hired/rejected

    Note: We use the existing PostgreSQL enum values but display HR-friendly labels in the UI.
    """
    # HR Pipeline stages (these exist in PostgreSQL enum)
    applied = "applied"           # Новый - just added to vacancy (displayed as "Новый")
    screening = "screening"       # Скрининг - initial review
    phone_screen = "phone_screen" # Практика - practical task/test (displayed as "Практика")
    interview = "interview"       # Тех-практика - technical interview (displayed as "Тех-практика")
    assessment = "assessment"     # ИС - final interview (displayed as "ИС")
    offer = "offer"               # Оффер - offer extended
    hired = "hired"               # Принят - accepted and hired
    probation = "probation"       # Практика - пробный период после оффера
    transferred = "transferred"   # Перешёл в отдел - оформлен в штат
    rejected = "rejected"         # Отказ - rejected at any stage
    withdrawn = "withdrawn"       # Отозван - candidate withdrew
    reserve = "reserve"           # Резерв - отложен в резерв

    # Deprecated values (these do NOT exist in PostgreSQL enum and will cause errors)
    # DO NOT USE these - they were added but never migrated to the database:
    # new = "new"
    # practice = "practice"
    # tech_practice = "tech_practice"
    # is_interview = "is_interview"

# Sync mappings between EntityStatus and ApplicationStage
STATUS_SYNC_MAP = {
    EntityStatus.new: ApplicationStage.applied,
    EntityStatus.screening: ApplicationStage.screening,
    EntityStatus.practice: ApplicationStage.phone_screen,
    EntityStatus.tech_practice: ApplicationStage.interview,
    EntityStatus.is_interview: ApplicationStage.assessment,
    EntityStatus.offer: ApplicationStage.offer,
    EntityStatus.hired: ApplicationStage.hired,
    EntityStatus.probation: ApplicationStage.probation,
    EntityStatus.transferred: ApplicationStage.transferred,
    EntityStatus.rejected: ApplicationStage.rejected,
    EntityStatus.withdrawn: ApplicationStage.withdrawn,
    EntityStatus.reserve: ApplicationStage.reserve,
}

STAGE_SYNC_MAP = {v: k for k, v in STATUS_SYNC_MAP.items()}

class EntityFileType(str, enum.Enum):
    """Type of file attached to an entity"""
    resume = "resume"
    cover_letter = "cover_letter"
    test_assignment = "test_assignment"
    certificate = "certificate"
    portfolio = "portfolio"
    offer = "offer"            # документ оффера (колонка «Оффер» на доске «Статусы»)
    other = "other"


class CallSource(str, enum.Enum):
    meet = "meet"
    zoom = "zoom"
    teams = "teams"
    upload = "upload"
    telegram = "telegram"
    google_doc = "google_doc"  # Transcript from Google Docs
    google_drive = "google_drive"  # Media file from Google Drive
    direct_url = "direct_url"  # Direct link to audio/video
    fireflies = "fireflies"  # Fireflies.ai transcript


class CallStatus(str, enum.Enum):
    pending = "pending"
    connecting = "connecting"
    recording = "recording"
    processing = "processing"
    transcribing = "transcribing"
    analyzing = "analyzing"
    done = "done"
    failed = "failed"


class ReportType(str, enum.Enum):
    daily_hr = "daily_hr"
    weekly_summary = "weekly_summary"
    daily_calls = "daily_calls"
    weekly_pipeline = "weekly_pipeline"


class DeliveryMethod(str, enum.Enum):
    telegram = "telegram"
    email = "email"


class OrgRole(str, enum.Enum):
    owner = "owner"      # Full access, can delete org
    admin = "admin"      # HR Admin — всё кроме /users (Настя)
    hr = "hr"            # HR рекрутер — кандидаты, воронки, вакансии, созвоны (Мария)
    member = "member"    # Сотрудник — профиль, проекты, документы


class DeptRole(str, enum.Enum):
    lead = "lead"           # Department lead - sees all dept data, full management
    sub_admin = "sub_admin" # Sub-admin - sees all dept data, limited management
    member = "member"       # Regular member - sees own data + shared


class SubscriptionPlan(str, enum.Enum):
    free = "free"
    pro = "pro"
    enterprise = "enterprise"


class Organization(Base):
    """Organization for multi-tenancy"""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    subscription_plan = Column(SQLEnum(SubscriptionPlan), default=SubscriptionPlan.free)
    settings = Column(JSON, default=dict)  # {max_users, max_chats, features, etc}
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    members = relationship("OrgMember", back_populates="organization", cascade="all, delete-orphan")
    departments = relationship("Department", back_populates="organization", cascade="all, delete-orphan")
    entities = relationship("Entity", back_populates="organization", cascade="all, delete-orphan")
    chats = relationship("Chat", back_populates="organization", cascade="all, delete-orphan")
    calls = relationship("CallRecording", back_populates="organization", cascade="all, delete-orphan")


class OrgMember(Base):
    """Organization membership - links users to organizations"""
    __tablename__ = "org_members"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SQLEnum(OrgRole), default=OrgRole.member)
    # «Наблюдатель»: read-only набор прав ПОВЕРХ роли. Роль даёт видимость (admin →
    # видит всех кандидатов), а этот флаг ЖЁСТКО запрещает любые изменения (все
    # не-GET запросы → 403 в get_current_user). Ортогонален роли: admin+readonly =
    # видит всё, но ничего не меняет. Для менторов, которым нужен только просмотр.
    is_readonly = Column(Boolean, default=False, nullable=False)
    # Скоуп по воронкам (01.10.2026, запрос Марии): список id вакансий, которыми
    # ограничена видимость кандидатов у этого человека. Пусто/NULL — ограничения
    # НЕТ (видит весь пул орга, как и раньше); непустой список — видны только
    # кандидаты с заявкой в этих воронках, и сами воронки тоже только эти.
    # Задумано для наблюдателя-ментора из другого отдела: «вижу только Трафик».
    scope_vacancy_ids = Column(JSON, nullable=True)
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'org_id', name='uq_org_member_user_org'),
    )

    organization = relationship("Organization", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="org_memberships")
    inviter = relationship("User", foreign_keys=[invited_by])


class Department(Base):
    """Department within an organization"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    color = Column(String(20), nullable=True)  # For UI display (e.g., "#3B82F6")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    organization = relationship("Organization", back_populates="departments")
    parent = relationship("Department", remote_side=[id], back_populates="children")
    children = relationship("Department", back_populates="parent", cascade="all, delete-orphan")
    members = relationship("DepartmentMember", back_populates="department", cascade="all, delete-orphan")
    entities = relationship("Entity", back_populates="department")


class DepartmentMember(Base):
    """Department membership - links users to departments"""
    __tablename__ = "department_members"

    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SQLEnum(DeptRole), default=DeptRole.member)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'department_id', name='uq_dept_member_user_dept'),
    )

    department = relationship("Department", back_populates="members")
    user = relationship("User", back_populates="department_memberships")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False, index=True)
    role = Column(SQLEnum(UserRole), default=UserRole.member)
    telegram_id = Column(BigInteger, unique=True, nullable=True, index=True)
    # Одноразовый токен привязки Telegram. Раньше привязка шла по /bind <email>
    # и по /start bind_<user_id> — без ЛЮБОЙ проверки: кто угадал email или
    # перебрал id, тот и забирал аккаунт. Теперь бинд возможен только по
    # секретному токену, который выдаётся уже авторизованному пользователю
    # (или админом) и живёт ограниченное время.
    telegram_bind_token = Column(String(64), nullable=True, index=True)
    telegram_bind_expires = Column(DateTime, nullable=True)
    telegram_username = Column(String(255), nullable=True)
    # Additional contact identifiers for speaker matching
    additional_emails = Column(JSON, default=list)  # List of additional email addresses
    additional_telegram_usernames = Column(JSON, default=list)  # List of additional telegram usernames
    notification_prefs = Column(JSON, default=dict)  # {notif_type: bool} вкл/выкл типов уведомлений (дефолты — в routes/notifications.py)
    is_active = Column(Boolean, default=True)
    token_version = Column(Integer, default=0, nullable=False)  # Increment on password change
    # Brute force protection
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    # Password reset by admin
    must_change_password = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    # Shadow user system - hidden superadmins with content isolation
    is_shadow = Column(Boolean, default=False, index=True)
    shadow_owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    chats = relationship("Chat", back_populates="owner")
    criteria_presets = relationship("CriteriaPreset", back_populates="created_by_user")
    ai_conversations = relationship("AIConversation", back_populates="user")
    analyses = relationship("AnalysisHistory", back_populates="user")
    org_memberships = relationship("OrgMember", foreign_keys="OrgMember.user_id", back_populates="user", cascade="all, delete-orphan")
    department_memberships = relationship("DepartmentMember", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    # Additional back_populates relationships
    owned_calls = relationship("CallRecording", back_populates="owner")
    report_subscriptions = relationship("ReportSubscription", back_populates="user", cascade="all, delete-orphan")
    entity_ai_conversations = relationship("EntityAIConversation", back_populates="user", cascade="all, delete-orphan")
    entity_analyses = relationship("EntityAnalysis", back_populates="user")
    uploaded_files = relationship("EntityFile", back_populates="uploader")


class ApiToken(Base):
    """Long-lived API token for external integrations (e.g. Claude MCP server).

    Owner = User. One human can have multiple named tokens. We store only
    sha256 hash — plain token is shown to the user ONCE at generation time.
    Actions done with the token are attributed to the owner (created_by, etc.).
    """
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)              # human-readable label
    token_hash = Column(String(64), unique=True, nullable=False, index=True)  # sha256 hex
    prefix = Column(String(12), nullable=False)            # first chars shown in UI
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    custom_name = Column(String(255), nullable=True)
    chat_type = Column(SQLEnum(ChatType), default=ChatType.work, index=True)
    custom_type_name = Column(String(255), nullable=True)  # For CUSTOM type
    custom_type_description = Column(Text, nullable=True)  # For CUSTOM type
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    auto_tasks_enabled = Column(Boolean, default=True, server_default="true")  # Auto-create tasks & status detection (on by default)
    remind_enabled = Column(Boolean, default=True, server_default="true")  # Standup reminders via /remind
    last_standup_at = Column(DateTime, nullable=True)  # Last time auto-tasks created tasks from this chat
    created_at = Column(DateTime, default=func.now())
    last_activity = Column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True, index=True)  # Soft delete timestamp

    __table_args__ = (
        # Composite index for filtering non-deleted chats by org (common list query)
        Index('ix_chat_org_deleted', 'org_id', 'deleted_at'),
        # Composite index for filtering by owner and activity
        Index('ix_chat_owner_activity', 'owner_id', 'last_activity'),
    )

    organization = relationship("Organization", back_populates="chats")
    owner = relationship("User", back_populates="chats")
    entity = relationship("Entity", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    criteria = relationship("ChatCriteria", back_populates="chat", uselist=False, cascade="all, delete-orphan")
    ai_conversations = relationship("AIConversation", back_populates="chat", cascade="all, delete-orphan")
    analyses = relationship("AnalysisHistory", back_populates="chat", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    content_type = Column(String(50), nullable=False, index=True)  # text, voice, video_note, document, photo, etc
    file_id = Column(String(255), nullable=True)  # Telegram Bot API file_id
    file_path = Column(String(512), nullable=True, index=True)  # Local file path for imported media
    file_name = Column(String(255), nullable=True)
    # Document parsing metadata
    document_metadata = Column(JSON, nullable=True)  # {file_type, pages_count, sheets, etc}
    parse_status = Column(String(20), nullable=True)  # parsed, partial, failed
    parse_error = Column(Text, nullable=True)
    is_imported = Column(Boolean, default=False)  # True if imported from file (not from bot)
    timestamp = Column(DateTime, default=func.now())

    __table_args__ = (
        # Composite index for message filtering by chat and user (common query pattern)
        Index('ix_message_chat_telegram_user', 'chat_id', 'telegram_user_id'),
        # Composite index for sorting messages by timestamp (common list query)
        Index('ix_message_chat_timestamp', 'chat_id', 'timestamp'),
    )

    chat = relationship("Chat", back_populates="messages")


class CriteriaPreset(Base):
    __tablename__ = "criteria_presets"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    criteria = Column(JSON, nullable=False)  # [{name, weight, description, category}]
    category = Column(String(100), nullable=True)  # basic, red_flags, green_flags, position
    chat_type = Column(SQLEnum(ChatType), nullable=True, index=True)  # Type-specific presets for chats
    entity_type = Column(SQLEnum(EntityType), nullable=True, index=True)  # Type-specific presets for entities
    is_global = Column(Boolean, default=False)  # True = visible to all
    is_default = Column(Boolean, default=False)  # True = default for chat/entity type
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    created_by_user = relationship("User", back_populates="criteria_presets")


class ChatCriteria(Base):
    __tablename__ = "chat_criteria"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), unique=True, nullable=False)
    criteria = Column(JSON, nullable=False)  # [{name, weight, description}]
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    chat = relationship("Chat", back_populates="criteria")


class EntityCriteria(Base):
    __tablename__ = "entity_criteria"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), unique=True, nullable=False)
    criteria = Column(JSON, nullable=False)  # [{name, weight, description, category}]
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    entity = relationship("Entity", back_populates="criteria")


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    messages = Column(JSON, nullable=False, default=list)  # [{role, content, timestamp}]
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    chat = relationship("Chat", back_populates="ai_conversations")
    user = relationship("User", back_populates="ai_conversations")


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    result = Column(Text, nullable=False)
    report_type = Column(String(50), nullable=True)  # full, quick, red_flags, etc
    report_format = Column(String(20), nullable=True)  # pdf, docx, markdown
    criteria_used = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())

    chat = relationship("Chat", back_populates="analyses")
    user = relationship("User", back_populates="analyses")
    entity = relationship("Entity", back_populates="analyses")


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(SQLEnum(EntityType), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    status = Column(SQLEnum(EntityStatus), default=EntityStatus.new, index=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    telegram_user_id = Column(BigInteger, nullable=True, index=True)
    company = Column(String(255), nullable=True)
    position = Column(String(255), nullable=True)
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)  # renamed from 'metadata' (reserved by SQLAlchemy)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Multiple identifiers support
    telegram_usernames = Column(JSON, default=list)  # List of telegram usernames (normalized, lowercase, without @)
    emails = Column(JSON, default=list)  # List of additional emails
    phones = Column(JSON, default=list)  # List of additional phone numbers

    # Transfer tracking fields
    is_transferred = Column(Boolean, default=False, index=True)
    transferred_to_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    transferred_at = Column(DateTime, nullable=True)

    # Shadow/archive base — candidates from bulk import (CSV/parser) or manually
    # archived. Hidden from all active lists/kanban/search/analytics; the full
    # archive is visible only to superadmin. See shadow-dedup design spec.
    is_archived = Column(Boolean, default=False, nullable=False, index=True)

    # Денормализованный поисковый блоб для умного поиска (транслитерация + любой
    # порядок слов + опечатки через pg_trgm): ФИО в ДВУХ алфавитах + должность/
    # компания/теги. Пишется на insert/update (services/search_index.py events),
    # GIN-триграммный индекс создаётся в start.sh.
    search_name = Column(Text, nullable=True)

    organization = relationship("Organization", back_populates="entities")
    department = relationship("Department", back_populates="entities")
    creator = relationship("User", foreign_keys=[created_by])
    transferred_to = relationship("User", foreign_keys=[transferred_to_id])
    chats = relationship("Chat", back_populates="entity")
    calls = relationship("CallRecording", back_populates="entity")
    transfers = relationship("EntityTransfer", back_populates="entity", primaryjoin="Entity.id==EntityTransfer.entity_id")
    analyses = relationship("AnalysisHistory", back_populates="entity")
    ai_conversations = relationship("EntityAIConversation", back_populates="entity", cascade="all, delete-orphan")
    ai_analyses = relationship("EntityAnalysis", back_populates="entity", cascade="all, delete-orphan")
    criteria = relationship("EntityCriteria", back_populates="entity", uselist=False, cascade="all, delete-orphan")
    files = relationship("EntityFile", back_populates="entity", cascade="all, delete-orphan")
    tag_objects = relationship("EntityTag", secondary="entity_tags", back_populates="entities")

    # Expected salary for candidates
    expected_salary_min = Column(Integer, nullable=True)
    expected_salary_max = Column(Integer, nullable=True)
    expected_salary_currency = Column(String(10), default='RUB')

    # AI Long-term Memory
    # Auto-updated summary of all interactions with this entity
    ai_summary = Column(Text, nullable=True)
    ai_summary_updated_at = Column(DateTime, nullable=True)
    # Key events/milestones extracted from conversations
    # Format: [{"date": "2024-01-15", "event": "hired", "details": "Hired to development team"}]
    key_events = Column(JSON, default=list)

    # Vector embedding for similarity search (OpenAI text-embedding-3-small: 1536 dimensions)
    # Note: embedding column is added via migration if pgvector is available
    embedding_updated_at = Column(DateTime, nullable=True)

    # Optimistic locking version field
    # Incremented on each update to detect concurrent modifications
    version = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        # Composite indexes for common query patterns
        Index('ix_entity_org_status', 'org_id', 'status'),  # Filter by org + status
        Index('ix_entity_org_created_by', 'org_id', 'created_by'),  # Filter by org + creator
        Index('ix_entity_org_type', 'org_id', 'type'),  # Filter by org + entity type
    )


class EntityTransfer(Base):
    __tablename__ = "entity_transfers"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    from_department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    to_department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    # For cancel functionality
    copy_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_deadline = Column(DateTime, nullable=True)  # Usually created_at + 1 hour

    entity = relationship("Entity", back_populates="transfers", foreign_keys=[entity_id])
    copy_entity = relationship("Entity", foreign_keys=[copy_entity_id])
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    from_department = relationship("Department", foreign_keys=[from_department_id])
    to_department = relationship("Department", foreign_keys=[to_department_id])


class CallRecording(Base):
    __tablename__ = "call_recordings"
    __table_args__ = (
        # Partial unique index to prevent duplicate source_url imports per organization
        # Only applies when source_url is NOT NULL (direct uploads don't have source_url)
        Index('ix_call_recordings_org_source_url', 'org_id', 'source_url', unique=True,
              postgresql_where=text("source_url IS NOT NULL")),
    )

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=True)  # Custom name for the call
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source_type = Column(SQLEnum(CallSource), nullable=False)
    source_url = Column(String(500), nullable=True)
    bot_name = Column(String(100), default="HR Recorder")
    status = Column(SQLEnum(CallStatus), default=CallStatus.pending, index=True)
    progress = Column(Integer, default=0)  # 0-100 progress percentage
    progress_stage = Column(String(100), nullable=True)  # Current processing stage description
    duration_seconds = Column(Integer, nullable=True)
    audio_file_path = Column(String(500), nullable=True)
    # Байты аудио в БД (bytea) для долговечности на эфемерном диске прода. Только
    # для загруженных файлов до лимита (крупные/URL-звонки не дублируем: source_url
    # позволяет пере-скачать, а транскрипт/анализ и так в БД). Диск — fallback.
    audio_data = Column(LargeBinary, nullable=True)
    fireflies_transcript_id = Column(String(100), nullable=True, index=True)  # Fireflies transcript ID
    transcript = Column(Text, nullable=True)
    speakers = Column(JSON, nullable=True)  # [{speaker: "Speaker 1", start: 0.0, end: 5.2, text: "..."}, ...]
    summary = Column(Text, nullable=True)
    action_items = Column(JSON, nullable=True)
    key_points = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Smart context fields for AI analysis
    participant_roles = Column(JSON, nullable=True)  # {evaluator: {user_id, name}, target: {entity_id, name}, others: [...]}
    speaker_stats = Column(JSON, nullable=True)  # {"Speaker 1": {total_seconds: 900, role: "hr", user_id: 5}, ...}
    segments = Column(JSON, nullable=True)  # [{start, end, summary, key_quotes: [], speaker_breakdown: {}}]
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)

    organization = relationship("Organization", back_populates="calls")
    entity = relationship("Entity", back_populates="calls")
    owner = relationship("User", back_populates="owned_calls")


class ReportSubscription(Base):
    __tablename__ = "report_subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(SQLEnum(ReportType), nullable=False)
    delivery_method = Column(SQLEnum(DeliveryMethod), nullable=False)
    delivery_time = Column(Time, default=time(18, 0))
    filters = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="report_subscriptions")


class EntityAIConversation(Base):
    """AI conversation history for Entity (contact card)"""
    __tablename__ = "entity_ai_conversations"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    messages = Column(JSON, default=list)  # [{role, content, timestamp}]
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    entity = relationship("Entity", back_populates="ai_conversations")
    user = relationship("User", back_populates="entity_ai_conversations")


class EntityAnalysis(Base):
    """Saved AI analysis results for Entity"""
    __tablename__ = "entity_analyses"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    analysis_type = Column(String(50))  # full_analysis, red_flags, prediction, etc
    result = Column(Text, nullable=False)
    scores = Column(JSON, default=dict)  # {success_rate: 75, risk_level: "medium"}
    created_at = Column(DateTime, default=func.now())

    entity = relationship("Entity", back_populates="ai_analyses")
    user = relationship("User", back_populates="entity_analyses")


class ResourceType(str, enum.Enum):
    """Type of resource that can be shared"""
    chat = "chat"
    entity = "entity"
    call = "call"
    vacancy = "vacancy"  # Job vacancy
    project = "project"  # Project


class AccessLevel(str, enum.Enum):
    """Level of access granted"""
    view = "view"      # Can only view
    edit = "edit"      # Can view and edit
    full = "full"      # Full access (can share with others)


class SharedAccess(Base):
    """Shared access to resources (chats, entities, calls)"""
    __tablename__ = "shared_access"

    id = Column(Integer, primary_key=True)
    resource_type = Column(SQLEnum(ResourceType), nullable=False, index=True)
    resource_id = Column(Integer, nullable=False, index=True)  # ID of chat/entity/call/vacancy
    # Proper foreign keys for cascade delete - only one should be set based on resource_type
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=True, index=True)
    call_id = Column(Integer, ForeignKey("call_recordings.id", ondelete="CASCADE"), nullable=True, index=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=True, index=True)
    shared_by_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    access_level = Column(SQLEnum(AccessLevel), default=AccessLevel.view)
    note = Column(String(500), nullable=True)  # Optional note about sharing
    expires_at = Column(DateTime, nullable=True)  # Optional expiration
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('resource_type', 'resource_id', 'shared_with_id', 'shared_by_id', name='uq_shared_access_resource_user'),
        # Composite index for fast permission lookups
        Index('ix_shared_access_user_resource', 'shared_with_id', 'resource_type', 'resource_id'),
    )

    shared_by = relationship("User", foreign_keys=[shared_by_id])
    shared_with = relationship("User", foreign_keys=[shared_with_id])
    entity = relationship("Entity", foreign_keys=[entity_id])
    chat = relationship("Chat", foreign_keys=[chat_id])
    call = relationship("CallRecording", foreign_keys=[call_id])
    vacancy = relationship("Vacancy", foreign_keys=[vacancy_id])


class Invitation(Base):
    """User invitation for onboarding new members"""
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=True)  # Pre-filled email
    name = Column(String(255), nullable=True)  # Pre-filled name
    org_role = Column(SQLEnum(OrgRole), default=OrgRole.member)
    department_ids = Column(JSON, default=list)  # [{"id": 1, "role": "member"}, ...]
    invited_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime, nullable=True)  # When invitation expires
    used_at = Column(DateTime, nullable=True)  # When invitation was used
    used_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    organization = relationship("Organization")
    invited_by = relationship("User", foreign_keys=[invited_by_id])
    used_by = relationship("User", foreign_keys=[used_by_id])


class ImpersonationLog(Base):
    """Audit log for user impersonation sessions"""
    __tablename__ = "impersonation_logs"

    id = Column(Integer, primary_key=True)
    superadmin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    impersonated_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime, default=func.now(), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    user_agent = Column(String(512), nullable=True)

    superadmin = relationship("User", foreign_keys=[superadmin_id])
    impersonated_user = relationship("User", foreign_keys=[impersonated_user_id])


class CustomRole(Base):
    """Custom roles created by superadmin"""
    __tablename__ = "custom_roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    base_role = Column(String(20), nullable=False)  # inherits from: owner, admin, sub_admin, member
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)  # null = system-wide
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)

    # Unique constraint: name unique per org (or globally if org_id is null)
    __table_args__ = (
        UniqueConstraint('name', 'org_id', name='uq_custom_role_name_org'),
    )

    # Relationships
    organization = relationship("Organization")
    creator = relationship("User", foreign_keys=[created_by])
    permission_overrides = relationship("RolePermissionOverride", back_populates="role", cascade="all, delete-orphan")
    user_assignments = relationship("UserCustomRole", back_populates="role", cascade="all, delete-orphan")
    audit_logs = relationship("PermissionAuditLog", back_populates="role", cascade="all, delete-orphan")


class RolePermissionOverride(Base):
    """Permission overrides for custom roles"""
    __tablename__ = "role_permission_overrides"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("custom_roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission = Column(String(50), nullable=False)  # e.g. "can_delete_users", "can_share_resources"
    allowed = Column(Boolean, nullable=False)

    __table_args__ = (
        UniqueConstraint('role_id', 'permission', name='uq_role_permission'),
    )

    # Relationships
    role = relationship("CustomRole", back_populates="permission_overrides")


class PermissionAuditLog(Base):
    """Audit log for permission changes"""
    __tablename__ = "permission_audit_logs"

    id = Column(Integer, primary_key=True)
    changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    role_id = Column(Integer, ForeignKey("custom_roles.id", ondelete="CASCADE"), nullable=True)
    action = Column(String(20), nullable=False)  # 'create', 'update', 'delete'
    permission = Column(String(50), nullable=True)
    old_value = Column(Boolean, nullable=True)
    new_value = Column(Boolean, nullable=True)
    details = Column(JSON, nullable=True)  # additional context
    created_at = Column(DateTime, default=func.now(), index=True)

    # Relationships
    changed_by_user = relationship("User", foreign_keys=[changed_by])
    role = relationship("CustomRole", back_populates="audit_logs")


class UserCustomRole(Base):
    """Assignment of custom roles to users"""
    __tablename__ = "user_custom_roles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("custom_roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='uq_user_custom_role'),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    role = relationship("CustomRole", back_populates="user_assignments")
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])


class Vacancy(Base):
    """Job vacancy/position opening"""
    __tablename__ = "vacancies"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)  # Job requirements
    responsibilities = Column(Text, nullable=True)  # Key responsibilities
    salary_min = Column(Integer, nullable=True)  # Minimum salary
    salary_max = Column(Integer, nullable=True)  # Maximum salary
    salary_currency = Column(String(10), default="RUB")  # Currency code
    location = Column(String(255), nullable=True)  # Work location
    employment_type = Column(String(50), nullable=True)  # full-time, part-time, contract, remote
    experience_level = Column(String(50), nullable=True)  # junior, middle, senior, lead
    status = Column(SQLEnum(VacancyStatus), default=VacancyStatus.pending_review, index=True)
    priority = Column(Integer, default=0)  # 0=normal, 1=high, 2=urgent
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)  # Additional custom fields
    # Visibility
    visible_to_all = Column(Boolean, default=False, server_default="false")  # Visible to all org members
    # Hiring team
    hiring_manager_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Dates
    published_at = Column(DateTime, nullable=True)
    closes_at = Column(DateTime, nullable=True)  # Application deadline
    deleted_at = Column(DateTime, nullable=True, index=True)  # Мягкое удаление: NULL = активна
    # Точка отсчёта «серии»: момент последнего переоткрытия (closed→open). Отклики,
    # чей last_stage_change_at < reopened_at, показываются как «В предыдущих сериях».
    # NAIVE UTC (как все таймстемпы тут), иначе сравнение с naive-колонками ломается.
    reopened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Assignment workflow
    assigned_to = Column(JSON, default=list)  # List of recruiter user IDs assigned to this vacancy
    assigned_to_all = Column(Boolean, default=False, server_default="false")  # If True, visible to all HR users

    # Funnel customization
    custom_stages = Column(JSON, nullable=True)  # Custom stage labels/order per funnel
    kanban_card_fields = Column(JSON, nullable=True)  # Which fields to show on kanban cards

    # Vector embedding for similarity search (OpenAI text-embedding-3-small: 1536 dimensions)
    # Note: embedding column is added via migration if pgvector is available
    embedding_updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # Composite index for filtering vacancies by org and status (common list query)
        Index('ix_vacancy_org_status', 'org_id', 'status'),
        # Composite index for filtering by department
        Index('ix_vacancy_dept_status', 'department_id', 'status'),
    )

    # Relationships
    organization = relationship("Organization")
    department = relationship("Department")
    hiring_manager = relationship("User", foreign_keys=[hiring_manager_id])
    creator = relationship("User", foreign_keys=[created_by])
    applications = relationship("VacancyApplication", back_populates="vacancy", cascade="all, delete-orphan")


class VacancyApplication(Base):
    """Candidate application to a vacancy (pipeline tracking)"""
    __tablename__ = "vacancy_applications"

    id = Column(Integer, primary_key=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(SQLEnum(ApplicationStage), default=ApplicationStage.applied, index=True)  # HR pipeline default (using 'applied' which exists in DB enum)
    stage_order = Column(Integer, default=0)  # For custom ordering within a stage
    rating = Column(Integer, nullable=True)  # 1-5 rating
    notes = Column(Text, nullable=True)  # Internal notes about candidate
    rejection_reason = Column(String(255), nullable=True)  # Reason for rejection
    source = Column(String(100), nullable=True)  # How candidate was sourced (linkedin, referral, etc)
    # Interview scheduling
    next_interview_at = Column(DateTime, nullable=True)
    # AI Compatibility Score (cached from AI scoring service)
    # Format: {overall_score, skills_match, experience_match, salary_match, culture_fit,
    #          strengths: [], weaknesses: [], recommendation, summary, key_factors: []}
    compatibility_score = Column(JSON, nullable=True)
    # Interview summary — required before moving to practice stage
    interview_summary = Column(Text, nullable=True)
    # Timestamps for analytics
    applied_at = Column(DateTime, default=func.now())
    last_stage_change_at = Column(DateTime, default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    # Закреплённая запись ленты этой воронки (24.09.2026): ключ строки —
    # "e:<id>" (перевод) или "n:<uuid>" (комментарий). ОДИН закреп на воронку:
    # кандидат в двух воронках получает два, каждый в своём блоке карточки.
    pinned_entry_key = Column(String(64), nullable=True)

    __table_args__ = (
        # One application per candidate per vacancy
        UniqueConstraint('vacancy_id', 'entity_id', name='uq_vacancy_application'),
        # Index for kanban queries
        Index('ix_vacancy_application_stage', 'vacancy_id', 'stage'),
        # Composite index for entity lookup across vacancies
        Index('ix_vacancy_application_entity_vacancy', 'entity_id', 'vacancy_id'),
    )

    # Relationships
    vacancy = relationship("Vacancy", back_populates="applications")
    entity = relationship("Entity")
    created_by_user = relationship("User", foreign_keys=[created_by])


class ApplicationCoRecruiter(Base):
    """Со-рекрутёры заявки: кандидат в ЭТОЙ воронке «принадлежит» также этим HR,
    помимо created_by. Нужно для ОБЩЕЙ воронки — один кандидат может быть у
    нескольких рекрутёров сразу (у каждого в его фильтре, свой чип «HR: Имя»).

    ОТДЕЛЬНАЯ ТАБЛИЦА, а НЕ колонка на vacancy_applications: create_all создаёт
    недостающие ТАБЛИЦЫ на старте (init_database), но НЕ добавляет колонки — новая
    колонка на проде не появлялась и роняла все SELECT (инцидент co_recruiter_ids).
    Таблица же появится сама, без ручной миграции.
    """
    __tablename__ = "application_co_recruiters"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("vacancy_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('application_id', 'user_id', name='uq_app_co_recruiter'),
    )


class DepartmentFeature(Base):
    """Controls which features are available to which departments.

    Features can be enabled/disabled at:
    - Organization level (department_id is NULL): applies to all departments as default
    - Department level (department_id is set): overrides org-wide setting for specific department

    Feature names include: 'vacancies', 'ai_analysis', 'calls', etc.
    Default features (chats, contacts, dashboard) are always available.
    """
    __tablename__ = "department_features"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)
    # If department_id is NULL, it's an org-wide default
    feature_name = Column(String(50), nullable=False)  # "vacancies", "calls", "ai_analysis", etc
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'department_id', 'feature_name', name='uq_dept_feature'),
        Index('ix_department_features_lookup', 'org_id', 'feature_name'),
    )

    organization = relationship("Organization")
    department = relationship("Department")


class FeatureAuditLog(Base):
    """Audit log for feature access changes.

    Tracks who changed feature access settings, when, and what was changed.
    Used for compliance and debugging access issues.
    """
    __tablename__ = "feature_audit_logs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    feature_name = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)  # 'enable', 'disable', 'delete'
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    # NULL department_id means org-wide change
    old_value = Column(Boolean, nullable=True)  # Previous enabled state
    new_value = Column(Boolean, nullable=True)  # New enabled state
    details = Column(JSON, nullable=True)  # Additional context (e.g., affected department names)
    created_at = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index('ix_feature_audit_logs_lookup', 'org_id', 'feature_name', 'created_at'),
    )

    # Relationships
    organization = relationship("Organization")
    changed_by_user = relationship("User", foreign_keys=[changed_by])
    department = relationship("Department")


class EntityFile(Base):
    """Files attached to an entity (resumes, certificates, etc.)"""
    __tablename__ = "entity_files"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    file_type = Column(SQLEnum(EntityFileType), default=EntityFileType.other)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)  # Legacy disk path (optional now)
    file_data = Column(LargeBinary, nullable=True)  # File content stored in DB (bytea)
    file_size = Column(Integer, nullable=True)  # Size in bytes
    mime_type = Column(String(100), nullable=True)
    description = Column(String(500), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        # Composite index for listing files by entity and type
        Index('ix_entity_file_entity_type', 'entity_id', 'file_type'),
    )

    # Relationships
    entity = relationship("Entity", back_populates="files")
    organization = relationship("Organization")
    uploader = relationship("User", back_populates="uploaded_files")


class RefreshToken(Base):
    """Refresh tokens for secure session management.

    Refresh tokens are stored with hashed values for security.
    They allow obtaining new access tokens without re-authentication.
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)  # SHA-256 hash of token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_name = Column(String(255), nullable=True)  # e.g., "Chrome on Windows", "Mobile App"
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    revoked_at = Column(DateTime, nullable=True)  # NULL = not revoked, set = revoked
    # Момент РОТАЦИИ (revoked именно из-за обновления, а не logout/security). Нужен,
    # чтобы отличить доброкачественную гонку мультивкладок (один и тот же токен
    # обновили секунду назад) от настоящего повторного использования украденного
    # токена. NULL = ревокнут не ротацией (logout / revoke-all) или не ревокнут.
    rotated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_refresh_tokens_user_expires', 'user_id', 'expires_at'),
    )

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")


class ParseJobStatus(str, enum.Enum):
    """Status of a background parsing job"""
    pending = "pending"        # Job created, waiting to be processed
    processing = "processing"  # Currently being parsed
    completed = "completed"    # Successfully parsed and entity created
    failed = "failed"          # Parsing failed


class ParseJob(Base):
    """Background parsing job for resumes.

    Allows users to start parsing without waiting for completion.
    The job runs in the background and creates an entity when done.
    """
    __tablename__ = "parse_jobs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(SQLEnum(ParseJobStatus), default=ParseJobStatus.pending, index=True)

    # File info (stored temporarily for processing)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)  # Temporary file path
    file_size = Column(Integer, nullable=True)

    # Result
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    error_message = Column(Text, nullable=True)

    # Progress tracking
    progress = Column(Integer, default=0)  # 0-100 percentage
    progress_stage = Column(String(100), nullable=True)  # "Extracting text", "Parsing with AI", etc.

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_parse_job_user_status', 'user_id', 'status'),
        Index('ix_parse_job_org_created', 'org_id', 'created_at'),
    )

    # Relationships
    organization = relationship("Organization")
    user = relationship("User")
    entity = relationship("Entity")


class PrometheusReviewCache(Base):
    """Cached AI-generated Prometheus detailed reviews for contacts.

    Stores the full response (intern data, deterministic review, AI detailed review,
    achievements) so that repeated visits to the Prometheus tab do not re-generate
    the review.  Regeneration is triggered manually via force=true.
    """
    __tablename__ = "prometheus_review_cache"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    review_data = Column(JSON, nullable=False)  # Full DetailedReviewResponse payload
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    entity = relationship("Entity")


# ==================== PROJECT MANAGEMENT ====================

class Project(Base):
    """Project tracked in the PM module"""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(300), nullable=False)
    prefix = Column(String(10), nullable=True)  # Short code like "PM", "HR", "XERO" for task IDs
    task_counter = Column(Integer, default=0)    # Auto-increment counter for task numbers
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(ProjectStatus, name="projectstatus", create_constraint=False, native_enum=False), nullable=False, default=ProjectStatus.planning)  # stores slug strings from ProjectStatusDef
    priority = Column(Integer, default=1)  # 0=low, 1=normal, 2=high, 3=critical
    client_name = Column(String(300), nullable=True)
    progress_percent = Column(Integer, default=0)  # 0-100
    progress_mode = Column(String(10), default="auto")  # "auto" or "manual"
    # Готовность продукта ставит РУКАМИ разработчик (решение владельца
    # 28.09.2026): доля закрытых задач врёт — можно закрыть двадцать мелких и
    # не сдвинуться. Помним, кто и когда оценивал, чтобы напоминать про старые.
    progress_updated_at = Column(DateTime, nullable=True)
    progress_updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    start_date = Column(DateTime, nullable=True)
    target_date = Column(DateTime, nullable=True)
    predicted_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)
    color = Column(String(20), nullable=True)  # hex color for UI
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_project_org_status', 'org_id', 'status'),
        Index('ix_project_dept_status', 'department_id', 'status'),
    )

    organization = relationship("Organization")
    department = relationship("Department")
    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    milestones = relationship("ProjectMilestone", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("ProjectTask", back_populates="project", cascade="all, delete-orphan")
    task_statuses = relationship("ProjectTaskStatus", back_populates="project", cascade="all, delete-orphan", order_by="ProjectTaskStatus.sort_order")


class ProjectStatusDef(Base):
    """Custom project status definitions per organization"""
    __tablename__ = "project_status_defs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)
    color = Column(String(20), default="#6366f1")
    sort_order = Column(Integer, default=0)
    is_done = Column(Boolean, default=False)  # marks project as "completed" for health calc
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'slug', name='uq_project_status_def_slug'),
        Index('ix_psd_org_sort', 'org_id', 'sort_order'),
    )

    organization = relationship("Organization")


class ProjectMember(Base):
    """User assigned to a project with a specific role"""
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(SQLEnum(ProjectRole, name="projectrole", create_constraint=False, native_enum=False), nullable=False, default=ProjectRole.developer)
    allocation_percent = Column(Integer, default=100)  # 0-100, how much of their time
    joined_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
    )

    project = relationship("Project", back_populates="members")
    user = relationship("User")


class ProjectTaskStatus(Base):
    """Custom task status definitions per project"""
    __tablename__ = "project_task_statuses"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g. "In Review", "Selected for Dev"
    slug = Column(String(100), nullable=False)   # e.g. "in_review", "selected_for_dev"
    color = Column(String(20), default="#6366f1") # hex color
    sort_order = Column(Integer, default=0)
    is_done = Column(Boolean, default=False)     # marks tasks as "completed" for progress calc
    is_default = Column(Boolean, default=False)  # default status for new tasks
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('project_id', 'slug', name='uq_project_status_slug'),
        Index('ix_pts_project_sort', 'project_id', 'sort_order'),
    )

    project = relationship("Project", back_populates="task_statuses")


class ProjectMilestone(Base):
    """Development phase/stage within a project"""
    __tablename__ = "project_milestones"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    target_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    project = relationship("Project", back_populates="milestones")
    tasks = relationship("ProjectTask", back_populates="milestone")


class ProjectTask(Base):
    """Task within a project, optionally tied to a milestone"""
    __tablename__ = "project_tasks"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_number = Column(Integer, nullable=True)  # Sequential number within project, e.g. 1, 2, 3
    milestone_id = Column(Integer, ForeignKey("project_milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(TaskStatus, name="taskstatus", create_constraint=False, native_enum=False), nullable=False, default=TaskStatus.backlog)
    priority = Column(Integer, default=1)  # 0=low, 1=normal, 2=high, 3=critical
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    estimated_hours = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    sort_order = Column(Integer, default=0)
    tags = Column(JSON, default=list)
    parent_task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    blocker_id = Column(Integer, ForeignKey("blockers.id", ondelete="SET NULL"), nullable=True, index=True)  # Если задача создана из блокера — ссылка на него
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Откуда задача: бот из сообщения в чате или человек руками. Без этого
    # нельзя было ни отличить «наработки бота» от настоящих задач, ни понять,
    # из какого сообщения он их выдумал (жалоба владельца 25.09.2026).
    created_by_bot = Column(Boolean, default=False, server_default="false", index=True)
    source_chat_id = Column(BigInteger, nullable=True)      # telegram chat id
    source_message = Column(Text, nullable=True)            # текст-первоисточник
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_task_project_status', 'project_id', 'status'),
        Index('ix_task_assignee_status', 'assignee_id', 'status'),
    )

    project = relationship("Project", back_populates="tasks")
    milestone = relationship("ProjectMilestone", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id])
    creator = relationship("User", foreign_keys=[created_by])
    time_logs = relationship("TaskTimeLog", back_populates="task", cascade="all, delete-orphan")
    subtasks = relationship("ProjectTask", back_populates="parent_task", cascade="all, delete-orphan")
    parent_task = relationship("ProjectTask", remote_side=[id], back_populates="subtasks")
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan", order_by="TaskComment.created_at")
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete-orphan", order_by="TaskAttachment.created_at")


class PendingTaskSuggestion(Base):
    """Задачи, которые бот предложил создать и ждёт «Создать» в чате.

    Бот больше не заводит задачи молча: он присылает разбор сообщения с
    кнопками. Готовый разбор хранится здесь, потому что в callback_data
    Telegram помещается только 64 байта (решение владельца 25.09.2026).
    Отклонённые не удаляем — это материал для настройки распознавания.
    """
    __tablename__ = "pending_task_suggestions"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=True, index=True)   # telegram chat id
    message_text = Column(Text, nullable=False)
    payload = Column(JSON, default=dict)                      # разобранные задачи
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # pending → created / rejected / expired
    status = Column(String(20), default="pending", index=True)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())


class TaskTimeLog(Base):
    """Light effort tracking — hours spent on a task"""
    __tablename__ = "task_time_logs"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hours = Column(Integer, nullable=False)  # whole hours
    date = Column(DateTime, nullable=False)
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())

    task = relationship("ProjectTask", back_populates="time_logs")
    user = relationship("User")


class TaskComment(Base):
    """Comment on a project task"""
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    edited_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    task = relationship("ProjectTask", back_populates="comments")
    user = relationship("User")


class TaskAttachment(Base):
    """File attachment on a project task"""
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # bytes
    content_type = Column(String(200), nullable=True)
    # Legacy: путь к локальному файлу. На Railway /tmp эфемерный и стирается
    # при каждом редеплое — поэтому новые вложения храним в file_data (БД).
    storage_path = Column(String(1000), nullable=True)
    file_data = Column(LargeBinary, nullable=True)  # содержимое файла в БД (persistent)
    created_at = Column(DateTime, default=func.now())

    task = relationship("ProjectTask", back_populates="attachments")
    user = relationship("User")


class ProjectCustomField(Base):
    """Custom field definition for a project"""
    __tablename__ = "project_custom_fields"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)      # "Dev Cost", "Sprint", "Story Points"
    field_type = Column(String(30), nullable=False)  # "text", "number", "currency", "select", "date", "checkbox"
    options = Column(JSON, default=list)              # for "select" type: ["Option A", "Option B"]
    currency = Column(String(10), nullable=True)      # for "currency" type: "USD", "RUB"
    sort_order = Column(Integer, default=0)
    is_required = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    project = relationship("Project")

    __table_args__ = (
        Index('ix_cf_project', 'project_id', 'sort_order'),
    )


class TaskCustomFieldValue(Base):
    """Value of a custom field on a specific task"""
    __tablename__ = "task_custom_field_values"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id = Column(Integer, ForeignKey("project_custom_fields.id", ondelete="CASCADE"), nullable=False, index=True)
    value = Column(Text, nullable=True)  # stored as string, parsed by type

    __table_args__ = (
        UniqueConstraint('task_id', 'field_id', name='uq_task_field_value'),
    )

    task = relationship("ProjectTask")
    field = relationship("ProjectCustomField")


# ============================================================
# SATURN INTEGRATION (Coolify-based deployment platform)
# ============================================================

class SaturnProject(Base):
    __tablename__ = "saturn_projects"

    id = Column(Integer, primary_key=True)
    saturn_uuid = Column(String(100), unique=True, nullable=False, index=True)
    saturn_id = Column(Integer)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False)
    enceladus_project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    enceladus_project = relationship("Project")


class SaturnApplication(Base):
    __tablename__ = "saturn_applications"

    id = Column(Integer, primary_key=True)
    saturn_uuid = Column(String(100), unique=True, nullable=False, index=True)
    saturn_project_id = Column(Integer, ForeignKey("saturn_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    fqdn = Column(String(500), nullable=True)
    status = Column(String(100), nullable=True)  # running:healthy, exited:unhealthy, etc
    build_pack = Column(String(50), nullable=True)
    git_repository = Column(String(500), nullable=True)
    git_branch = Column(String(200), nullable=True)
    environment_name = Column(String(100), nullable=True)  # development/uat/production
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    saturn_project = relationship("SaturnProject")


class SaturnSyncLog(Base):
    __tablename__ = "saturn_sync_logs"

    id = Column(Integer, primary_key=True)
    sync_type = Column(String(20), nullable=False)  # "full", "webhook", "manual"
    projects_synced = Column(Integer, default=0)
    apps_synced = Column(Integer, default=0)
    errors = Column(JSON, default=list)
    created_at = Column(DateTime, default=func.now())


# ============================================================
# NOTIFICATIONS
# ============================================================

class Notification(Base):
    """In-app notification for users"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # task_assigned, deadline_tomorrow, comment_added
    title = Column(String(300), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)  # e.g. /projects/1/tasks/5
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    # Поллинг: WHERE user_id=? ORDER BY is_read, created_at DESC LIMIT 50 каждые 25с
    # на пользователя. Композитный индекс убирает per-user сортировку под нагрузкой.
    __table_args__ = (
        Index("ix_notification_user_created", "user_id", "created_at"),
    )

    user = relationship("User")


# ============================================================
# FORM CONSTRUCTOR
# ============================================================

class FormTemplate(Base):
    """Custom form template created by recruiter"""
    __tablename__ = "form_templates"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    slug = Column(String(100), unique=True, nullable=False)  # for public URL
    is_active = Column(Boolean, default=True)
    is_template = Column(Boolean, default=False, nullable=False)
    fields = Column(JSON, default=list)  # Array of field definitions
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    organization = relationship("Organization")
    vacancy = relationship("Vacancy")
    creator = relationship("User", foreign_keys=[created_by])
    submissions = relationship("FormSubmission", back_populates="form", cascade="all, delete-orphan")


class FormSubmission(Base):
    """A candidate's submission of a form"""
    __tablename__ = "form_submissions"

    id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    data = Column(JSON, nullable=False)  # {field_id: value, ...}
    dispatch_id = Column(Integer, ForeignKey("form_dispatches.id", ondelete="SET NULL"), nullable=True, index=True)
    # Вопросы анкеты на момент ответа (поля шаблона потом могут поменяться).
    fields_snapshot = Column(JSON, nullable=True)
    submitted_at = Column(DateTime, default=func.now())

    form = relationship("FormTemplate", back_populates="submissions")
    entity = relationship("Entity")


class FormVacancy(Base):
    """Many-to-many: one form can be linked to multiple vacancies"""
    __tablename__ = "form_vacancy"

    id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('form_id', 'vacancy_id', name='uq_form_vacancy'),
    )

    form = relationship("FormTemplate")
    vacancy = relationship("Vacancy")


class FormDispatch(Base):
    """Анкета, отправленная конкретному существующему кандидату по личной ссылке."""
    __tablename__ = "form_dispatches"

    id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(20), default="sent")            # sent | opened | submitted
    submission_id = Column(Integer, ForeignKey("form_submissions.id", ondelete="SET NULL", use_alter=True), nullable=True)
    seen_by_recruiter = Column(Boolean, default=False)     # управляет бейджем на кнопке
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    opened_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)

    form = relationship("FormTemplate")
    entity = relationship("Entity")


class CandidateShareLink(Base):
    """Публичная ссылка предпросмотра кандидата для заказчика (без авторизации).

    Токен неугадываемый, живёт ограниченно (expires_at, 30 дней) — страница
    показывает только ФИО/контакты/резюме/комментарии HR, без CRM-интерфейса.
    """
    __tablename__ = "candidate_share_links"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=False)

    entity = relationship("Entity")


# ============================================================
# EMPLOYEE MANAGEMENT (Personal Cabinet, Leave Counter, Reminders)
# ============================================================

class OrgUnit(Base):
    """HR org-chart unit — изолировано от рекрутингового Department."""
    __tablename__ = "org_units"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("org_units.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    color = Column(String(20), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class Employee(Base):
    """Employee record — created when candidate transitions to staff"""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)  # link to candidate record
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    org_unit_id = Column(Integer, ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True)
    manager_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)

    # Personal info
    position = Column(String(300), nullable=True)
    phone = Column(String(50), nullable=True)
    telegram_username = Column(String(200), nullable=True)

    # Employment dates
    practice_start_date = Column(DateTime, nullable=True)
    department_start_date = Column(DateTime, nullable=True)  # when moved to dept (first working day)
    probation_end_date = Column(DateTime, nullable=True)     # auto: department_start_date + 3 months
    one_year_date = Column(DateTime, nullable=True)          # auto: department_start_date + 1 year

    # Leave counters
    vacation_days_total = Column(Integer, default=0)         # accumulated vacation days
    vacation_days_used = Column(Integer, default=0)
    # Лимиты на рабочий год; умолчание — services/leave_limits.py (7 / 2), HR правит в карточке
    sick_days_total = Column(Integer, default=7)
    sick_days_used = Column(Integer, default=0)
    family_leave_days_total = Column(Integer, default=2)
    family_leave_days_used = Column(Integer, default=0)

    # Contract
    nda_signed = Column(Boolean, default=False)
    nda_signed_at = Column(DateTime, nullable=True)
    contract_signed = Column(Boolean, default=False)
    contract_signed_at = Column(DateTime, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    dismissed_at = Column(DateTime, nullable=True)
    dismissal_reason = Column(Text, nullable=True)

    # Metadata
    extra_data = Column(JSON, default=dict)  # wallet, passport hash, etc
    # Зашифрованный (Fernet) скан паспорта в БД — диск на проде эфемерный, иначе
    # PII теряется при редеплое. Метаданные (имя/тип) лежат в extra_data["passport"].
    passport_data = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User")
    organization = relationship("Organization")
    department = relationship("Department")
    entity = relationship("Entity")
    leave_requests = relationship("LeaveRequest", back_populates="employee", cascade="all, delete-orphan")


class LeaveRequest(Base):
    """Employee leave/vacation request"""
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(30), nullable=False)  # vacation, sick, family_leave, bereavement
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    days = Column(Integer, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    employee = relationship("Employee", back_populates="leave_requests")
    approver = relationship("User", foreign_keys=[approved_by])


class EmployeeDocument(Base):
    """Файл, загруженный в карточку сотрудника (вкладка «Документы»)."""
    __tablename__ = "employee_documents"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    path = Column(String, nullable=False)  # путь к зашифрованному файлу на диске (legacy)
    # Зашифрованные байты файла в БД (Fernet, как на диске): диск на проде эфемерный,
    # без этого документ сотрудника теряется при редеплое. Диск остаётся как fallback.
    file_data = Column(LargeBinary, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# DOCUMENT SIGNING (Templates, Signed Documents, Canvas Signature)
# ============================================================

class DocumentTemplate(Base):
    """Template for documents like NDA, contracts"""
    __tablename__ = "document_templates"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    variables = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    organization = relationship("Organization")


class SignedDocument(Base):
    """A signed document instance"""
    __tablename__ = "signed_documents"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("document_templates.id", ondelete="SET NULL"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    content_rendered = Column(Text, nullable=False)
    signature_data = Column(Text, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    signer_ip = Column(String(50), nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=func.now())

    template = relationship("DocumentTemplate")
    employee = relationship("Employee")


class RecruiterBonus(Base):
    """Tracks recruiter bonus accruals per candidate"""
    __tablename__ = "recruiter_bonuses"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    recruiter_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    direction = Column(String(30), nullable=False)  # "traffic" or "development"
    stage = Column(String(30), nullable=False)  # "practice", "department", "probation"
    amount = Column(Integer, nullable=False)  # bonus amount in USD
    is_paid = Column(Boolean, default=False)
    paid_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    organization = relationship("Organization")
    recruiter = relationship("User", foreign_keys=[recruiter_id])
    entity = relationship("Entity")


class StageTransition(Base):
    """Audit log for every stage/status change of a candidate application."""
    __tablename__ = "stage_transitions"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("vacancy_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    from_stage = Column(String(50), nullable=True)  # null for initial creation
    to_stage = Column(String(50), nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    # Правка комментария к переводу (24.09.2026). В строке ленты остаётся тот,
    # кто написал, и время написания; кто и когда правил — показывается
    # подсказкой при наведении, поэтому нужны ОБА поля, а не только время.
    edited_at = Column(DateTime, nullable=True)
    edited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    application = relationship("VacancyApplication")
    entity = relationship("Entity")
    changed_by_user = relationship("User", foreign_keys=[changed_by])
    edited_by_user = relationship("User", foreign_keys=[edited_by])


# ============================================================
# TIME OFF & BLOCKERS
# ============================================================

class TimeOffRequest(Base):
    __tablename__ = "time_off_requests"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(SQLEnum(TimeOffType), default=TimeOffType.vacation)
    status = Column(SQLEnum(TimeOffStatus), default=TimeOffStatus.pending)
    date_from = Column(DateTime, nullable=False)
    date_to = Column(DateTime, nullable=False)
    reason = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reject_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('ix_timeoff_org_status', 'org_id', 'status'),
        Index('ix_timeoff_user_status', 'user_id', 'status'),
    )


class Blocker(Base):
    __tablename__ = "blockers"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(Text, nullable=False)
    status = Column(SQLEnum(BlockerStatus), default=BlockerStatus.open)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolve_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('ix_blocker_org_status', 'org_id', 'status'),
    )


# ==================== Tags / Labels ====================

# Many-to-many association table: Entity <-> EntityTag
entity_tag_association = Table(
    "entity_tags",
    Base.metadata,
    Column("entity_id", Integer, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("entity_tags_catalog.id", ondelete="CASCADE"), primary_key=True),
    # Яркий ярлык у ФИО кандидата (бывшие extra_data.headline_tags). Флаг на
    # СВЯЗИ, а не на метке: «перфомер» висел у конкретного Руслана, и если бы
    # признак жил в справочнике, та же метка у другого кандидата сразу полезла
    # бы ему к имени. Одна метка — у кого-то ярлык, у кого-то обычная.
    Column("show_at_name", Boolean, nullable=False, server_default="false", default=False),
    extend_existing=True,
)


class EntityTag(Base):
    """Tag/label that can be attached to entities (candidates, clients, etc.)"""
    __tablename__ = "entity_tags_catalog"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # 40, а не 20: палитра шлёт CSS-переменные вида var(--hf-status-purple).
    color = Column(String(40), nullable=False, default="#3b82f6")
    # 'general' | 'sourcer'. Сорсер — внешний человек без доступа в систему,
    # который привёл кандидата; помечаем метку, чтобы отделить её от обычных
    # ярлыков в аналитике. Enum в БД намеренно не заводим: значений мало и
    # добавлять новые через ALTER TYPE дороже, чем через строку.
    kind = Column(String(20), nullable=False, default="general", server_default="general")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    # «Удалена за ненадобностью»: метка пропадает из списка выбора, но остаётся
    # на карточках тех, кому уже проставлена. Настоящий DELETE тут не подходит —
    # у entity_tags стоит ondelete=CASCADE и снёс бы метку у всех разом.
    archived_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('org_id', 'name', name='uq_entity_tag_org_name'),
        Index('ix_entity_tag_org', 'org_id'),
    )

    entities = relationship("Entity", secondary="entity_tags", back_populates="tag_objects")


# Теги у ФИО кандидата («+ тег» рядом с именем) — ОТДЕЛЬНО от меток (21.09.2026).
# До этого тег был той же меткой из entity_tags_catalog с флагом show_at_name на
# связи. Метки теперь — только сорсеры (кто привёл кандидата), а у тегов будет
# своя задача, поэтому справочники разведены: свой каталог и своя связь.
entity_name_tag_association = Table(
    "entity_name_tags",
    Base.metadata,
    Column("entity_id", Integer, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("entity_name_tags_catalog.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True,
)


class NameTag(Base):
    """Тег у ФИО кандидата. Справочник организации, как у меток."""
    __tablename__ = "entity_name_tags_catalog"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(40), nullable=False, default="var(--hf-status-pink)")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    # Скрыт из списка выбора, но остаётся у кандидатов (как у меток).
    archived_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('org_id', 'name', name='uq_entity_name_tag_org_name'),
    )


class BoardDepartment(Base):
    """Отдел на доске «Статусы» — СВОЙ справочник, не оргструктура Enceladus.

    Названия совпадают, а сущности разные (решение владельца 23.09.2026):
    в оргструктуре (``departments``) у отдела есть участники, руководители и
    права доступа, а здесь — просто список, куда HR раскладывает людей на
    доске. Поэтому у доски отдельная таблица: правки на доске не должны
    трогать оргструктуру и наоборот.
    """
    __tablename__ = "staff_board_departments"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # Скрыт с доски: отдел остаётся в базе и у людей, просто не мозолит глаза
    # в списке и в выборе. Удаления нет намеренно (решение владельца
    # 23.09.2026): неактуальные отделы прячут, а не сносят.
    hidden_at = Column(DateTime, nullable=True)
    # Иерархия отделов (решение владельца 30.09.2026). Родительские — это
    # песочницы (SANDBOX, SANDBOX MOBILE, SANDBOX R&D): туда попадают с
    # практики. Дочерние — команды (Facebook, Google, SEO…), куда человека
    # переводят ИЗ песочницы, оставаясь в ней же.
    # sandbox — песочница (родительский отдел), team — команда внутри неё.
    # Роль отдела задаётся явно: «команда без выбранной песочницы» и песочница
    # по одному пустому parent_id не отличаются.
    kind = Column(String(10), default="team", server_default="team")
    # sandbox — песочница (родительский отдел), team — команда внутри неё.
    # Роль задаётся явно: «команду без выбранной песочницы» и песочницу по
    # одному пустому parent_id не отличить.
    kind = Column(String(10), default="team", server_default="team")
    parent_id = Column(Integer, ForeignKey("staff_board_departments.id", ondelete="SET NULL"), nullable=True, index=True)
    # Кому отдел виден: all — всем HR, admins — только владельцам и админам,
    # custom — перечисленным в visible_to. Юниты видят Мария и Настя, а
    # рекрутёрам нужны только песочницы (Мария, 30.09.2026).
    visibility = Column(String(10), default="all", server_default="all")
    visible_to = Column(JSON, default=list)   # user_id, когда visibility = custom
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())


class BoardPlacement(Base):
    """Человек в отделе на доске «Статусы».

    Кандидат в базе ОДИН, а мест у него может быть несколько: пришёл на
    практику в SANDBOX, перешёл в Facebook — и остался в обоих (решение
    владельца 30.09.2026). Поэтому дублируем не карточку кандидата, а ссылку
    на него: строка доски = назначение.

    Что принадлежит человеку (статус, HR, сорсер, должность, Telegram), живёт
    в самой карточке и одинаково во всех отделах: уволили в Facebook — уволен
    и в песочнице, потому что это один и тот же объект. Что принадлежит
    отделу — дата выхода в него и вехи 2 недели / 1 / 3 / 12 месяцев — лежит
    здесь, в extra, у каждого назначения своё.
    """
    __tablename__ = "staff_board_placements"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("staff_board_departments.id", ondelete="CASCADE"), nullable=False, index=True)
    # Даты и отметки ЭТОГО отдела: ключи те же, что раньше лежали в карточке
    # кандидата (department_transfer_date, w2_date, m1_done…) — так код доски
    # читает их одинаково и для старых карточек, и для новых назначений.
    extra = Column(JSON, default=dict)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("entity_id", "department_id", name="uq_placement_entity_dept"),
    )


class BoardStatusView(Base):
    """Какие секции доски «Статусы» показывать — СВОИ у каждого и у отдела.

    Мит 07.10.2026: «у Маши в отделе SANDBOX видны „Перевёлся“ и „Практика“, а
    у Насти только „Уволился“ — они сами выбрали эти статусы». Поэтому ключ
    составной: пользователь + вкладка доски (``scope_key`` — ``all``, ``none``
    для «Без отдела» или id отдела строкой).

    Записи нет — показываем ВСЕ секции: так ведут себя все, кто ничего не
    настраивал, и новый отдел не открывается пустым.
    """
    __tablename__ = "staff_board_status_views"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # «all» | «none» | id отдела строкой — вкладка, к которой относится набор.
    scope_key = Column(String(32), primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    statuses = Column(JSON, default=list)   # ключи секций: transferred, probation…
    # Ключи КОЛОНОК таблицы — «лист-вью не только по статусам, но и по
    # столбцам» (Мария, 08.10.2026). Пусто — показываем все колонки.
    column_keys = Column(JSON, default=list)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class BoardDepartmentOrder(Base):
    """Порядок отделов в колонке слева — СВОЙ у каждого пользователя.

    Мария раскладывает отделы так, как ей удобно смотреть, и этот порядок
    должен пережить перезагрузку и не мешать другим HR (решение владельца
    24.09.2026). Храним просто список id: отделы приходят и уходят, а
    «дырки» в списке безопасны — неизвестные id игнорируются.
    """
    __tablename__ = "staff_board_department_order"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    dept_ids = Column(JSON, default=list)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class EveningReport(Base):
    """Вечерний отчёт сотрудника за день.

    Присылается в рабочий чат с тегом «вечерний отчёт» в любом виде: текстом,
    файлом, голосовым, кружком или видео-демо. Голос и видео бот расшифровывает,
    файл разбирает — а дальше модель делает выжимку, чтобы владелец не читал
    три минуты сплошного текста (решение владельца 28.09.2026).
    """
    __tablename__ = "evening_reports"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    chat_id = Column(BigInteger, nullable=True, index=True)     # telegram chat id
    author_name = Column(String(255), nullable=True)            # как подписан в Telegram
    report_date = Column(Date, nullable=False, index=True)      # за какой день
    source_type = Column(String(20), nullable=False)            # text / voice / video / document
    raw_text = Column(Text, nullable=False)                     # расшифровка или текст файла
    summary = Column(JSON, default=dict)                        # выжимка: сделано, проблемы, план
    # Сообщение-отчёт и ответ бота: отчёт правят прямо в Telegram, и бот
    # пересобирает выжимку в своём же сообщении (просьба команды 28.09.2026).
    tg_message_id = Column(BigInteger, nullable=True, index=True)
    reply_message_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=func.now())


class DataMigrationMark(Base):
    """Отметка «одноразовая правка данных уже выполнена».

    Правки, которые нельзя повторять на каждом старте (например, удаление меток
    по списку имён: позже кто-то может завести метку с тем же именем осознанно),
    сверяются с этой таблицей и пишут сюда ключ после успешного прогона.
    """
    __tablename__ = "data_migration_marks"

    key = Column(String(100), primary_key=True)
    applied_at = Column(DateTime, default=func.now())


class DuplicatePairDecision(Base):
    """Решение рекрутёра по паре похожих кандидатов: «это разные люди».

    Раньше решение лежало в ``extra_data.dismissed_duplicate_ids`` у каждой из
    двух анкет и терялось при объединении: выживала ``extra_data`` одной стороны,
    а ссылки на влитую анкету у соседей указывали в пустоту — пара всплывала снова.
    Здесь пара хранится один раз (меньший id — в ``entity_a_id``), а при слиянии
    переписывается на выжившую карточку (``services/duplicate_decisions.py``).
    """
    __tablename__ = "duplicate_pair_decisions"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_a_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_b_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String(20), nullable=False, default="different")
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("entity_a_id", "entity_b_id", name="uq_duplicate_pair"),
    )


class DeletedEntity(Base):
    """Корзина и журнал удалений кандидатов (20.10.2026).

    19.10.2026 кандидатку удалили, и ни кто, ни когда — не осталось нигде, а
    вернуть было нечем: удаление стирает кандидата вместе с воронками, историей,
    файлами и метками (каскадом). Теперь перед удалением снимается полный
    слепок (``snapshot``, services/entity_trash.py), и 7 дней админ может вернуть
    кандидата как был. Потом слепок стирается (``purged_at``), а строка журнала
    «кто, кого, когда» остаётся навсегда.
    """
    __tablename__ = "deleted_entities"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    # Номер удалённого кандидата — НЕ внешний ключ: самой строки уже нет.
    entity_id = Column(Integer, nullable=False, index=True)
    entity_name = Column(String(500), nullable=True)
    entity_type = Column(String(50), nullable=True)
    deleted_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_by_name = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    purge_after = Column(DateTime, nullable=False)
    snapshot = Column(JSON, nullable=True)
    restored_at = Column(DateTime, nullable=True)
    restored_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    restored_by_name = Column(String(255), nullable=True)
    purged_at = Column(DateTime, nullable=True)
    # Что удалено (21.10.2026): «entity» — кандидат целиком; «application» —
    # кандидат убран из ОДНОЙ воронки кнопкой «Удалить с воронки» (заявка, её
    # история и комментарии). Пусто у старых строк = кандидат.
    kind = Column(String(20), nullable=True, default="entity")
    vacancy_id = Column(Integer, nullable=True)
    vacancy_title = Column(String(500), nullable=True)
    # Чей кандидат был в воронке (автор заявки) и на каком этапе — для строки
    # корзины: «был у Марии, Интервью с заказчиком».
    owner_name = Column(String(255), nullable=True)
    stage = Column(String(50), nullable=True)


class AuditEvent(Base):
    """Журнал действий (21.10.2026, владелец: «каждый их чих… чтобы не было
    расхождения, в котором непонятно, кто что делал, кто редактировал»).

    Одна строка = один изменяющий запрос к API (всё, кроме GET): кто, когда,
    что вызвал, с каким результатом и с какими данными. Пишет промежуточный
    слой (middleware/audit.py), поэтому новые ручки попадают в журнал сами.
    Логи Saturn живут до перезапуска контейнера — журнал в базе переживает
    деплои. Пароли и токены вырезаются, у файлов — только имя и размер.
    """
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    at = Column(DateTime, default=func.now(), nullable=False, index=True)
    # Не внешние ключи: строка журнала переживает удаление и человека, и кандидата.
    user_id = Column(Integer, nullable=True, index=True)
    user_name = Column(String(255), nullable=True)
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    status = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    action = Column(String(200), nullable=True)
    entity_id = Column(Integer, nullable=True, index=True)
    vacancy_id = Column(Integer, nullable=True, index=True)
    application_id = Column(Integer, nullable=True, index=True)
    body = Column(JSON, nullable=True)
    correlation_id = Column(String(40), nullable=True)


class AiUsageEvent(Base):
    """Один вызов Claude: сколько стоил и откуда (21.10.2026, services/ai_usage.py).

    Пишется на каждый вызов SDK (обёртка ставится при старте), ошибки тоже —
    так видно и «кончился баланс». Цена примерная, по прайсу в ai_usage.PRICES.
    """
    __tablename__ = "ai_usage_events"

    id = Column(Integer, primary_key=True)
    at = Column(DateTime, default=func.now(), nullable=False, index=True)
    model = Column(String(100), nullable=True)
    caller = Column(String(200), nullable=True, index=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    ok = Column(Boolean, nullable=False, default=True)
    error = Column(String(400), nullable=True)


# ===========================================================================
# ХАБ ДОСТУПОВ (модуль Enceladus)
# ---------------------------------------------------------------------------
# Вокруг сотрудника собирается единая экосистема ресурсов: он запрашивает по
# своей роли прокси/аккаунты/пополнения, заявка уходит ответственному, выданное
# копится в карточке — и при увольнении по этому же списку строится чек-лист
# отзыва.
#
# ВАЖНО про секреты: система трекает только ФАКТ выдачи и статус. Реальные
# креды (пароли, ключи, данные карт) здесь НЕ хранятся и не передаются —
# осознанное решение, чтобы не брать на себя хранение чувствительных данных.
# ===========================================================================


class ResourceCategory(str, enum.Enum):
    """Категория ресурса. Расширяется суперадмином через каталог."""
    proxy = "proxy"                  # Прокси
    payment_topup = "payment_topup"  # Пополнение платёжки
    payment = "payment"              # Оплата
    account = "account"              # Аккаунт
    tg_account = "tg_account"        # Telegram-аккаунт
    consumable = "consumable"        # Расходник
    other = "other"


class AccessRequestStatus(str, enum.Enum):
    """Статус заявки. new/in_progress/granted/rejected — из ТЗ,
    revoked добавлен для оффбординга (отзыв ранее выданного)."""
    new = "new"                  # Новая
    in_progress = "in_progress"  # В работе
    granted = "granted"          # Выдано
    rejected = "rejected"        # Отклонено
    revoked = "revoked"          # Отозвано


class ResourceCatalog(Base):
    """Справочник типов ресурсов: что вообще можно запросить."""
    __tablename__ = "resource_catalog"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(64), nullable=False)          # машинный ключ (proxy_us)
    name = Column(String(200), nullable=False)        # человеческое имя
    category = Column(SQLEnum(ResourceCategory, name="resourcecategory",
                              create_constraint=False, native_enum=False),
                      nullable=False, default=ResourceCategory.other)
    description = Column(Text, nullable=True)

    # Кому летит заявка этого типа. Заявитель имени не видит — только «Снабжение».
    responsible_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Параметры формы: [{key,label,type,required,options[]}] — например страна прокси
    params_schema = Column(JSON, default=list)

    # Условие разблокировки: always | prometheus_accepted | in_staff
    unlock_condition = Column(String(40), nullable=False, default="always")

    # Лимиты (в v1 по требованию бизнеса). NULL = без ограничения.
    limit_per_month = Column(Integer, nullable=True)      # штук в месяц на человека
    limit_amount_month = Column(Integer, nullable=True)   # сумма в месяц на человека (в минорных единицах)
    currency = Column(String(8), nullable=True, default="RUB")

    # Доступен всем сотрудникам, без привязки к роли.
    #
    # Без этого хаб был мёртв для большинства: видимость считалась ТОЛЬКО от
    # кастомной роли, а у обычного сотрудника её обычно нет — он не увидел бы
    # ничего даже при полном каталоге, и «настроить в конструкторе ролей» было
    # нечего. Ресурсы вроде прокси нужны всем, и заводить ради них роль каждому
    # человеку — лишний обряд.
    available_to_all = Column(Boolean, default=False, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("org_id", "key", name="uq_resource_catalog_org_key"),
        Index("ix_resource_catalog_org_active", "org_id", "is_active"),
    )

    responsible = relationship("User", foreign_keys=[responsible_user_id])
    grants = relationship("RoleResourceGrant", back_populates="resource", cascade="all, delete-orphan")


class RoleResourceGrant(Base):
    """Какие типы ресурсов доступны роли — те самые галочки в конструкторе ролей."""
    __tablename__ = "role_resource_grants"

    id = Column(Integer, primary_key=True)
    # role_id, а не custom_role_id — соответствует полю модели CustomRole
    role_id = Column(Integer, ForeignKey("custom_roles.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resource_catalog.id", ondelete="CASCADE"), nullable=False, index=True)
    can_request = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("role_id", "resource_id", name="uq_role_resource_grant"),
    )

    resource = relationship("ResourceCatalog", back_populates="grants")


class AccessRequest(Base):
    """Заявка на ресурс: заявитель → ответственный → выдача/отказ."""
    __tablename__ = "access_requests"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    requester_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Для кого ресурс (обычно = заявитель, но админ может завести за сотрудника)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    resource_id = Column(Integer, ForeignKey("resource_catalog.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Компания холдинга (верхний уровень org_units) — чтобы сводить расходы
    company_unit_id = Column(Integer, ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True)

    params = Column(JSON, default=dict)      # значения по params_schema ресурса
    comment = Column(Text, nullable=True)    # свободный текст от заявителя

    status = Column(SQLEnum(AccessRequestStatus, name="accessrequeststatus",
                            create_constraint=False, native_enum=False),
                    nullable=False, default=AccessRequestStatus.new, index=True)
    assignee_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Стоимость — для лимитов и сводки расходов (минорные единицы, напр. копейки)
    amount = Column(Integer, nullable=True)
    currency = Column(String(8), nullable=True)

    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_comment = Column(Text, nullable=True)

    granted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_access_request_org_status", "org_id", "status"),
        Index("ix_access_request_assignee_status", "assignee_user_id", "status"),
        Index("ix_access_request_target_status", "target_user_id", "status"),
    )

    resource = relationship("ResourceCatalog")
    requester = relationship("User", foreign_keys=[requester_user_id])
    target_user = relationship("User", foreign_keys=[target_user_id])
    assignee = relationship("User", foreign_keys=[assignee_user_id])
    audit = relationship("AccessRequestAudit", back_populates="request",
                         cascade="all, delete-orphan", order_by="AccessRequestAudit.created_at")


class AccessRequestMessage(Base):
    """Сообщение в анонимном чате по заявке (ТЗ п. 3.5).

    Чат привязан к заявке, а не к паре людей: у одного человека может быть
    несколько заявок к разным ответственным, и переписку нельзя смешивать.

    Анонимность односторонняя: заявитель видит «Снабжение» вместо имени
    ответственного — как и в самой заявке. Ответственный имя заявителя видит,
    иначе не поймёт, кому и что выдаёт.
    """
    __tablename__ = "access_request_messages"

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("access_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    text = Column(Text, nullable=False)
    # Откуда пришло: miniapp | web | bot — видно, работает ли ответ из Telegram
    source = Column(String(12), nullable=False, default="web")
    created_at = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index("ix_ah_msg_request_created", "request_id", "created_at"),
    )


class AccessRequestAudit(Base):
    """Append-only журнал переходов статусов заявки (по образцу StageTransition)."""
    __tablename__ = "access_request_audit"

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("access_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=False)
    action = Column(String(30), nullable=False)   # create | assign | grant | reject | revoke | comment
    changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    comment = Column(Text, nullable=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_access_audit_request_created", "request_id", "created_at"),
    )

    request = relationship("AccessRequest", back_populates="audit")
