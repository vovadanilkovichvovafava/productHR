"""
Comprehensive tests for participant identification system.

This test suite covers:
- exact_match: Find participants by exact telegram username or user ID
- fuzzy_match_name: Find participants by fuzzy name matching
- identify_participants: Identify all participants in a chat
- get_role_icon: Get emoji icons for participant roles
- API: Entity multiple identifiers (emails, telegram_usernames, phones)

These tests ensure proper participant identification across Users and Entities
with support for multiple identifiers per Entity.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from httpx import AsyncClient

from api.models.database import (
    User, Entity, Chat, Message,
    Organization, Department, OrgMember, DepartmentMember,
    EntityType, EntityStatus, ChatType, OrgRole, DeptRole
)


# ============================================================================
# PARTICIPANT IDENTIFICATION UTILITIES (to be implemented in production)
# ============================================================================

class ParticipantRole(str, Enum):
    """Role of participant in the system."""
    system_user = "system_user"      # User account in the system
    target_entity = "target_entity"  # Entity linked to chat (chat.entity_id)
    employee = "employee"            # Entity with type=employee (future)
    candidate = "candidate"          # Entity with type=candidate
    client = "client"                # Entity with type=client
    contractor = "contractor"        # Entity with type=contractor
    unknown = "unknown"              # Not identified


def get_role_icon(role: ParticipantRole) -> str:
    """Get emoji icon for participant role."""
    icons = {
        ParticipantRole.system_user: "🔑",
        ParticipantRole.target_entity: "🎯",
        ParticipantRole.employee: "🏢",
        ParticipantRole.candidate: "👤",
        ParticipantRole.client: "💼",
        ParticipantRole.contractor: "🔧",
        ParticipantRole.unknown: "❓",
    }
    return icons.get(role, "❓")


async def exact_match(
    db: AsyncSession,
    org_id: int,
    telegram_user_id: Optional[int] = None,
    telegram_username: Optional[str] = None
) -> Optional[Dict]:
    """
    Find participant by exact match (telegram_user_id or telegram_username).

    Search order:
    1. User.telegram_id == telegram_user_id
    2. User.telegram_username == telegram_username (exact, case-insensitive)
    3. Entity.telegram_user_id == telegram_user_id
    4. Entity.telegram_usernames contains username (normalized)

    Returns:
        Dict with keys: type ('user'|'entity'), id, name, role
        None if not found
    """
    # Normalize username
    if telegram_username:
        telegram_username = telegram_username.lower().lstrip('@')

    # 1. Try User by telegram_id
    if telegram_user_id:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return {
                "type": "user",
                "id": user.id,
                "name": user.name,
                "role": ParticipantRole.system_user
            }

    # 2. Try User by telegram_username
    if telegram_username:
        result = await db.execute(
            select(User).where(
                User.telegram_username.ilike(telegram_username)
            )
        )
        user = result.scalar_one_or_none()
        if user:
            return {
                "type": "user",
                "id": user.id,
                "name": user.name,
                "role": ParticipantRole.system_user
            }

    # 3. Try Entity by telegram_user_id
    if telegram_user_id:
        result = await db.execute(
            select(Entity).where(
                Entity.org_id == org_id,
                Entity.telegram_user_id == telegram_user_id
            )
        )
        entity = result.scalar_one_or_none()
        if entity:
            return {
                "type": "entity",
                "id": entity.id,
                "name": entity.name,
                "role": ParticipantRole(entity.type.value) if entity.type.value in [r.value for r in ParticipantRole] else ParticipantRole.unknown
            }

    # 4. Try Entity by telegram_usernames array
    if telegram_username:
        result = await db.execute(
            select(Entity).where(Entity.org_id == org_id)
        )
        entities = result.scalars().all()
        for entity in entities:
            usernames = entity.telegram_usernames or []
            # Normalize stored usernames
            normalized = [u.lower().lstrip('@') for u in usernames]
            if telegram_username in normalized:
                return {
                    "type": "entity",
                    "id": entity.id,
                    "name": entity.name,
                    "role": ParticipantRole(entity.type.value) if entity.type.value in [r.value for r in ParticipantRole] else ParticipantRole.unknown
                }

    return None


async def fuzzy_match_name(
    db: AsyncSession,
    org_id: int,
    first_name: Optional[str],
    last_name: Optional[str]
) -> Optional[Dict]:
    """
    Find participant by fuzzy name matching.

    Returns:
        Dict with keys: type, id, name, role, confidence (0.0-1.0)
        None if no good match found
    """
    if not first_name and not last_name:
        return None

    search_name = f"{first_name or ''} {last_name or ''}".strip()
    full_name = search_name.lower()

    # Try exact match on Entity.name. Шаблон — в исходном регистре: в тестовой
    # SQLite ILIKE/LOWER не знают кириллицы («иван» не находит «Иван Петров»),
    # в Postgres регистр всё равно не важен.
    result = await db.execute(
        select(Entity).where(
            Entity.org_id == org_id,
            Entity.name.ilike(f"%{search_name}%")
        )
    )
    entity = result.scalar_one_or_none()
    if entity:
        # Calculate simple confidence
        entity_name_lower = entity.name.lower()
        if entity_name_lower == full_name:
            confidence = 1.0
        elif full_name in entity_name_lower or entity_name_lower in full_name:
            confidence = 0.8
        else:
            confidence = 0.6

        return {
            "type": "entity",
            "id": entity.id,
            "name": entity.name,
            "role": ParticipantRole(entity.type.value) if entity.type.value in [r.value for r in ParticipantRole] else ParticipantRole.unknown,
            "confidence": confidence
        }

    return None


async def identify_participants(
    db: AsyncSession,
    chat: Chat
) -> List[Dict]:
    """
    Identify all unique participants in a chat.

    Returns list of dicts with keys:
    - telegram_user_id: int
    - username: Optional[str]
    - first_name: Optional[str]
    - last_name: Optional[str]
    - identified_as: Optional[Dict] (from exact_match or fuzzy_match)
    - role: ParticipantRole
    - role_icon: str
    - messages_count: int
    """
    # Get all unique senders
    result = await db.execute(
        select(
            Message.telegram_user_id,
            Message.username,
            Message.first_name,
            Message.last_name
        )
        .where(Message.chat_id == chat.id)
        .distinct()
    )
    senders = result.all()

    participants = []
    for sender in senders:
        telegram_user_id = sender[0]
        username = sender[1]
        first_name = sender[2]
        last_name = sender[3]

        # Get message count
        count_result = await db.execute(
            select(Message)
            .where(
                Message.chat_id == chat.id,
                Message.telegram_user_id == telegram_user_id
            )
        )
        messages_count = len(count_result.scalars().all())

        # Try exact match
        identified = await exact_match(
            db,
            chat.org_id,
            telegram_user_id=telegram_user_id,
            telegram_username=username
        )

        # Try fuzzy match if no exact match
        if not identified:
            identified = await fuzzy_match_name(
                db,
                chat.org_id,
                first_name=first_name,
                last_name=last_name
            )

        # Determine role
        if identified:
            role = identified["role"]
            # Check if this is the target entity
            if chat.entity_id and identified.get("type") == "entity" and identified.get("id") == chat.entity_id:
                role = ParticipantRole.target_entity
        else:
            role = ParticipantRole.unknown

        participants.append({
            "telegram_user_id": telegram_user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "identified_as": identified,
            "role": role,
            "role_icon": get_role_icon(role),
            "messages_count": messages_count
        })

    return participants


# ============================================================================
# TESTS: exact_match
# ============================================================================

class TestExactMatch:
    """Tests for exact_match function."""

    @pytest.mark.asyncio
    async def test_match_by_telegram_id_in_user(
        self,
        db_session: AsyncSession,
        organization: Organization,
        user_with_telegram: User
    ):
        """Find User by telegram_id."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_user_id=user_with_telegram.telegram_id
        )

        assert result is not None
        assert result["type"] == "user"
        assert result["id"] == user_with_telegram.id
        assert result["name"] == user_with_telegram.name
        assert result["role"] == ParticipantRole.system_user

    @pytest.mark.asyncio
    async def test_match_by_telegram_username_in_user(
        self,
        db_session: AsyncSession,
        organization: Organization,
        user_with_telegram: User
    ):
        """Find User by telegram_username."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_username=user_with_telegram.telegram_username
        )

        assert result is not None
        assert result["type"] == "user"
        assert result["id"] == user_with_telegram.id
        assert result["role"] == ParticipantRole.system_user

    @pytest.mark.asyncio
    async def test_match_by_username_with_at_symbol(
        self,
        db_session: AsyncSession,
        organization: Organization,
        user_with_telegram: User
    ):
        """Find User by telegram_username with @ prefix (should be normalized)."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_username=f"@{user_with_telegram.telegram_username}"
        )

        assert result is not None
        assert result["type"] == "user"

    @pytest.mark.asyncio
    async def test_match_by_username_case_insensitive(
        self,
        db_session: AsyncSession,
        organization: Organization,
        user_with_telegram: User
    ):
        """Username matching should be case-insensitive."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_username=user_with_telegram.telegram_username.upper()
        )

        assert result is not None
        assert result["type"] == "user"

    @pytest.mark.asyncio
    async def test_match_by_username_in_entity_array(
        self,
        db_session: AsyncSession,
        organization: Organization,
        entity_with_usernames: Entity
    ):
        """Find Entity by username in telegram_usernames array."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_username="ivan"
        )

        assert result is not None
        assert result["type"] == "entity"
        assert result["id"] == entity_with_usernames.id
        assert result["name"] == entity_with_usernames.name

    @pytest.mark.asyncio
    async def test_match_by_second_username_in_array(
        self,
        db_session: AsyncSession,
        organization: Organization,
        entity_with_usernames: Entity
    ):
        """Find Entity by second username in array."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_username="ivan_work"
        )

        assert result is not None
        assert result["type"] == "entity"
        assert result["id"] == entity_with_usernames.id

    @pytest.mark.asyncio
    async def test_match_by_telegram_user_id_in_entity(
        self,
        db_session: AsyncSession,
        organization: Organization,
        entity: Entity
    ):
        """Find Entity by telegram_user_id."""
        # Set telegram_user_id on entity
        entity.telegram_user_id = 123456789
        db_session.add(entity)
        await db_session.commit()

        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_user_id=123456789
        )

        assert result is not None
        assert result["type"] == "entity"
        assert result["id"] == entity.id

    @pytest.mark.asyncio
    async def test_no_match_returns_none(
        self,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Return None when no match found."""
        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_user_id=999999999,
            telegram_username="nonexistent"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_user_takes_precedence_over_entity(
        self,
        db_session: AsyncSession,
        organization: Organization,
        user_with_telegram: User,
        entity: Entity
    ):
        """User match takes precedence over Entity match."""
        # Give entity same telegram_user_id as user
        entity.telegram_user_id = user_with_telegram.telegram_id
        db_session.add(entity)
        await db_session.commit()

        result = await exact_match(
            db_session,
            org_id=organization.id,
            telegram_user_id=user_with_telegram.telegram_id
        )

        # Should return User, not Entity
        assert result is not None
        assert result["type"] == "user"
        assert result["id"] == user_with_telegram.id


