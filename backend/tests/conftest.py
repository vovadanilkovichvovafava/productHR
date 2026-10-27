"""
Pytest configuration and fixtures for HR-Bot backend tests.
"""
import os
# Set TESTING mode BEFORE any imports to disable rate limiting
os.environ["TESTING"] = "1"
# Set required environment variables for testing
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["SUPERADMIN_PASSWORD"] = "test-superadmin-password"
os.environ["SUPERADMIN_EMAIL"] = "test-superadmin@test.com"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import asyncio
import re
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# Import models and app
import sys
sys.path.insert(0, '/home/user/HR-bot-/backend')

from api.models.database import Base, User, Organization, OrgMember, Department, DepartmentMember
from api.models.database import Entity, Chat, Message, CallRecording, SharedAccess
from api.models.database import UserRole, OrgRole, DeptRole, AccessLevel, ResourceType
from api.models.database import EntityType, EntityStatus, ChatType, CallStatus, CallSource
from api.database import get_db
from api.services.auth import hash_password, create_access_token
from main import app


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


_JSONB_CONTAINS = re.compile(r"([\w.]+|\?)::jsonb\s*@>\s*('[^']*'|\?)::jsonb")
# Тот же «@>», который SQLAlchemy строит из Column.contains([x]) у JSONB:
# «entities.emails @> jsonb_build_array(?)» (поиск по второму email/телефону).
_JSONB_ARRAY_CONTAINS = re.compile(r"([\w.]+)\s*@>\s*jsonb_build_array\((\?)\)")


