"""
Shared test utilities and helper functions for HR-Bot backend tests.

This module provides reusable functions for creating test data, simulating
user actions, and performing common test operations.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, Organization, OrgMember, Department, DepartmentMember,
    Entity, Chat, CallRecording, Message, SharedAccess,
    UserRole, OrgRole, DeptRole, EntityType, EntityStatus,
    ChatType, CallStatus, CallSource, AccessLevel, ResourceType
)
from api.services.auth import hash_password, create_access_token


# ============================================================================
# USER HELPERS
# ============================================================================

async def create_test_user(
    db_session: AsyncSession,
    email: str = "test@test.com",
    password: str = "Password123",
    name: str = "Test User",
    role: UserRole = UserRole.admin,
    is_active: bool = True,
    telegram_id: Optional[int] = None,
    telegram_username: Optional[str] = None
) -> User:
    """Create a test user with given parameters.

    Args:
        db_session: Database session
        email: User email address
        password: Plain text password (will be hashed)
        name: User display name
        role: User role (SUPERADMIN, ADMIN, SUB_ADMIN)
        is_active: Whether user is active
        telegram_id: Optional Telegram user ID
        telegram_username: Optional Telegram username

    Returns:
        Created User object
    """
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=role,
        is_active=is_active,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_user_with_token(
    db_session: AsyncSession,
    email: str = "test@test.com",
    password: str = "Password123",
    name: str = "Test User",
    role: UserRole = UserRole.admin,
) -> tuple[User, str]:
    """Create a test user and return user object with auth token.

    Args:
        db_session: Database session
        email: User email address
        password: Plain text password (will be hashed)
        name: User display name
        role: User role

    Returns:
        Tuple of (User object, JWT token string)
    """
    user = await create_test_user(db_session, email, password, name, role)
    token = create_access_token(data={"sub": str(user.id)})
    return user, token


# ============================================================================
# ORGANIZATION HELPERS
# ============================================================================

async def create_test_organization(
    db_session: AsyncSession,
    name: str = "Test Organization",
    slug: Optional[str] = None
) -> Organization:
    """Create a test organization.

    Args:
        db_session: Database session
        name: Organization name
        slug: Organization slug (auto-generated if not provided)

    Returns:
        Created Organization object
    """
    if not slug:
        slug = name.lower().replace(" ", "-")

    org = Organization(
        name=name,
        slug=slug,
        created_at=datetime.utcnow()
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def add_user_to_org(
    db_session: AsyncSession,
    user: User,
    org: Organization,
    role: OrgRole = OrgRole.member
) -> OrgMember:
    """Add a user to an organization with specified role.

    Args:
        db_session: Database session
        user: User to add
        org: Organization to add user to
        role: Organization role (owner, admin, member)

    Returns:
        Created OrgMember object
    """
    member = OrgMember(
        org_id=org.id,
        user_id=user.id,
        role=role,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


async def create_full_org_setup(
    db_session: AsyncSession,
    user: User,
    org_name: str = "Test Org",
    dept_name: str = "Test Department"
) -> tuple[Organization, Department, OrgMember, DepartmentMember]:
    """Create org with departments and memberships for testing.

    This is a convenience function that sets up a complete organization
    structure with the user as owner and department lead.

    Args:
        db_session: Database session
        user: User to make owner/lead
        org_name: Organization name
        dept_name: Department name

    Returns:
        Tuple of (Organization, Department, OrgMember, DepartmentMember)
    """
    org = await create_test_organization(db_session, org_name)

    org_member = await add_user_to_org(db_session, user, org, OrgRole.owner)

    dept = await create_test_department(db_session, org, dept_name)

    dept_member = await add_user_to_dept(db_session, user, dept, DeptRole.lead)

    return org, dept, org_member, dept_member


# ============================================================================
# DEPARTMENT HELPERS
# ============================================================================

async def create_test_department(
    db_session: AsyncSession,
    organization: Organization,
    name: str = "Test Department",
    description: Optional[str] = None
) -> Department:
    """Create a test department.

    Args:
        db_session: Database session
        organization: Parent organization
        name: Department name
        description: Optional department description

    Returns:
        Created Department object
    """
    dept = Department(
        name=name,
        org_id=organization.id,
        description=description,
        created_at=datetime.utcnow()
    )
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def add_user_to_dept(
    db_session: AsyncSession,
    user: User,
    dept: Department,
    role: DeptRole = DeptRole.member
) -> DepartmentMember:
    """Add a user to a department with specified role.

    Args:
        db_session: Database session
        user: User to add
        dept: Department to add user to
        role: Department role (lead, sub_admin, member)

    Returns:
        Created DepartmentMember object
    """
    member = DepartmentMember(
        department_id=dept.id,
        user_id=user.id,
        role=role,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


# ============================================================================
# ENTITY HELPERS
# ============================================================================

async def create_test_entity(
    db_session: AsyncSession,
    organization: Organization,
    created_by: User,
    name: str = "Test Contact",
    entity_type: EntityType = EntityType.candidate,
    status: EntityStatus = EntityStatus.active,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    department: Optional[Department] = None,
    **kwargs
) -> Entity:
    """Create a test entity (contact).

    Args:
        db_session: Database session
        organization: Parent organization
        created_by: User who creates the entity
        name: Entity name
        entity_type: Type of entity (candidate, client, etc.)
        status: Entity status
        email: Optional email address
        phone: Optional phone number
        department: Optional department
        **kwargs: Additional entity fields (company, position, tags, etc.)

    Returns:
        Created Entity object
    """
    entity = Entity(
        org_id=organization.id,
        department_id=department.id if department else None,
        created_by=created_by.id,
        name=name,
        type=entity_type,
        status=status,
        email=email,
        phone=phone,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        **kwargs
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


async def create_entities_batch(
    db_session: AsyncSession,
    organization: Organization,
    created_by: User,
    count: int = 5,
    department: Optional[Department] = None
) -> List[Entity]:
    """Create multiple test entities at once.

    Args:
        db_session: Database session
        organization: Parent organization
        created_by: User who creates the entities
        count: Number of entities to create
        department: Optional department

    Returns:
        List of created Entity objects
    """
    entities = []
    for i in range(count):
        entity = await create_test_entity(
            db_session,
            organization,
            created_by,
            name=f"Contact {i+1}",
            email=f"contact{i+1}@test.com",
            department=department
        )
        entities.append(entity)
    return entities


# ============================================================================
# CHAT HELPERS
# ============================================================================

async def create_test_chat(
    db_session: AsyncSession,
    organization: Organization,
    owner: User,
    title: str = "Test Chat",
    chat_type: ChatType = ChatType.hr,
    telegram_chat_id: Optional[int] = None,
    entity: Optional[Entity] = None
) -> Chat:
    """Create a test chat.

    Args:
        db_session: Database session
        organization: Parent organization
        owner: Chat owner
        title: Chat title
        chat_type: Type of chat
        telegram_chat_id: Optional Telegram chat ID
        entity: Optional linked entity

    Returns:
        Created Chat object
    """
    if not telegram_chat_id:
        telegram_chat_id = 100000000 + id(owner)  # Generate unique ID

    chat = Chat(
        org_id=organization.id,
        owner_id=owner.id,
        entity_id=entity.id if entity else None,
        telegram_chat_id=telegram_chat_id,
        title=title,
        chat_type=chat_type,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    return chat


async def add_chat_messages(
    db_session: AsyncSession,
    chat: Chat,
    count: int = 5,
    telegram_user_id: int = 123456789,
    username: str = "testuser"
) -> List[Message]:
    """Add multiple messages to a chat.

    Args:
        db_session: Database session
        chat: Chat to add messages to
        count: Number of messages to create
        telegram_user_id: Telegram user ID of sender
        username: Username of sender

    Returns:
        List of created Message objects
    """
    messages = []
    for i in range(count):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=1000 + i,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name="Test",
            last_name="User",
            content=f"Test message {i+1}",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(msg)
        messages.append(msg)

    await db_session.commit()
    return messages


# ============================================================================
# CALL RECORDING HELPERS
# ============================================================================

async def create_test_call(
    db_session: AsyncSession,
    organization: Organization,
    owner: User,
    title: str = "Test Call",
    status: CallStatus = CallStatus.done,
    source_type: CallSource = CallSource.upload,
    duration_seconds: int = 300,
    entity: Optional[Entity] = None
) -> CallRecording:
    """Create a test call recording.

    Args:
        db_session: Database session
        organization: Parent organization
        owner: Call owner
        title: Call title
        status: Call processing status
        source_type: Source of the call
        duration_seconds: Call duration in seconds
        entity: Optional linked entity

    Returns:
        Created CallRecording object
    """
    call = CallRecording(
        org_id=organization.id,
        owner_id=owner.id,
        entity_id=entity.id if entity else None,
        title=title,
        source_type=source_type,
        status=status,
        duration_seconds=duration_seconds,
        created_at=datetime.utcnow()
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call


# ============================================================================
# SHARING HELPERS
# ============================================================================

async def create_share(
    db_session: AsyncSession,
    resource_type: ResourceType,
    resource_id: int,
    shared_by: User,
    shared_with: User,
    access_level: AccessLevel = AccessLevel.view,
    **kwargs
) -> SharedAccess:
    """Create a shared access record.

    Args:
        db_session: Database session
        resource_type: Type of resource (entity, chat, call)
        resource_id: ID of the resource
        shared_by: User sharing the resource
        shared_with: User receiving access
        access_level: Access level (view, edit, full)
        **kwargs: Additional fields (entity_id, chat_id, call_id, expires_at)

    Returns:
        Created SharedAccess object
    """
    # Set proper foreign key based on resource type
    fk_field = f"{resource_type.value}_id"
    if fk_field not in kwargs:
        kwargs[fk_field] = resource_id

    share = SharedAccess(
        resource_type=resource_type,
        resource_id=resource_id,
        shared_by_id=shared_by.id,
        shared_with_id=shared_with.id,
        access_level=access_level,
        created_at=datetime.utcnow(),
        **kwargs
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


# ============================================================================
# AUTH HELPERS
# ============================================================================

def make_auth_headers(token: str) -> Dict[str, str]:
    """Create authorization headers with Bearer token.

    Args:
        token: JWT token string

    Returns:
        Dictionary with Authorization header
    """
    return {"Authorization": f"Bearer {token}"}


def make_auth_cookies(token: str) -> Dict[str, str]:
    """Create cookies dict with access token.

    Args:
        token: JWT token string

    Returns:
        Dictionary with access_token cookie
    """
    return {"access_token": token}


# ============================================================================
# ASSERTION HELPERS
# ============================================================================

def assert_response_has_fields(response_data: Dict[str, Any], required_fields: List[str]) -> None:
    """Assert that response data contains all required fields.

    Args:
        response_data: Response JSON data
        required_fields: List of field names that must be present

    Raises:
        AssertionError: If any required field is missing
    """
    for field in required_fields:
        assert field in response_data, f"Missing required field: {field}"


def assert_pagination_format(response_data: Any) -> None:
    """Assert that response follows pagination format.

    Response should either be a list or have 'items' field.

    Args:
        response_data: Response JSON data

    Raises:
        AssertionError: If pagination format is invalid
    """
    assert isinstance(response_data, list) or "items" in response_data, \
        "Response should be a list or contain 'items' field for pagination"
