"""
Tests for Entity multiple identifiers functionality.
Tests cover telegram_usernames, emails, and phones arrays.
"""
import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Department, Message, Chat, ChatType
)


class TestEntityMultipleIdentifiers:
    """Tests for Entity multiple identifiers (telegram_usernames, emails, phones)."""

    @pytest.fixture(autouse=True)
    def _admin_in_org(self, org_owner):
        """admin_user — владелец организации. Без членства в орге ручки
        /entities отвечают 403 (создание, карточка) или пустым списком."""

    @pytest.mark.asyncio
    async def test_create_entity_with_multiple_identifiers(
        self, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test creating an entity with multiple identifiers."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Test Candidate",
                "status": "new",
                "email": "primary@test.com",
                "telegram_usernames": ["@user1", "user2", "@USER3"],  # Mixed formats
                "emails": ["secondary@test.com", "tertiary@test.com"],
                "phones": ["+1234567890", "+9876543210"],
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201  # создание отвечает 201 Created
        data = response.json()

        # Verify normalized telegram usernames (lowercase, without @)
        assert set(data["telegram_usernames"]) == {"user1", "user2", "user3"}

        # Verify emails
        assert set(data["emails"]) == {"secondary@test.com", "tertiary@test.com"}

        # Verify phones
        assert set(data["phones"]) == {"+1234567890", "+9876543210"}

    @pytest.mark.asyncio
    async def test_create_entity_with_invalid_email_in_array(
        self, client, admin_user, admin_token, department, get_auth_headers
    ):
        """Test that creating an entity with invalid email in array fails."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Test Candidate",
                "status": "new",
                "emails": ["valid@test.com", "invalid-email"],  # One invalid
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Invalid email format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_entity_removes_duplicate_identifiers(
        self, client, admin_user, admin_token, department, get_auth_headers
    ):
        """Test that duplicate identifiers are removed."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Test Candidate",
                "status": "new",
                "telegram_usernames": ["@user1", "user1", "USER1"],  # Duplicates
                "emails": ["test@test.com", "test@test.com"],  # Duplicates
                "phones": ["+123", "+123"],  # Duplicates
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201  # создание отвечает 201 Created
        data = response.json()

        # All duplicates should be removed
        assert data["telegram_usernames"] == ["user1"]
        assert data["emails"] == ["test@test.com"]
        assert data["phones"] == ["+123"]

    @pytest.mark.asyncio
    async def test_search_by_identifier_email(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test searching entities by email identifier."""
        # Create entity with multiple emails
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            email="primary@test.com",
            emails=["secondary@test.com", "tertiary@test.com"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Search by secondary email
        response = await client.get(
            "/api/entities?identifier=secondary@test.com",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        found = any(e["id"] == entity.id for e in data)
        assert found, "Entity should be found by secondary email"

    @pytest.mark.asyncio
    async def test_search_by_identifier_telegram_username(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test searching entities by telegram username."""
        # Create entity with telegram usernames
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            telegram_usernames=["johndoe", "john_doe_alt"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Search by username (with @)
        response = await client.get(
            "/api/entities?identifier=@johndoe",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        found = any(e["id"] == entity.id for e in data)
        assert found, "Entity should be found by telegram username"

        # Search by username (without @)
        response = await client.get(
            "/api/entities?identifier=john_doe_alt",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        found = any(e["id"] == entity.id for e in data)
        assert found, "Entity should be found by alt telegram username"

    @pytest.mark.asyncio
    async def test_search_by_identifier_phone(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test searching entities by phone number."""
        # Create entity with multiple phones
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            phone="+1234567890",
            phones=["+9876543210", "+5555555555"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Search by phone in array
        # Через params: «+» в сыром адресе — это пробел, и искался «9876543210».
        response = await client.get(
            "/api/entities",
            params={"identifier": "+9876543210"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        found = any(e["id"] == entity.id for e in data)
        assert found, "Entity should be found by phone in phones array"

    @pytest.mark.asyncio
    async def test_get_entity_chat_participants(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test getting chat participants for an entity."""
        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.flush()

        # Create chat linked to entity
        chat = Chat(
            org_id=organization.id,
            telegram_chat_id=123456789,
            title="Test Chat",
            chat_type=ChatType.hr,
            owner_id=admin_user.id,
            entity_id=entity.id
        )
        db_session.add(chat)
        await db_session.flush()

        # Create messages from different participants
        messages = [
            Message(
                chat_id=chat.id,
                telegram_user_id=111111,
                username="john_doe",
                first_name="John",
                last_name="Doe",
                content="Hello",
                content_type="text"
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=222222,
                username="jane_smith",
                first_name="Jane",
                last_name="Smith",
                content="Hi",
                content_type="text"
            ),
            # Another message from John (should not duplicate)
            Message(
                chat_id=chat.id,
                telegram_user_id=111111,
                username="john_doe",
                first_name="John",
                last_name="Doe",
                content="How are you?",
                content_type="text"
            ),
        ]
        db_session.add_all(messages)
        await db_session.commit()

        # Get participants
        response = await client.get(
            f"/api/entities/{entity.id}/chat-participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should have 2 unique participants
        assert len(data) == 2

        # Verify participant data
        participants_by_id = {p["telegram_user_id"]: p for p in data}

        assert 111111 in participants_by_id
        assert participants_by_id[111111]["telegram_username"] == "john_doe"
        assert participants_by_id[111111]["name"] == "John Doe"
        assert chat.id in participants_by_id[111111]["chat_ids"]

        assert 222222 in participants_by_id
        assert participants_by_id[222222]["telegram_username"] == "jane_smith"
        assert participants_by_id[222222]["name"] == "Jane Smith"

    @pytest.mark.asyncio
    async def test_get_entity_chat_participants_no_chats(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test getting participants when entity has no chats."""
        # Create entity without chats
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        # Get participants
        response = await client.get(
            f"/api/entities/{entity.id}/chat-participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_entities_returns_multiple_identifiers(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test that list_entities returns multiple identifiers."""
        # Create entity with multiple identifiers
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            telegram_usernames=["user1", "user2"],
            emails=["email1@test.com", "email2@test.com"],
            phones=["+111", "+222"]
        )
        db_session.add(entity)
        await db_session.commit()

        # List entities
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find our entity
        entity_data = next((e for e in data if e["id"] == entity.id), None)
        assert entity_data is not None

        # Verify multiple identifiers are returned
        assert set(entity_data["telegram_usernames"]) == {"user1", "user2"}
        assert set(entity_data["emails"]) == {"email1@test.com", "email2@test.com"}
        assert set(entity_data["phones"]) == {"+111", "+222"}

    @pytest.mark.asyncio
    async def test_get_entity_returns_multiple_identifiers(
        self, db_session, client, admin_user, admin_token, organization, department, get_auth_headers
    ):
        """Test that get_entity returns multiple identifiers."""
        # Create entity with multiple identifiers
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            telegram_usernames=["user1", "user2"],
            emails=["email1@test.com", "email2@test.com"],
            phones=["+111", "+222"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Get entity
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify multiple identifiers are returned
        assert set(data["telegram_usernames"]) == {"user1", "user2"}
        assert set(data["emails"]) == {"email1@test.com", "email2@test.com"}
        assert set(data["phones"]) == {"+111", "+222"}