def _install_sqlite_jsonb_shim(engine) -> None:
    """Переводит постгресовое «X::jsonb @> '[N]'::jsonb» (и «X @> jsonb_build_array(?)») на язык SQLite.

    В коде несколько сырых text()-условий «назначен ли юзер на вакансию»
    (assigned_to — JSON-массив id). На проде это Postgres, в тестах — SQLite,
    который такой синтаксис не разбирает вовсе («unrecognized token: ':'»), и
    любой запрос через эти ветки падал. Смысл тот же: каждый элемент правого
    массива есть в левом.
    """
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _rewrite(conn, cursor, statement, parameters, context, executemany):
        if "jsonb_build_array" in statement:
            statement = _JSONB_ARRAY_CONTAINS.sub(
                lambda m: f"EXISTS (SELECT 1 FROM json_each({m.group(1)}) AS _a WHERE _a.value = {m.group(2)})",
                statement,
            )
        if "::jsonb" in statement:
            statement = _JSONB_CONTAINS.sub(
                lambda m: (
                    f"(NOT EXISTS (SELECT 1 FROM json_each({m.group(2)}) AS _r "
                    f"WHERE _r.value NOT IN (SELECT _l.value FROM json_each({m.group(1)}) AS _l)))"
                ),
                statement,
            )
        return statement, parameters


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create async SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    _install_sqlite_jsonb_shim(engine)

    async with engine.begin() as conn:
        # Enable foreign key constraints in SQLite
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    async_session = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with database override."""
    from api.limiter import limiter

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Reset rate limiter storage before each test to avoid test interference
    try:
        limiter._storage.reset()
    except Exception:
        pass  # Ignore if reset fails

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Reset rate limiter after test too
    try:
        limiter._storage.reset()
    except Exception:
        pass

    app.dependency_overrides.clear()


# ============================================================================
# USER FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def superadmin_user(db_session: AsyncSession) -> User:
    """Create a superadmin user."""
    user = User(
        email="superadmin@test.com",
        password_hash=hash_password("Superadmin123"),
        name="Super Admin",
        role=UserRole.superadmin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user."""
    user = User(
        email="admin@test.com",
        password_hash=hash_password("Admin123"),
        name="Admin User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    """Create a regular user."""
    user = User(
        email="user@test.com",
        password_hash=hash_password("User123"),
        name="Regular User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_user(db_session: AsyncSession) -> User:
    """Create a second regular user for sharing tests."""
    user = User(
        email="user2@test.com",
        password_hash=hash_password("User123"),
        name="Second User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ============================================================================
# ORGANIZATION FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def organization(db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        name="Test Organization",
        slug="test-organization",
        created_at=datetime.utcnow()
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def second_organization(db_session: AsyncSession) -> Organization:
    """Create a second test organization for cross-org tests."""
    org = Organization(
        name="Second Organization",
        slug="second-organization",
        created_at=datetime.utcnow()
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def org_owner(db_session: AsyncSession, organization: Organization, admin_user: User) -> OrgMember:
    """Create an organization owner membership."""
    member = OrgMember(
        org_id=organization.id,
        user_id=admin_user.id,
        role=OrgRole.owner,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


@pytest_asyncio.fixture
async def org_admin(db_session: AsyncSession, organization: Organization, regular_user: User) -> OrgMember:
    """Create an organization admin membership."""
    member = OrgMember(
        org_id=organization.id,
        user_id=regular_user.id,
        role=OrgRole.admin,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


@pytest_asyncio.fixture
async def org_member(db_session: AsyncSession, organization: Organization, second_user: User) -> OrgMember:
    """Create a regular organization member."""
    member = OrgMember(
        org_id=organization.id,
        user_id=second_user.id,
        role=OrgRole.member,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


@pytest_asyncio.fixture
async def superadmin_org_member(db_session: AsyncSession, organization: Organization, superadmin_user: User) -> OrgMember:
    """Create organization membership for superadmin user."""
    member = OrgMember(
        org_id=organization.id,
        user_id=superadmin_user.id,
        role=OrgRole.owner,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


# ============================================================================
# DEPARTMENT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def department(db_session: AsyncSession, organization: Organization) -> Department:
    """Create a test department."""
    dept = Department(
        name="Test Department",
        org_id=organization.id,
        created_at=datetime.utcnow()
    )
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


@pytest_asyncio.fixture
async def second_department(db_session: AsyncSession, organization: Organization) -> Department:
    """Create a second test department."""
    dept = Department(
        name="Second Department",
        org_id=organization.id,
        created_at=datetime.utcnow()
    )
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


@pytest_asyncio.fixture
async def dept_lead(db_session: AsyncSession, department: Department, admin_user: User) -> DepartmentMember:
    """Create a department lead membership."""
    member = DepartmentMember(
        department_id=department.id,
        user_id=admin_user.id,
        role=DeptRole.lead,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


@pytest_asyncio.fixture
async def dept_member(db_session: AsyncSession, department: Department, regular_user: User) -> DepartmentMember:
    """Create a department member."""
    member = DepartmentMember(
        department_id=department.id,
        user_id=regular_user.id,
        role=DeptRole.member,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


# ============================================================================
# ENTITY FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def entity(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Create a test entity (contact)."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Test Contact",
        email="contact@test.com",
        phone="+1234567890",
        type=EntityType.candidate,
        status=EntityStatus.active,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def second_entity(db_session: AsyncSession, organization: Organization, department: Department, second_user: User) -> Entity:
    """Create a second test entity owned by second user."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=second_user.id,
        name="Second Contact",
        email="contact2@test.com",
        type=EntityType.client,
        status=EntityStatus.active,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def user_with_telegram(db_session: AsyncSession) -> User:
    """Create a user with telegram credentials."""
    user = User(
        email="telegram_user@test.com",
        password_hash=hash_password("Password123"),
        name="Telegram User",
        role=UserRole.admin,
        telegram_id=555666777,
        telegram_username="testuser123",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def entity_with_usernames(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Entity with telegram_usernames = ["ivan", "ivan_work"]."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Ivan Petrov",
        email="ivan@test.com",
        type=EntityType.candidate,
        status=EntityStatus.active,
        telegram_usernames=["ivan", "ivan_work"],
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def entity_with_emails(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Entity with emails = ["a@test.com", "b@test.com"]."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Multi Email Person",
        email="a@test.com",
        emails=["b@test.com", "c@test.com"],
        type=EntityType.client,
        status=EntityStatus.active,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def candidate_entity(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Entity with type=candidate and telegram_user_id."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Jane Candidate",
        email="candidate@test.com",
        telegram_user_id=888999000,
        type=EntityType.candidate,
        status=EntityStatus.interview,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


# ============================================================================
# CHAT FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def chat(db_session: AsyncSession, organization: Organization, admin_user: User) -> Chat:
    """Create a test chat."""
    chat = Chat(
        org_id=organization.id,
        owner_id=admin_user.id,
        telegram_chat_id=123456789,
        title="Test Chat",
        chat_type=ChatType.hr,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    return chat


@pytest_asyncio.fixture
async def second_chat(db_session: AsyncSession, organization: Organization, second_user: User) -> Chat:
    """Create a second test chat owned by second user."""
    chat = Chat(
        org_id=organization.id,
        owner_id=second_user.id,
        telegram_chat_id=987654321,
        title="Second Chat",
        chat_type=ChatType.sales,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    return chat


@pytest_asyncio.fixture
async def chat_with_messages(db_session: AsyncSession, organization: Organization, admin_user: User, user_with_telegram: User) -> Chat:
    """Chat with messages from a system user."""
    chat = Chat(
        org_id=organization.id,
        owner_id=admin_user.id,
        telegram_chat_id=111222333,
        title="Chat With Messages",
        chat_type=ChatType.hr,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.flush()

    # Add messages from user_with_telegram
    for i in range(3):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=10000 + i,
            telegram_user_id=user_with_telegram.telegram_id,
            username=user_with_telegram.telegram_username,
            first_name="Telegram",
            last_name="User",
            content=f"Message {i+1}",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(msg)

    await db_session.commit()
    await db_session.refresh(chat)
    return chat


@pytest_asyncio.fixture
async def chat_linked_to_entity(db_session: AsyncSession, organization: Organization, admin_user: User, entity: Entity) -> Chat:
    """Chat linked to an entity (chat.entity_id is set)."""
    chat = Chat(
        org_id=organization.id,
        owner_id=admin_user.id,
        entity_id=entity.id,
        telegram_chat_id=444555666,
        title="Entity Linked Chat",
        chat_type=ChatType.hr,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.flush()

    # Add message from entity (if it has telegram_user_id)
    if entity.telegram_user_id:
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=30000,
            telegram_user_id=entity.telegram_user_id,
            username="entity_user",
            first_name=entity.name.split()[0],
            last_name=entity.name.split()[1] if len(entity.name.split()) > 1 else "",
            content="Hello from entity",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(msg)

    await db_session.commit()
    await db_session.refresh(chat)
    return chat


@pytest_asyncio.fixture
async def chat_with_mixed_senders(db_session: AsyncSession, organization: Organization, admin_user: User, user_with_telegram: User, entity: Entity) -> Chat:
    """Chat with messages from User, Entity, and unknown participants."""
    chat = Chat(
        org_id=organization.id,
        owner_id=admin_user.id,
        telegram_chat_id=777888999,
        title="Mixed Senders Chat",
        chat_type=ChatType.work,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.flush()

    # Message from system user
    msg1 = Message(
        chat_id=chat.id,
        telegram_message_id=40001,
        telegram_user_id=user_with_telegram.telegram_id,
        username=user_with_telegram.telegram_username,
        first_name="System",
        last_name="User",
        content="Message from system user",
        content_type="text",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg1)

    # Set telegram_user_id on entity for testing
    entity.telegram_user_id = 123123123
    db_session.add(entity)
    await db_session.flush()

    # Message from entity
    msg2 = Message(
        chat_id=chat.id,
        telegram_message_id=40002,
        telegram_user_id=entity.telegram_user_id,
        username="entity_username",
        first_name=entity.name.split()[0],
        last_name=entity.name.split()[1] if len(entity.name.split()) > 1 else "",
        content="Message from entity",
        content_type="text",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg2)

    # Message from unknown user
    msg3 = Message(
        chat_id=chat.id,
        telegram_message_id=40003,
        telegram_user_id=999888777,
        username="unknown_user",
        first_name="Unknown",
        last_name="Person",
        content="Message from unknown",
        content_type="text",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg3)

    await db_session.commit()
    await db_session.refresh(chat)
    return chat


# ============================================================================
# CALL FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def call_recording(db_session: AsyncSession, organization: Organization, admin_user: User) -> CallRecording:
    """Create a test call recording."""
    call = CallRecording(
        org_id=organization.id,
        owner_id=admin_user.id,
        title="Test Call",
        source_type=CallSource.upload,
        status=CallStatus.done,
        duration_seconds=300,
        created_at=datetime.utcnow()
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call


@pytest_asyncio.fixture
async def second_call(db_session: AsyncSession, organization: Organization, second_user: User) -> CallRecording:
    """Create a second test call owned by second user."""
    call = CallRecording(
        org_id=organization.id,
        owner_id=second_user.id,
        title="Second Call",
        source_type=CallSource.meet,
        status=CallStatus.done,
        duration_seconds=600,
        created_at=datetime.utcnow()
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call


# ============================================================================
# SHARING FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def entity_share_view(
    db_session: AsyncSession,
    entity: Entity,
    admin_user: User,
    second_user: User
) -> SharedAccess:
    """Create a view-only share for entity."""
    share = SharedAccess(
        resource_type=ResourceType.entity,
        resource_id=entity.id,
        entity_id=entity.id,  # Populate proper foreign key
        shared_by_id=admin_user.id,
        shared_with_id=second_user.id,
        access_level=AccessLevel.view,
        created_at=datetime.utcnow()
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def entity_share_edit(
    db_session: AsyncSession,
    entity: Entity,
    admin_user: User,
    second_user: User
) -> SharedAccess:
    """Create an edit share for entity."""
    share = SharedAccess(
        resource_type=ResourceType.entity,
        resource_id=entity.id,
        entity_id=entity.id,  # Populate proper foreign key
        shared_by_id=admin_user.id,
        shared_with_id=second_user.id,
        access_level=AccessLevel.edit,
        created_at=datetime.utcnow()
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def chat_share_view(
    db_session: AsyncSession,
    chat: Chat,
    admin_user: User,
    second_user: User
) -> SharedAccess:
    """Create a view-only share for chat."""
    share = SharedAccess(
        resource_type=ResourceType.chat,
        resource_id=chat.id,
        chat_id=chat.id,  # Populate proper foreign key
        shared_by_id=admin_user.id,
        shared_with_id=second_user.id,
        access_level=AccessLevel.view,
        created_at=datetime.utcnow()
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def call_share_view(
    db_session: AsyncSession,
    call_recording: CallRecording,
    admin_user: User,
    second_user: User
) -> SharedAccess:
    """Create a view-only share for call."""
    share = SharedAccess(
        resource_type=ResourceType.call,
        resource_id=call_recording.id,
        call_id=call_recording.id,  # Populate proper foreign key
        shared_by_id=admin_user.id,
        shared_with_id=second_user.id,
        access_level=AccessLevel.view,
        created_at=datetime.utcnow()
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def expired_share(
    db_session: AsyncSession,
    entity: Entity,
    admin_user: User,
    second_user: User
) -> SharedAccess:
    """Create an expired share."""
    share = SharedAccess(
        resource_type=ResourceType.entity,
        resource_id=entity.id,
        entity_id=entity.id,  # Populate proper foreign key
        shared_by_id=admin_user.id,
        shared_with_id=second_user.id,
        access_level=AccessLevel.edit,
        expires_at=datetime.utcnow() - timedelta(days=1),  # Expired
        created_at=datetime.utcnow() - timedelta(days=2)
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


# ============================================================================
# AUTH TOKEN FIXTURES
# ============================================================================

@pytest.fixture
def superadmin_token(superadmin_user: User) -> str:
    """Generate JWT token for superadmin."""
    return create_access_token(data={"sub": str(superadmin_user.id)})


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Generate JWT token for admin."""
    return create_access_token(data={"sub": str(admin_user.id)})


@pytest.fixture
def user_token(regular_user: User) -> str:
    """Generate JWT token for regular user."""
    return create_access_token(data={"sub": str(regular_user.id)})


@pytest.fixture
def second_user_token(second_user: User) -> str:
    """Generate JWT token for second user."""
    return create_access_token(data={"sub": str(second_user.id)})


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# Make helper available to tests
@pytest.fixture
def get_auth_headers():
    """Return auth_headers function for use in tests."""
    return auth_headers


# ============================================================================
# EXTERNAL SERVICE MOCKS (Auto-applied to all tests)
# ============================================================================

@pytest.fixture(autouse=True)
def mock_fireflies_client(monkeypatch):
    """Mock Fireflies API client for all tests."""
    mock_client = MagicMock()
    mock_client.start_bot = AsyncMock(return_value={"id": "test-bot-123", "status": "started"})
    mock_client.stop_bot = AsyncMock(return_value={"status": "stopped"})
    mock_client.get_transcript = AsyncMock(return_value={
        "id": "test-transcript-123",
        "title": "Test Call",
        "sentences": [
            {"text": "Hello, how are you?", "speaker_name": "Speaker 1", "start_time": 0},
            {"text": "I'm doing great, thanks!", "speaker_name": "Speaker 2", "start_time": 2}
        ],
        "summary": {"overview": "Test call summary"},
        "duration": 300
    })
    mock_client.list_transcripts = AsyncMock(return_value=[])

    # Patch both the class and the singleton instance at source
    monkeypatch.setattr("api.services.fireflies_client.FirefliesClient", lambda *args, **kwargs: mock_client)
    monkeypatch.setattr("api.services.fireflies_client.fireflies_client", mock_client)

    return mock_client


@pytest.fixture(autouse=True)
def mock_anthropic_client(monkeypatch):
    """Mock Anthropic Claude API for all tests."""
    # Mock response for non-streaming create()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This is a mock AI response for testing.")]
    mock_response.stop_reason = "end_turn"
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    # Create async generator for text_stream
    async def mock_text_stream():
        chunks = ["Mock ", "streamed ", "response"]
        for chunk in chunks:
            yield chunk

    # Function to create a fresh stream each time
    def create_stream(*args, **kwargs):
        """Create a fresh mock stream with a new generator."""
        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.text_stream = mock_text_stream()
        return mock_stream

    # Create the mock client
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_client.messages.stream = MagicMock(side_effect=create_stream)

    # Mock both Anthropic and AsyncAnthropic
    monkeypatch.setattr("anthropic.Anthropic", lambda *args, **kwargs: mock_client)
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda *args, **kwargs: mock_client)

    return mock_client


@pytest.fixture(autouse=True)
def mock_openai_client(monkeypatch):
    """Mock OpenAI Whisper API for transcription tests."""
    mock_transcription = MagicMock()
    mock_transcription.text = "This is a mock transcription of the audio file."

    mock_audio = MagicMock()
    mock_audio.transcriptions.create = MagicMock(return_value=mock_transcription)

    mock_client = MagicMock()
    mock_client.audio = mock_audio

    monkeypatch.setattr("openai.OpenAI", lambda *args, **kwargs: mock_client)

    return mock_client


@pytest.fixture(autouse=True)
def mock_file_operations(monkeypatch, tmp_path):
    """Mock file system operations for tests."""
    import tempfile
    import shutil

    # Create a mock uploads directory
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    # Mock the UPLOAD_DIR and related paths
    monkeypatch.setenv("UPLOAD_DIR", str(uploads_dir))

    # Create mock audio file
    mock_audio = uploads_dir / "test_audio.mp3"
    mock_audio.write_bytes(b"mock audio content")

    return uploads_dir


@pytest.fixture(autouse=True)
def mock_subprocess(monkeypatch):
    """Mock subprocess calls (ffmpeg, etc.)."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = b""
    mock_result.stderr = b""

    async def mock_create_subprocess(*args, **kwargs):
        process = MagicMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        process.wait = AsyncMock(return_value=0)
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess)
    monkeypatch.setattr("asyncio.create_subprocess_shell", mock_create_subprocess)

    return mock_result


@pytest.fixture(autouse=True)
def mock_aiofiles(monkeypatch):
    """Mock aiofiles for async file operations."""
    # Create async context manager mock
    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=b"mock file content")
    mock_file.write = AsyncMock(return_value=None)
    mock_file.close = AsyncMock(return_value=None)

    # Create async context manager
    class MockAsyncFile:
        async def __aenter__(self):
            return mock_file

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Mock the open function to return the async context manager
    def mock_open_func(*args, **kwargs):
        return MockAsyncFile()

    try:
        monkeypatch.setattr("aiofiles.open", mock_open_func)
    except AttributeError:
        pass  # aiofiles not imported in all modules

    return mock_file


@pytest.fixture(autouse=True)
def mock_httpx_async(monkeypatch):
    """Mock httpx async client for external API calls."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"status": "ok"})
    mock_response.text = "OK"
    mock_response.content = b"OK"
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.put = AsyncMock(return_value=mock_response)
    mock_client.delete = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    return mock_client


@pytest.fixture
def mock_reportlab(monkeypatch):
    """Mock ReportLab for PDF generation tests.

    NOTE: This fixture is not auto-used. Request it explicitly in tests that need to
    avoid actual PDF generation. The PDF report tests need real ReportLab functionality.
    """
    mock_canvas = MagicMock()
    mock_canvas.drawString = MagicMock()
    mock_canvas.save = MagicMock()
    mock_canvas.showPage = MagicMock()

    mock_doc = MagicMock()
    mock_doc.build = MagicMock()

    try:
        monkeypatch.setattr("reportlab.pdfgen.canvas.Canvas", lambda *args, **kwargs: mock_canvas)
        monkeypatch.setattr("reportlab.platypus.SimpleDocTemplate", lambda *args, **kwargs: mock_doc)
    except AttributeError:
        pass

    return mock_canvas


@pytest.fixture(autouse=True)
def mock_pillow(monkeypatch):
    """Mock Pillow for image processing tests."""
    mock_image = MagicMock()
    mock_image.size = (100, 100)
    mock_image.mode = "RGB"
    mock_image.save = MagicMock()
    mock_image.convert = MagicMock(return_value=mock_image)

    mock_image_open = MagicMock(return_value=mock_image)

    try:
        monkeypatch.setattr("PIL.Image.open", mock_image_open)
    except AttributeError:
        pass

    return mock_image


@pytest.fixture
def mock_websocket_broadcast(monkeypatch):
    """Mock WebSocket broadcast helper functions.

    NOTE: Not auto-used. Tests that need to mock broadcasts should request this fixture explicitly.
    The realtime route tests need real broadcast functionality.
    """
    # Mock the actual broadcast helper functions
    mock_entity_created = AsyncMock()
    mock_entity_updated = AsyncMock()
    mock_entity_deleted = AsyncMock()
    mock_chat_message = AsyncMock()
    mock_share_created = AsyncMock()
    mock_share_revoked = AsyncMock()

    monkeypatch.setattr("api.routes.realtime.broadcast_entity_created", mock_entity_created)
    monkeypatch.setattr("api.routes.realtime.broadcast_entity_updated", mock_entity_updated)
    monkeypatch.setattr("api.routes.realtime.broadcast_entity_deleted", mock_entity_deleted)
    monkeypatch.setattr("api.routes.realtime.broadcast_chat_message", mock_chat_message)
    monkeypatch.setattr("api.routes.realtime.broadcast_share_created", mock_share_created)
    monkeypatch.setattr("api.routes.realtime.broadcast_share_revoked", mock_share_revoked)

    return {
        "entity_created": mock_entity_created,
        "entity_updated": mock_entity_updated,
        "entity_deleted": mock_entity_deleted,
        "chat_message": mock_chat_message,
        "share_created": mock_share_created,
        "share_revoked": mock_share_revoked,
    }


@pytest.fixture(autouse=True)
def mock_call_processor(monkeypatch):
    """Mock call processor for all tests."""
    # Mock analyze_transcript method
    mock_analyze = AsyncMock(return_value=None)

    # Mock process_call method
    mock_process = AsyncMock(return_value=None)

    # Create mock processor
    mock_processor = MagicMock()
    mock_processor.analyze_transcript = mock_analyze
    mock_processor.process_call = mock_process

    # Mock the global call_processor instance
    try:
        monkeypatch.setattr("api.services.call_processor.call_processor", mock_processor)
    except AttributeError:
        pass

    # Mock process_call_background function
    mock_bg_process = AsyncMock(return_value=None)
    try:
        monkeypatch.setattr("api.services.call_processor.process_call_background", mock_bg_process)
    except AttributeError:
        pass

    return mock_processor


@pytest.fixture(autouse=True)
def mock_call_recorder_service(monkeypatch):
    """Mock call recorder service for all tests."""
    # Mock start_recording method
    mock_start = AsyncMock(return_value={"success": True, "message": "Recording started"})

    # Mock stop_recording method
    mock_stop = AsyncMock(return_value=None)

    # Create mock recorder
    mock_recorder = MagicMock()
    mock_recorder.start_recording = mock_start
    mock_recorder.stop_recording = mock_stop

    # Mock the global call_recorder instance
    try:
        monkeypatch.setattr("api.services.call_recorder.call_recorder", mock_recorder)
    except AttributeError:
        pass

    return mock_recorder


@pytest.fixture(autouse=True)
def mock_playwright(monkeypatch):
    """Mock Playwright async API for all tests.

    This prevents tests from requiring actual browser installation.
    Mocks the async_playwright context manager and returns mock browser/page objects.
    """
    # Create mock element that has text_content method
    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Mock element text content")

    # Create mock page with all necessary methods
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=None)
    mock_page.wait_for_selector = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock(return_value=None)
    mock_page.query_selector = AsyncMock(return_value=mock_element)
    mock_page.query_selector_all = AsyncMock(return_value=[mock_element])

    # Create mock browser
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock(return_value=None)

    # Create mock chromium
    mock_chromium = MagicMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    # Create mock playwright instance
    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium = mock_chromium

    # Create async context manager for async_playwright
    class MockAsyncPlaywright:
        async def __aenter__(self):
            return mock_playwright_instance

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Mock the async_playwright function
    def mock_async_playwright():
        return MockAsyncPlaywright()

    # Apply the mock
    try:
        monkeypatch.setattr("playwright.async_api.async_playwright", mock_async_playwright)
    except (AttributeError, ImportError):
        # Playwright not imported in all modules
        pass

    return {
        "playwright": mock_playwright_instance,
        "chromium": mock_chromium,
        "browser": mock_browser,
        "page": mock_page,
        "element": mock_element,
    }


# ============================================================================
# PARALLEL TEST SUPPORT
# ============================================================================

def pytest_configure(config):
    """Configure pytest for parallel execution."""
    # Add markers
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


# ============================================================================
# ADDITIONAL TEST HELPERS
# ============================================================================

@pytest.fixture
def mock_file_upload(tmp_path):
    """Create a mock file upload."""
    from io import BytesIO

    def _create_upload(filename="test.txt", content=b"test content", content_type="text/plain"):
        file_obj = BytesIO(content)
        file_obj.name = filename
        return {
            "file": (filename, file_obj, content_type)
        }

    return _create_upload


@pytest.fixture
def mock_audio_file(tmp_path):
    """Create a mock audio file for upload tests."""
    audio_path = tmp_path / "test_audio.mp3"
    # Write minimal MP3 header
    audio_path.write_bytes(b'\xff\xfb\x90\x00' + b'\x00' * 100)
    return audio_path