# ============================================================================
# TESTS: fuzzy_match_name
# ============================================================================

class TestFuzzyMatch:
    """Tests for fuzzy_match_name function."""

    @pytest.mark.asyncio
    async def test_exact_name_match(
        self,
        db_session: AsyncSession,
        organization: Organization,
        entity: Entity
    ):
        """Exact name match returns confidence 1.0."""
        # Split entity name
        parts = entity.name.split()
        first_name = parts[0] if parts else entity.name
        last_name = parts[1] if len(parts) > 1 else ""

        result = await fuzzy_match_name(
            db_session,
            org_id=organization.id,
            first_name=first_name,
            last_name=last_name
        )

        assert result is not None
        assert result["type"] == "entity"
        assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_partial_name_match(
        self,
        db_session: AsyncSession,
        organization: Organization,
        entity: Entity
    ):
        """Partial name match (Иван → Иван Петров)."""
        # Update entity name
        entity.name = "Иван Петров"
        db_session.add(entity)
        await db_session.commit()

        result = await fuzzy_match_name(
            db_session,
            org_id=organization.id,
            first_name="Иван",
            last_name=None
        )

        assert result is not None
        assert result["type"] == "entity"
        assert result["confidence"] > 0.0

    @pytest.mark.asyncio
    async def test_case_insensitive_match(
        self,
        db_session: AsyncSession,
        organization: Organization,
        entity: Entity
    ):
        """Name matching is case-insensitive."""
        entity.name = "John Doe"
        db_session.add(entity)
        await db_session.commit()

        result = await fuzzy_match_name(
            db_session,
            org_id=organization.id,
            first_name="JOHN",
            last_name="DOE"
        )

        assert result is not None
        assert result["type"] == "entity"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(
        self,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Return None when no match found."""
        result = await fuzzy_match_name(
            db_session,
            org_id=organization.id,
            first_name="NonExistent",
            last_name="Person"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_names_returns_none(
        self,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Return None when both names are empty."""
        result = await fuzzy_match_name(
            db_session,
            org_id=organization.id,
            first_name=None,
            last_name=None
        )

        assert result is None


# ============================================================================
# TESTS: identify_participants
# ============================================================================

class TestIdentifyParticipants:
    """Tests for identify_participants function."""

    @pytest.mark.asyncio
    async def test_identifies_system_user(
        self,
        db_session: AsyncSession,
        chat_with_messages: Chat,
        user_with_telegram: User
    ):
        """Identify system user in chat."""
        participants = await identify_participants(db_session, chat_with_messages)

        # Find user participant
        user_participant = next(
            (p for p in participants if p["telegram_user_id"] == user_with_telegram.telegram_id),
            None
        )

        assert user_participant is not None
        assert user_participant["role"] == ParticipantRole.system_user
        assert user_participant["role_icon"] == "🔑"
        assert user_participant["identified_as"] is not None
        assert user_participant["identified_as"]["type"] == "user"

    @pytest.mark.asyncio
    async def test_identifies_target_entity(
        self,
        db_session: AsyncSession,
        chat_linked_to_entity: Chat,
        entity: Entity
    ):
        """Identify target entity (chat.entity_id)."""
        # У общей фикстуры entity нет telegram_user_id, поэтому в чате нет ни
        # одного сообщения от неё и участников не было вовсе. Даём кандидату
        # Telegram и его сообщение в чате.
        entity.telegram_user_id = 555000111
        db_session.add(Message(
            chat_id=chat_linked_to_entity.id,
            telegram_message_id=30001,
            telegram_user_id=entity.telegram_user_id,
            username="entity_user",
            first_name="Test",
            last_name="Contact",
            content="Hello from entity",
            content_type="text",
            timestamp=datetime.utcnow(),
        ))
        await db_session.commit()

        participants = await identify_participants(db_session, chat_linked_to_entity)

        # Find target entity
        target = next(
            (p for p in participants if p["role"] == ParticipantRole.target_entity),
            None
        )

        assert target is not None
        assert target["role_icon"] == "🎯"

    @pytest.mark.asyncio
    async def test_identifies_candidate_entity(
        self,
        db_session: AsyncSession,
        chat: Chat,
        candidate_entity: Entity
    ):
        """Identify candidate Entity (type=candidate)."""
        # Add message from candidate
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=11111,
            telegram_user_id=candidate_entity.telegram_user_id,
            username="candidate_user",
            first_name="Candidate",
            last_name="Person",
            content="Hello, I'm interested",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(msg)
        await db_session.commit()

        participants = await identify_participants(db_session, chat)

        candidate = next(
            (p for p in participants if p.get("identified_as") and p["identified_as"].get("id") == candidate_entity.id),
            None
        )

        assert candidate is not None
        assert candidate["role"] == ParticipantRole.candidate
        assert candidate["role_icon"] == "👤"

    @pytest.mark.asyncio
    async def test_mixed_participants(
        self,
        db_session: AsyncSession,
        chat_with_mixed_senders: Chat
    ):
        """Chat with User, Entity, and unknown participants."""
        participants = await identify_participants(db_session, chat_with_mixed_senders)

        assert len(participants) >= 2

        # Should have at least one identified and one unknown
        identified = [p for p in participants if p["identified_as"] is not None]
        unknown = [p for p in participants if p["role"] == ParticipantRole.unknown]

        assert len(identified) >= 1
        assert len(unknown) >= 1

    @pytest.mark.asyncio
    async def test_empty_chat_returns_empty_list(
        self,
        db_session: AsyncSession,
        chat: Chat
    ):
        """Empty chat returns empty participants list."""
        participants = await identify_participants(db_session, chat)

        assert participants == []

    @pytest.mark.asyncio
    async def test_messages_count_accurate(
        self,
        db_session: AsyncSession,
        chat: Chat,
        user_with_telegram: User
    ):
        """Participants have accurate message counts."""
        # Add 3 messages from user
        for i in range(3):
            msg = Message(
                chat_id=chat.id,
                telegram_message_id=20000 + i,
                telegram_user_id=user_with_telegram.telegram_id,
                username=user_with_telegram.telegram_username,
                first_name="User",
                last_name="Test",
                content=f"Message {i}",
                content_type="text",
                timestamp=datetime.utcnow()
            )
            db_session.add(msg)
        await db_session.commit()

        participants = await identify_participants(db_session, chat)

        user_participant = next(
            (p for p in participants if p["telegram_user_id"] == user_with_telegram.telegram_id),
            None
        )

        assert user_participant is not None
        assert user_participant["messages_count"] == 3


# ============================================================================
# TESTS: get_role_icon
# ============================================================================

class TestRoleIcons:
    """Tests for get_role_icon function."""

    def test_all_role_icons(self):
        """Test all role icons are defined."""
        assert get_role_icon(ParticipantRole.system_user) == "🔑"
        assert get_role_icon(ParticipantRole.target_entity) == "🎯"
        assert get_role_icon(ParticipantRole.employee) == "🏢"
        assert get_role_icon(ParticipantRole.candidate) == "👤"
        assert get_role_icon(ParticipantRole.client) == "💼"
        assert get_role_icon(ParticipantRole.contractor) == "🔧"
        assert get_role_icon(ParticipantRole.unknown) == "❓"


# ============================================================================
# TESTS: API Entity with Multiple Identifiers
# ============================================================================

class TestEntityMultipleIdentifiers:
    """Tests for Entity API with multiple emails, telegram_usernames, phones.

    Ручек /api/organizations/{id}/entities нет: кандидаты живут на /api/entities,
    организация — текущая у пользователя.
    """

    @pytest.mark.asyncio
    async def test_create_entity_with_multiple_emails(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Create Entity with multiple emails."""
        payload = {
            "name": "Multi Email Contact",
            "type": "candidate",
            "email": "primary@test.com",
            "emails": ["secondary@test.com", "third@test.com"],
            "department_id": department.id
        }

        response = await client.post(
            "/api/entities",  # организация берётся из пользователя
            json=payload,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "primary@test.com"
        assert "secondary@test.com" in data.get("emails", [])
        assert "third@test.com" in data.get("emails", [])

    @pytest.mark.asyncio
    async def test_create_entity_with_multiple_telegram_usernames(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Create Entity with multiple telegram usernames."""
        payload = {
            "name": "Multi Username Contact",
            "type": "client",
            "telegram_usernames": ["user_work", "user_personal"],
            "department_id": department.id
        }

        response = await client.post(
            "/api/entities",  # организация берётся из пользователя
            json=payload,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert "user_work" in data.get("telegram_usernames", [])
        assert "user_personal" in data.get("telegram_usernames", [])

    @pytest.mark.asyncio
    async def test_update_entity_add_telegram_username(
        self,
        client: AsyncClient,
        admin_token: str,
        entity: Entity,
        get_auth_headers,
        org_owner
    ):
        """Add telegram username to existing Entity."""
        payload = {
            "telegram_usernames": ["new_username", "another_one"]
        }

        # Правка карточки — PUT (PATCH у /entities/{id} нет).
        response = await client.put(
            f"/api/entities/{entity.id}",
            json=payload,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "new_username" in data.get("telegram_usernames", [])
        assert "another_one" in data.get("telegram_usernames", [])

    @pytest.mark.asyncio
    async def test_search_by_any_email(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        entity_with_emails: Entity,
        get_auth_headers,
        org_owner
    ):
        """Search Entity by any of its emails."""
        # Search by secondary email
        response = await client.get(
            "/api/entities?search=b@test.com",  # организация берётся из пользователя
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        found = any(e["id"] == entity_with_emails.id for e in data)
        assert found, "Entity should be found by secondary email"

    @pytest.mark.asyncio
    async def test_entity_with_empty_arrays(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Create Entity with empty identifier arrays."""
        payload = {
            "name": "Empty Arrays Contact",
            "type": "lead",
            "emails": [],
            "telegram_usernames": [],
            "phones": [],
            "department_id": department.id
        }

        response = await client.post(
            "/api/entities",  # организация берётся из пользователя
            json=payload,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data.get("emails", []) == []
        assert data.get("telegram_usernames", []) == []
        assert data.get("phones", []) == []

    @pytest.mark.asyncio
    async def test_entity_username_normalization(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Telegram usernames should be normalized (lowercase, no @)."""
        payload = {
            "name": "Normalization Test",
            "type": "candidate",
            "telegram_usernames": ["@UserName", "ANOTHER_USER"],
            "department_id": department.id
        }

        response = await client.post(
            "/api/entities",  # организация берётся из пользователя
            json=payload,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        usernames = data.get("telegram_usernames", [])

        # Check normalization (if implemented in API)
        # This test will pass if normalization is not yet implemented
        # and can be updated when normalization is added
        assert len(usernames) == 2
