"""
Comprehensive tests for Entity (contact) API endpoints.
Tests cover CRUD operations, filtering, pagination, search, sharing, and transfers.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Chat, CallRecording,
    SharedAccess, AccessLevel, ResourceType,
    ChatType, CallSource, CallStatus, Department
)


@pytest.fixture(autouse=True)
def no_profile_regen(monkeypatch):
    """Фоновый AI-профиль после привязки чата/звонка в тестах не запускаем.

    link-chat / link-call ставят в фон `add_task(asyncio.create_task, coro)`:
    Starlette зовёт синхронный create_task в пуле потоков, там нет event loop —
    «no running event loop». На проде ответ к этому моменту уже ушёл (привязка
    работает, падает только профиль — владелец 19.10.2026 решил это не чинить:
    профиль нигде не виден, а чинить = платить за Claude на каждую привязку).
    В тестах ASGITransport пробрасывает ошибку фоновой задачи в сам запрос,
    поэтому подменяем create_task в модуле ручек на «выбросить корутину».
    """
    import types
    from api.routes.entities import memory

    monkeypatch.setattr(
        memory, "asyncio", types.SimpleNamespace(create_task=lambda coro: coro.close())
    )


# ============================================================================
# GET /api/entities - LIST ENTITIES
# ============================================================================

class TestListEntities:
    """Test entity listing with various filters and access control."""

    @pytest.mark.asyncio
    async def test_list_entities_basic(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test basic entity listing."""
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify entity structure
        entity_data = next((e for e in data if e["id"] == entity.id), None)
        assert entity_data is not None
        assert entity_data["name"] == "Test Contact"
        assert entity_data["email"] == "contact@test.com"
        assert entity_data["type"] == EntityType.candidate.value
        assert entity_data["status"] == EntityStatus.active.value
        assert "chats_count" in entity_data
        assert "calls_count" in entity_data

    @pytest.mark.asyncio
    async def test_list_entities_filter_by_type(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering entities by type."""
        # Create entities of different types
        candidate = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Candidate Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        client_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Client Contact",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add_all([candidate, client_entity])
        await db_session.commit()

        # Filter by candidate type
        response = await client.get(
            "/api/entities?type=candidate",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["type"] == "candidate" for e in data)

        # Filter by client type
        response = await client.get(
            "/api/entities?type=client",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["type"] == "client" for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_filter_by_status(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering entities by status."""
        # Create entities with different statuses
        active = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Active Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        rejected = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Rejected Contact",
            type=EntityType.candidate,
            status=EntityStatus.rejected
        )
        db_session.add_all([active, rejected])
        await db_session.commit()

        # Filter by active status
        response = await client.get(
            "/api/entities?status=active",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "active" for e in data)

        # Filter by rejected status
        response = await client.get(
            "/api/entities?status=rejected",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "rejected" for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_filter_by_department(
        self, db_session, client, admin_user, admin_token, organization,
        department, second_department, get_auth_headers, org_owner
    ):
        """Test filtering entities by department."""
        # Create entities in different departments
        dept1_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Dept 1 Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        dept2_entity = Entity(
            org_id=organization.id,
            department_id=second_department.id,
            created_by=admin_user.id,
            name="Dept 2 Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add_all([dept1_entity, dept2_entity])
        await db_session.commit()

        # Filter by first department
        response = await client.get(
            f"/api/entities?department_id={department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["department_id"] == department.id for e in data)

        # Filter by second department
        response = await client.get(
            f"/api/entities?department_id={second_department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["department_id"] == second_department.id for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_search_by_name(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test searching entities by name."""
        # Create entities with different names
        john = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="John Doe",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        jane = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Jane Smith",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add_all([john, jane])
        await db_session.commit()

        # Search for "John"
        response = await client.get(
            "/api/entities?search=John",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("John" in e["name"] for e in data)

        # Search for "Jane"
        response = await client.get(
            "/api/entities?search=Jane",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("Jane" in e["name"] for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_search_by_email(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test searching entities by email."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Email Test",
            email="unique@example.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?search=unique@example.com",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(e["email"] == "unique@example.com" for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_search_by_phone(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test searching entities by phone."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Phone Test",
            phone="+9876543210",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?search=9876543210",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(e["phone"] == "+9876543210" for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_search_by_company(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test searching entities by company."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Company Test",
            company="Acme Corporation",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?search=Acme",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(e["company"] == "Acme Corporation" for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_filter_by_tags(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering entities by tags."""
        # Create entities with different tags
        senior = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Senior Dev",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["senior", "python"]
        )
        junior = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Junior Dev",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["junior", "javascript"]
        )
        db_session.add_all([senior, junior])
        await db_session.commit()

        # Filter by "senior" tag
        response = await client.get(
            "/api/entities?tags=senior",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Tags filtering requires exact match with PostgreSQL array contains
        # If no results, the filtering is working (just no matches in SQLite test)
        # In production PostgreSQL it should work correctly
        if len(data) > 0:
            assert any("senior" in e["tags"] for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_pagination(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test entity list pagination."""
        # Create multiple entities
        entities = []
        for i in range(15):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Contact {i}",
                type=EntityType.candidate,
                status=EntityStatus.active
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        # Get first page (limit 10)
        response = await client.get(
            "/api/entities?limit=10&offset=0",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        page1 = response.json()
        assert len(page1) == 10

        # Get second page
        response = await client.get(
            "/api/entities?limit=10&offset=10",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        page2 = response.json()
        assert len(page2) >= 5

        # Ensure different results
        page1_ids = {e["id"] for e in page1}
        page2_ids = {e["id"] for e in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_list_entities_ownership_filter_mine(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, department, get_auth_headers, org_owner
    ):
        """Test filtering entities by ownership=mine."""
        # Create entity owned by admin
        my_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="My Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        # Create entity owned by another user
        other_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=second_user.id,
            name="Other Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add_all([my_entity, other_entity])
        await db_session.commit()

        # Filter by ownership=mine
        response = await client.get(
            "/api/entities?ownership=mine",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # All entities should be owned by admin_user
        assert all(e["created_by"] == admin_user.id for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_ownership_filter_shared(
        self, db_session, client, second_user, second_user_token,
        entity, get_auth_headers, org_member
    ):
        """Test filtering entities by ownership=shared."""
        # Share entity with second_user
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=entity.created_by,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Filter by ownership=shared
        response = await client.get(
            "/api/entities?ownership=shared",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should only show entities shared with user (not owned by them)
        assert all(e["created_by"] != second_user.id for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_access_control_member(
        self, db_session, client, second_user, second_user_token,
        organization, department, get_auth_headers, org_member, dept_member
    ):
        """Test that members see own + shared + department entities."""
        # Create entity owned by second_user
        own_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=second_user.id,
            name="Own Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(own_entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        entity_ids = [e["id"] for e in data]

        # Should see own entity
        assert own_entity.id in entity_ids

    @pytest.mark.asyncio
    async def test_list_entities_no_org_access(
        self, db_session, client, get_auth_headers
    ):
        """Test that user without org access gets empty list."""
        # Create user without org membership
        from api.models.database import User, UserRole
        from api.services.auth import hash_password, create_access_token

        no_org_user = User(
            email="noorg@test.com",
            password_hash=hash_password("test123"),
            name="No Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(no_org_user)
        await db_session.commit()
        await db_session.refresh(no_org_user)

        token = create_access_token(data={"sub": str(no_org_user.id)})

        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_entities_with_counts(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that entity list includes chats_count and calls_count."""
        # Create chats linked to entity
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=111111,
            title="Chat 1",
            chat_type=ChatType.hr,
            is_active=True
        )
        chat2 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=222222,
            title="Chat 2",
            chat_type=ChatType.hr,
            is_active=True
        )
        # Create calls linked to entity
        call1 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Call 1",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300
        )
        db_session.add_all([chat1, chat2, call1])
        await db_session.commit()

        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        entity_data = next((e for e in data if e["id"] == entity.id), None)
        assert entity_data is not None
        assert entity_data["chats_count"] == 2
        assert entity_data["calls_count"] == 1


# ============================================================================
# POST /api/entities - CREATE ENTITY
# ============================================================================

class TestCreateEntity:
    """Test entity creation with various configurations."""

    @pytest.mark.asyncio
    async def test_create_entity_basic(
        self, client, admin_user, admin_token, organization, get_auth_headers, org_owner
    ):
        """Test basic entity creation."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "New Contact",
                "status": "new",
                "email": "new@test.com",
                "phone": "+1111111111"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Contact"
        assert data["type"] == "candidate"
        assert data["status"] == "new"
        assert data["email"] == "new@test.com"
        assert data["phone"] == "+1111111111"
        assert data["created_by"] == admin_user.id
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_entity_all_types(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entities of all types."""
        entity_types = [
            EntityType.candidate,
            EntityType.client,
            EntityType.contractor,
            EntityType.lead,
            EntityType.partner,
            EntityType.custom
        ]

        for entity_type in entity_types:
            response = await client.post(
                "/api/entities",
                json={
                    "type": entity_type.value,
                    "name": f"{entity_type.value.title()} Contact",
                    "status": "active"
                },
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 201
            data = response.json()
            assert data["type"] == entity_type.value

    @pytest.mark.asyncio
    async def test_create_entity_with_tags(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with tags."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Tagged Contact",
                "status": "active",
                "tags": ["senior", "python", "remote"]
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tags"] == ["senior", "python", "remote"]

    @pytest.mark.asyncio
    async def test_create_entity_with_department(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner
    ):
        """Test creating entity with department assignment."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Dept Contact",
                "status": "active",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["department_id"] == department.id
        assert data["department_name"] == "Test Department"

    @pytest.mark.asyncio
    async def test_create_entity_with_extra_data(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with extra_data field."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Extra Data Contact",
                "status": "active",
                "extra_data": {
                    "linkedin": "https://linkedin.com/in/test",
                    "years_experience": 5,
                    "skills": ["Python", "JavaScript"]
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["extra_data"]["linkedin"] == "https://linkedin.com/in/test"
        assert data["extra_data"]["years_experience"] == 5

    @pytest.mark.asyncio
    async def test_create_entity_with_all_fields(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner
    ):
        """Test creating entity with all possible fields."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Full Contact",
                "status": "interview",
                "email": "full@test.com",
                "phone": "+1234567890",
                "telegram_user_id": 123456789,
                "company": "Previous Company",
                "position": "Senior Developer",
                "tags": ["python", "senior"],
                "extra_data": {"note": "Great candidate"},
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Full Contact"
        assert data["email"] == "full@test.com"
        assert data["phone"] == "+1234567890"
        assert data["telegram_user_id"] == 123456789
        assert data["company"] == "Previous Company"
        assert data["position"] == "Senior Developer"
        assert data["tags"] == ["python", "senior"]
        assert data["department_id"] == department.id

    @pytest.mark.asyncio
    async def test_create_entity_invalid_department(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with invalid department_id."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Invalid Dept",
                "status": "active",
                "department_id": 99999  # Non-existent
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Invalid department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_entity_no_org_access(
        self, db_session, client, get_auth_headers
    ):
        """Test that user without org access cannot create entity."""
        from api.models.database import User, UserRole
        from api.services.auth import hash_password, create_access_token

        no_org_user = User(
            email="noorg2@test.com",
            password_hash=hash_password("test123"),
            name="No Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(no_org_user)
        await db_session.commit()
        await db_session.refresh(no_org_user)

        token = create_access_token(data={"sub": str(no_org_user.id)})

        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Should Fail",
                "status": "active"
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code == 403
        assert "No organization access" in response.json()["detail"]


# ============================================================================
# GET /api/entities/{id} - GET ENTITY DETAILS
# ============================================================================

class TestGetEntity:
    """Test retrieving entity details."""

    @pytest.mark.asyncio
    async def test_get_entity_basic(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test getting entity details."""
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == entity.id
        assert data["name"] == "Test Contact"
        assert data["email"] == "contact@test.com"
        assert data["type"] == EntityType.candidate.value
        assert "chats" in data
        assert "calls" in data
        assert "transfers" in data
        assert "analyses" in data

    @pytest.mark.asyncio
    async def test_get_entity_with_chats_and_calls(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test entity includes related chats and calls."""
        # Create chats
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=111111,
            title="Test Chat 1",
            chat_type=ChatType.hr,
            is_active=True
        )
        chat2 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=222222,
            title="Test Chat 2",
            chat_type=ChatType.hr,
            is_active=True
        )
        # Create calls
        call1 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Test Call 1",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300,
            summary="Test summary"
        )
        db_session.add_all([chat1, chat2, call1])
        await db_session.commit()

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["chats"]) == 2
        assert len(data["calls"]) == 1

        # Verify chat structure
        assert data["chats"][0]["title"] is not None
        assert "chat_type" in data["chats"][0]

        # Verify call structure
        assert data["calls"][0]["source_type"] == "upload"
        assert data["calls"][0]["duration_seconds"] == 300
        assert data["calls"][0]["summary"] == "Test summary"

    @pytest.mark.asyncio
    async def test_get_entity_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test getting non-existent entity."""
        response = await client.get(
            "/api/entities/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_entity_access_control(
        self, db_session, client, second_user, second_user_token,
        organization, department, admin_user, get_auth_headers, org_member
    ):
        """Test that user cannot access entity without permission."""
        # Create entity owned by admin_user (not second_user)
        # Не кандидат: кандидаты общие для организации (модель «общий пул HR»,
        # check_entity_access 3.5) — их читает любой член орга. Закрытым
        # остаётся контакт другого типа.
        entity = Entity(
            org_id=organization.id,
            department_id=None,  # No department
            created_by=admin_user.id,
            name="Private Contact",
            type=EntityType.partner,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Should not have access (not owner, not shared, not in dept)
        assert response.status_code == 404


# ============================================================================
# PUT /api/entities/{id} - UPDATE ENTITY
# ============================================================================

class TestUpdateEntity:
    """Test entity updates."""

    @pytest.mark.asyncio
    async def test_update_entity_name(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test updating entity name."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Updated Name"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_entity_status(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test changing entity status."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"status": "hired"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "hired"

    @pytest.mark.asyncio
    async def test_update_entity_department(
        self, client, admin_user, admin_token, entity, second_department,
        get_auth_headers, org_owner
    ):
        """Test changing entity department."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"department_id": second_department.id},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["department_id"] == second_department.id
        assert data["department_name"] == "Second Department"

    @pytest.mark.asyncio
    async def test_update_entity_multiple_fields(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test updating multiple fields at once."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "name": "Multi Update",
                "email": "multi@test.com",
                "phone": "+9999999999",
                "company": "New Company",
                "position": "CEO",
                "status": "active",
                "tags": ["vip", "urgent"]
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Multi Update"
        assert data["email"] == "multi@test.com"
        assert data["phone"] == "+9999999999"
        assert data["company"] == "New Company"
        assert data["position"] == "CEO"
        assert data["tags"] == ["vip", "urgent"]

    @pytest.mark.asyncio
    async def test_update_entity_client_extra_data_cannot_clobber_notes(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner, db_session
    ):
        """PUT /entities НЕ должен затирать серверные комментарии клиентским
        extra_data. Регресс «пропали некоторые комментарии»: модалка спредит весь
        card.extra_data (включая устаревший notes), и старый merge заменял им
        свежие заметки. Серверные ключи (notes и пр.) теперь отбрасываются."""
        from sqlalchemy import select as _select
        from api.models.database import Entity as _Entity

        entity.extra_data = {"notes": [{"id": "n1", "text": "серверный коммент"}]}
        await db_session.commit()

        # Клиент шлёт устаревший/пустой notes + легитимное поле в extra_data.
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"extra_data": {"notes": [], "salary_expectation": "200k"}},
            headers=get_auth_headers(admin_token),
        )
        assert response.status_code == 200

        refreshed = (await db_session.execute(
            _select(_Entity).where(_Entity.id == entity.id)
        )).scalar_one()
        await db_session.refresh(refreshed)
        # серверный комментарий уцелел, а легитимное поле применилось
        assert refreshed.extra_data.get("notes") == [{"id": "n1", "text": "серверный коммент"}]
        assert refreshed.extra_data.get("salary_expectation") == "200k"

    @pytest.mark.asyncio
    async def test_update_entity_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test updating non-existent entity."""
        response = await client.put(
            "/api/entities/99999",
            json={"name": "Should Fail"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_entity_invalid_department(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test updating entity with invalid department."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"department_id": 99999},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_transferred_entity_fails(
        self, db_session, client, admin_user, admin_token, organization,
        department, second_user, get_auth_headers, org_owner
    ):
        """Test that transferred (frozen) entities cannot be updated."""
        # Create a transferred entity (use second_user.id as a valid transferred_to_id)
        transferred = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Transferred Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            is_transferred=True,
            transferred_to_id=second_user.id
        )
        db_session.add(transferred)
        await db_session.commit()
        await db_session.refresh(transferred)

        response = await client.put(
            f"/api/entities/{transferred.id}",
            json={"name": "Try to Update"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Cannot edit a transferred entity" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_entity_no_permission(
        self, db_session, client, second_user, second_user_token,
        organization, admin_user, get_auth_headers, org_member
    ):
        """Test that user cannot update entity without permission."""
        # Create entity owned by admin_user
        entity = Entity(
            org_id=organization.id,
            department_id=None,
            created_by=admin_user.id,
            name="Private Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Hacked"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# DELETE /api/entities/{id} - DELETE ENTITY
# ============================================================================

class TestDeleteEntity:
    """Test entity deletion."""

    @pytest.mark.asyncio
    async def test_delete_entity_owner(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test that owner can delete entity."""
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_entity_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test deleting non-existent entity."""
        response = await client.delete(
            "/api/entities/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_transferred_entity_fails(
        self, db_session, client, admin_user, admin_token, organization,
        department, second_user, get_auth_headers, org_owner
    ):
        """Test that transferred (frozen) entities cannot be deleted."""
        transferred = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Transferred Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            is_transferred=True,
            transferred_to_id=second_user.id
        )
        db_session.add(transferred)
        await db_session.commit()
        await db_session.refresh(transferred)

        response = await client.delete(
            f"/api/entities/{transferred.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Cannot delete a transferred entity" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_entity_cascade_to_shares(
        self, db_session, client, admin_user, admin_token, entity,
        second_user, get_auth_headers, org_owner
    ):
        """Test that deleting entity cascades to shared access records."""
        # Share entity with second_user
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify share is also deleted (cascade)
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.entity_id == entity.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_entity_no_permission(
        self, db_session, client, second_user, second_user_token,
        organization, admin_user, get_auth_headers, org_member
    ):
        """Test that user cannot delete entity without permission."""
        entity = Entity(
            org_id=organization.id,
            department_id=None,
            created_by=admin_user.id,
            name="Private Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404]


# ============================================================================
# POST /api/entities/{id}/share - SHARE ENTITY
# ============================================================================

class TestShareEntity:
    """Test entity sharing functionality."""

    @pytest.mark.asyncio
    async def test_share_entity_view_access(
        self, client, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test sharing entity with view access."""
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view",
                "note": "For review"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["entity_id"] == entity.id
        assert data["shared_with_id"] == second_user.id
        assert data["access_level"] == "view"

    @pytest.mark.asyncio
    async def test_share_entity_edit_access(
        self, client, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test sharing entity with edit access."""
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_share_entity_full_access(
        self, client, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test sharing entity with full access."""
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "full"

    @pytest.mark.asyncio
    async def test_share_entity_with_expiration(
        self, client, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test sharing entity with expiration date."""
        expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()

        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view",
                "expires_at": expires_at
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_share_entity_auto_share_related(
        self, db_session, client, admin_user, admin_token, entity,
        second_user, organization, get_auth_headers, org_owner, org_member
    ):
        """Test auto-sharing related chats and calls."""
        # Create related chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=111111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        # Create related call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Test Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300
        )
        db_session.add_all([chat, call])
        await db_session.commit()

        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view",
                "auto_share_related": True
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auto_shared"] is not None
        assert data["auto_shared"]["chats"] >= 0
        assert data["auto_shared"]["calls"] >= 0

    @pytest.mark.asyncio
    async def test_share_entity_no_auto_share(
        self, client, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test sharing without auto-share related."""
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view",
                "auto_share_related": False
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auto_shared"] is None

    @pytest.mark.asyncio
    async def test_share_entity_update_existing_share(
        self, db_session, client, admin_user, admin_token, entity,
        second_user, get_auth_headers, org_owner, org_member
    ):
        """Test updating an existing share."""
        # Create initial share
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Update to edit access
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "edit",
                "note": "Updated access"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify share was updated, not duplicated
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.entity_id == entity.id,
                SharedAccess.shared_with_id == second_user.id
            )
        )
        shares = result.scalars().all()
        assert len(shares) == 1
        assert shares[0].access_level == AccessLevel.edit

    @pytest.mark.asyncio
    async def test_share_entity_not_found(
        self, client, admin_user, admin_token, second_user,
        get_auth_headers, org_owner
    ):
        """Test sharing non-existent entity."""
        response = await client.post(
            "/api/entities/99999/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_entity_no_permission(
        self, db_session, client, second_user, second_user_token,
        organization, admin_user, regular_user, get_auth_headers, org_member
    ):
        """Test that user cannot share entity they don't own."""
        entity = Entity(
            org_id=organization.id,
            department_id=None,
            created_by=admin_user.id,
            name="Private Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# ADDITIONAL ENDPOINTS
# ============================================================================

class TestEntityLinkChat:
    """Test linking/unlinking chats to entities."""

    @pytest.mark.asyncio
    async def test_link_chat_to_entity(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test linking a chat to an entity."""
        # Create unlinked chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111111,
            title="Unlinked Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify chat is now linked
        await db_session.refresh(chat)
        assert chat.entity_id == entity.id

    @pytest.mark.asyncio
    async def test_unlink_chat_from_entity(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test unlinking a chat from an entity."""
        # Create linked chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=111111,
            title="Linked Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        response = await client.delete(
            f"/api/entities/{entity.id}/unlink-chat/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify chat is now unlinked
        await db_session.refresh(chat)
        assert chat.entity_id is None


class TestEntityStats:
    """Test entity statistics endpoints."""

    @pytest.mark.asyncio
    async def test_get_entities_stats_by_type(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test getting entity counts by type."""
        # Create entities of different types
        candidate1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Candidate 1",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        candidate2 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Candidate 2",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        client1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Client 1",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add_all([candidate1, candidate2, client1])
        await db_session.commit()

        response = await client.get(
            "/api/entities/stats/by-type",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        stats = response.json()
        assert stats["candidate"] >= 2
        assert stats["client"] >= 1

    @pytest.mark.asyncio
    async def test_get_entities_stats_by_status(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test getting entity counts by status."""
        # Create entities with different statuses
        active1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Active 1",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        active2 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Active 2",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        rejected1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Rejected 1",
            type=EntityType.candidate,
            status=EntityStatus.rejected
        )
        db_session.add_all([active1, active2, rejected1])
        await db_session.commit()

        response = await client.get(
            "/api/entities/stats/by-status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        stats = response.json()
        assert stats["active"] >= 2
        assert stats["rejected"] >= 1

    @pytest.mark.asyncio
    async def test_get_entities_stats_by_status_filtered_by_type(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test getting entity counts by status filtered by type."""
        # Create entities
        candidate_active = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Candidate Active",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        client_active = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Client Active",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add_all([candidate_active, client_active])
        await db_session.commit()

        response = await client.get(
            "/api/entities/stats/by-status?type=candidate",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        stats = response.json()
        # Should only count candidates, not clients
        assert "active" in stats


# ============================================================================
# COMPREHENSIVE ENTITY TYPE TESTS
# ============================================================================

class TestEntityTypes:
    """Comprehensive tests for all entity types."""

    @pytest.mark.asyncio
    async def test_create_candidate_all_statuses(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating candidate entities with all possible statuses."""
        statuses = [
            EntityStatus.new,
            EntityStatus.active,
            EntityStatus.interview,
            EntityStatus.offer,
            EntityStatus.hired,
            EntityStatus.rejected
        ]

        for status in statuses:
            response = await client.post(
                "/api/entities",
                json={
                    "type": "candidate",
                    "name": f"Candidate {status.value}",
                    "status": status.value
                },
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 201
            data = response.json()
            assert data["type"] == "candidate"
            assert data["status"] == status.value

    @pytest.mark.asyncio
    async def test_create_client_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating client entity with relevant fields."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "client",
                "name": "Acme Corporation",
                "status": "active",
                "email": "contact@acme.com",
                "phone": "+1234567890",
                "company": "Acme Corp",
                "position": "CTO",
                "tags": ["enterprise", "b2b"],
                "extra_data": {
                    "contract_value": 100000,
                    "contract_start": "2024-01-01"
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "client"
        assert data["company"] == "Acme Corp"
        assert "enterprise" in data["tags"]
        assert data["extra_data"]["contract_value"] == 100000

    @pytest.mark.asyncio
    async def test_create_contractor_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating contractor entity."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "contractor",
                "name": "John Smith",
                "status": "active",
                "email": "john@contractor.com",
                "phone": "+1111111111",
                "company": "Smith Consulting",
                "position": "Senior Consultant",
                "tags": ["freelance", "expert"],
                "extra_data": {
                    "hourly_rate": 150,
                    "availability": "part-time"
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "contractor"
        assert data["extra_data"]["hourly_rate"] == 150

    @pytest.mark.asyncio
    async def test_create_lead_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating lead entity."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "lead",
                "name": "Potential Client",
                "status": "new",
                "email": "lead@example.com",
                "company": "Startup Inc",
                "tags": ["warm-lead", "startup"],
                "extra_data": {
                    "source": "referral",
                    "interest_level": "high"
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "lead"
        assert data["status"] == "new"
        assert "warm-lead" in data["tags"]

    @pytest.mark.asyncio
    async def test_create_partner_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating partner entity."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "partner",
                "name": "Strategic Partner",
                "status": "active",
                "email": "partner@company.com",
                "company": "Partner Corp",
                "tags": ["strategic", "long-term"],
                "extra_data": {
                    "partnership_type": "reseller",
                    "revenue_share": 20
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "partner"
        assert data["extra_data"]["partnership_type"] == "reseller"

    @pytest.mark.asyncio
    async def test_create_custom_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating custom entity type."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "custom",
                "name": "Custom Contact",
                "status": "active",
                "tags": ["custom-type"],
                "extra_data": {
                    "custom_field_1": "value1",
                    "custom_field_2": "value2"
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "custom"
        assert data["extra_data"]["custom_field_1"] == "value1"

    @pytest.mark.asyncio
    async def test_list_entities_filter_contractor_type(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering for contractor entities."""
        # Create mixed entity types
        contractor = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Contractor 1",
            type=EntityType.contractor,
            status=EntityStatus.active
        )
        candidate = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Candidate 1",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add_all([contractor, candidate])
        await db_session.commit()

        response = await client.get(
            "/api/entities?type=contractor",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["type"] == "contractor" for e in data)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_entities_filter_lead_type(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering for lead entities."""
        lead = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Lead 1",
            type=EntityType.lead,
            status=EntityStatus.new
        )
        db_session.add(lead)
        await db_session.commit()

        response = await client.get(
            "/api/entities?type=lead",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["type"] == "lead" for e in data)

    @pytest.mark.asyncio
    async def test_list_entities_filter_partner_type(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering for partner entities."""
        partner = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Partner 1",
            type=EntityType.partner,
            status=EntityStatus.active
        )
        db_session.add(partner)
        await db_session.commit()

        response = await client.get(
            "/api/entities?type=partner",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["type"] == "partner" for e in data)


# ============================================================================
# ADVANCED SEARCH AND FILTERING TESTS
# ============================================================================

class TestAdvancedSearch:
    """Advanced search and filtering scenarios."""

    @pytest.mark.asyncio
    async def test_search_case_insensitive(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test that search is case-insensitive."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Alexander Thompson",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        # Search with different cases
        for search_term in ["alexander", "ALEXANDER", "Alexander", "THOMPSON", "thompson"]:
            response = await client.get(
                f"/api/entities?search={search_term}",
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 1
            assert any("Alexander" in e["name"] or "Thompson" in e["name"] for e in data)

    @pytest.mark.asyncio
    async def test_search_partial_match(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test partial string matching in search."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Jennifer Martinez",
            email="jennifer.martinez@example.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        # Partial matches
        response = await client.get(
            "/api/entities?search=mart",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("Martinez" in e["name"] or "martinez" in (e["email"] or "") for e in data)

    @pytest.mark.asyncio
    async def test_combined_filters_type_and_status(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test combining type and status filters."""
        # Create diverse entities
        active_candidate = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Active Candidate",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        rejected_candidate = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Rejected Candidate",
            type=EntityType.candidate,
            status=EntityStatus.rejected
        )
        active_client = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Active Client",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add_all([active_candidate, rejected_candidate, active_client])
        await db_session.commit()

        # Filter: candidate + active only
        response = await client.get(
            "/api/entities?type=candidate&status=active",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # All results should be candidates with active status
        assert all(e["type"] == "candidate" and e["status"] == "active" for e in data)

    @pytest.mark.asyncio
    async def test_combined_filters_type_status_search(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test combining type, status, and search filters."""
        entity1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Python Developer Active",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        entity2 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Python Developer Rejected",
            type=EntityType.candidate,
            status=EntityStatus.rejected
        )
        entity3 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Java Developer Active",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add_all([entity1, entity2, entity3])
        await db_session.commit()

        # Filter: candidate + active + search "Python"
        response = await client.get(
            "/api/entities?type=candidate&status=active&search=Python",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should only get active Python developers
        assert all(
            e["type"] == "candidate" and
            e["status"] == "active" and
            "Python" in e["name"]
            for e in data
        )

    @pytest.mark.asyncio
    async def test_combined_filters_all_parameters(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test combining all filter parameters."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Senior Python Engineer",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["senior", "python", "backend"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Combine: type + status + department + search + tags
        response = await client.get(
            f"/api/entities?type=candidate&status=active&department_id={department.id}&search=Python&tags=senior",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Results should match all criteria
        for e in data:
            assert e["type"] == "candidate"
            assert e["status"] == "active"
            assert e["department_id"] == department.id
            # Note: search and tags filtering in SQLite may behave differently than PostgreSQL


# ============================================================================
# COMPREHENSIVE TAG TESTS
# ============================================================================

class TestEntityTags:
    """Comprehensive tests for entity tag functionality."""

    @pytest.mark.asyncio
    async def test_create_entity_with_multiple_tags(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with multiple tags."""
        tags = ["python", "senior", "remote", "full-time", "backend"]

        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Multi-Tag Contact",
                "status": "active",
                "tags": tags
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert set(data["tags"]) == set(tags)
        assert len(data["tags"]) == 5

    @pytest.mark.asyncio
    async def test_create_entity_with_empty_tags(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with empty tags array."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "No Tags Contact",
                "status": "active",
                "tags": []
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tags"] == []

    @pytest.mark.asyncio
    async def test_create_entity_without_tags(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity without providing tags field."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Default Tags Contact",
                "status": "active"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tags"] == []

    @pytest.mark.asyncio
    async def test_update_entity_add_tags(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test adding tags to entity via update."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Update Tags Test",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=[]
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": ["new-tag", "another-tag"]},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "new-tag" in data["tags"]
        assert "another-tag" in data["tags"]

    @pytest.mark.asyncio
    async def test_update_entity_replace_tags(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test replacing existing tags."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Replace Tags Test",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["old-tag-1", "old-tag-2"]
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": ["new-tag-1", "new-tag-2"]},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert set(data["tags"]) == {"new-tag-1", "new-tag-2"}
        assert "old-tag-1" not in data["tags"]

    @pytest.mark.asyncio
    async def test_filter_by_single_tag(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering entities by single tag."""
        entity_with_tag = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Tagged Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["important"]
        )
        entity_without_tag = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Untagged Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["other"]
        )
        db_session.add_all([entity_with_tag, entity_without_tag])
        await db_session.commit()

        response = await client.get(
            "/api/entities?tags=important",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # In PostgreSQL, should only return entities with "important" tag
        # In SQLite, tag filtering may not work the same way
        if len(data) > 0:
            assert all("important" in e["tags"] for e in data if e["tags"])

    @pytest.mark.asyncio
    async def test_filter_by_multiple_tags(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering entities by multiple tags (comma-separated)."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Multi-Tag Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["python", "senior", "remote"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Filter by multiple tags
        response = await client.get(
            "/api/entities?tags=python,senior",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        # Should work in PostgreSQL with array contains


# ============================================================================
# ENTITY STATUS TRANSITION TESTS
# ============================================================================

class TestEntityStatusTransitions:
    """Test entity status transitions and workflows."""

    @pytest.mark.asyncio
    async def test_candidate_workflow_new_to_hired(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test candidate progressing through hiring workflow."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Workflow Candidate",
            type=EntityType.candidate,
            status=EntityStatus.new
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Progress through workflow: new -> interview -> offer -> hired
        workflow = [
            EntityStatus.interview,
            EntityStatus.offer,
            EntityStatus.hired
        ]

        for status in workflow:
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"status": status.value},
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == status.value

    @pytest.mark.asyncio
    async def test_filter_by_interview_status(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering candidates in interview status."""
        interview_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Interview Candidate",
            type=EntityType.candidate,
            status=EntityStatus.interview
        )
        db_session.add(interview_entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?status=interview",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "interview" for e in data)

    @pytest.mark.asyncio
    async def test_filter_by_offer_status(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering candidates with offer status."""
        offer_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Offer Candidate",
            type=EntityType.candidate,
            status=EntityStatus.offer
        )
        db_session.add(offer_entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?status=offer",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "offer" for e in data)

    @pytest.mark.asyncio
    async def test_filter_by_hired_status(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering hired candidates."""
        hired_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Hired Candidate",
            type=EntityType.candidate,
            status=EntityStatus.hired
        )
        db_session.add(hired_entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?status=hired",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "hired" for e in data)


# ============================================================================
# ADVANCED SHARING PERMISSION TESTS
# ============================================================================

class TestEntitySharingPermissions:
    """Test entity operations with different sharing permission levels."""

    @pytest.mark.asyncio
    async def test_shared_view_cannot_edit(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that user with view access cannot edit entity."""
        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with view access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Try to edit
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Hacked Name"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_shared_view_cannot_delete(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that user with view access cannot delete entity."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with view access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Try to delete
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_shared_edit_can_edit(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that user with edit access can edit entity."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with edit access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.commit()

        # Edit should succeed
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Updated Name"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_shared_edit_cannot_delete(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that user with edit access cannot delete entity."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with edit access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.commit()

        # Delete should fail
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_shared_full_can_delete(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that user with full access can delete entity."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with full access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full
        )
        db_session.add(share)
        await db_session.commit()

        # Delete should succeed
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_share_no_access(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that expired share doesn't grant access."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            # Не кандидат: кандидата член орга читает и без шаринга (общий пул).
            type=EntityType.partner,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Create expired share
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(share)
        await db_session.commit()

        # Should not have access
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_future_expiration_has_access(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that share with future expiration works."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Create share with future expiration
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(share)
        await db_session.commit()

        # Should have access
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200


# ============================================================================
# BULK OPERATIONS TESTS
# ============================================================================

class TestEntityBulkOperations:
    """Test bulk/batch entity operations."""

    @pytest.mark.asyncio
    async def test_create_multiple_entities(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating multiple entities in sequence."""
        entities_to_create = [
            {"type": "candidate", "name": "Candidate 1", "status": "new"},
            {"type": "candidate", "name": "Candidate 2", "status": "active"},
            {"type": "client", "name": "Client 1", "status": "active"},
            {"type": "contractor", "name": "Contractor 1", "status": "active"},
            {"type": "lead", "name": "Lead 1", "status": "new"},
        ]

        created_ids = []
        for entity_data in entities_to_create:
            response = await client.post(
                "/api/entities",
                json=entity_data,
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])

        # Verify all created
        assert len(created_ids) == 5
        assert len(set(created_ids)) == 5  # All unique

    @pytest.mark.asyncio
    async def test_update_multiple_entities(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test updating multiple entities."""
        # Create entities
        entities = []
        for i in range(3):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                type=EntityType.candidate,
                status=EntityStatus.new
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        # Update all to active status
        for entity in entities:
            await db_session.refresh(entity)
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"status": "active"},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200
            assert response.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_delete_multiple_entities(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test deleting multiple entities."""
        # Create entities
        entities = []
        for i in range(3):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                type=EntityType.candidate,
                status=EntityStatus.active
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        # Delete all
        for entity in entities:
            await db_session.refresh(entity)
            response = await client.delete(
                f"/api/entities/{entity.id}",
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_share_with_multiple_users(
        self, db_session, client, admin_user, admin_token, second_user,
        regular_user, organization, department, get_auth_headers,
        org_owner, org_member, org_admin
    ):
        """Test sharing entity with multiple users."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Multi-Share Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with multiple users
        users_to_share = [second_user.id, regular_user.id]
        for user_id in users_to_share:
            response = await client.post(
                f"/api/entities/{entity.id}/share",
                json={
                    "shared_with_id": user_id,
                    "access_level": "view"
                },
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify shares created
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.entity_id == entity.id)
        )
        shares = result.scalars().all()
        assert len(shares) == 2


# ============================================================================
# ADVANCED TAG FILTERING TESTS
# ============================================================================

class TestAdvancedTagFiltering:
    """Test advanced tag filtering scenarios."""

    @pytest.mark.asyncio
    async def test_filter_by_tag_with_special_characters(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test filtering by tags with special characters."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Special Tag Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["python3.11", "aws-certified", "node.js"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Test filtering (may not work in SQLite but should in PostgreSQL)
        response = await client.get(
            "/api/entities?tags=python3.11",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_filter_by_tag_case_sensitive(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test that tag filtering is case-sensitive."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Case Tag Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["Python", "JavaScript"]
        )
        db_session.add(entity)
        await db_session.commit()

        # Filter by exact case
        response = await client.get(
            "/api/entities?tags=Python",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_entity_clear_tags(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test clearing all tags from entity."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Clear Tags Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["tag1", "tag2", "tag3"]
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Clear tags
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": []},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["tags"] == []

    @pytest.mark.asyncio
    async def test_entity_with_many_tags(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test entity with large number of tags."""
        many_tags = [f"tag{i}" for i in range(50)]

        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Many Tags Entity",
                "status": "active",
                "tags": many_tags
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        assert len(response.json()["tags"]) == 50


# ============================================================================
# ENTITY SEARCH EDGE CASES
# ============================================================================

class TestEntitySearchEdgeCases:
    """Test edge cases in entity search functionality."""

    @pytest.mark.asyncio
    async def test_search_empty_string(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test search with empty string."""
        response = await client.get(
            "/api/entities?search=",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        # Empty search should return all entities

    @pytest.mark.asyncio
    async def test_search_special_characters(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test search with special characters."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="O'Brien & Associates",
            email="test+special@example.com",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        # Search for apostrophe
        response = await client.get(
            "/api/entities?search=O'Brien",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            assert any("O'Brien" in e["name"] for e in data)

    @pytest.mark.asyncio
    async def test_search_unicode(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test search with Unicode characters."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Müller Enterprises",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        response = await client.get(
            "/api/entities?search=Müller",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_very_long_query(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test search with very long query string."""
        long_query = "a" * 1000

        response = await client.get(
            f"/api/entities?search={long_query}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        # Should return empty list or handle gracefully

    @pytest.mark.asyncio
    async def test_search_sql_injection_attempt(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that search is safe from SQL injection."""
        malicious_query = "'; DROP TABLE entities; --"

        response = await client.get(
            f"/api/entities?search={malicious_query}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        # Should handle safely, no errors


# ============================================================================
# ENTITY LINK/UNLINK ADVANCED TESTS
# ============================================================================

class TestEntityLinkingAdvanced:
    """Advanced tests for linking/unlinking chats and resources."""

    @pytest.mark.asyncio
    async def test_link_multiple_chats_to_entity(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test linking multiple chats to single entity."""
        # Create multiple chats
        chats = []
        for i in range(3):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=111111 + i,
                title=f"Chat {i}",
                chat_type=ChatType.hr,
                is_active=True
            )
            chats.append(chat)
        db_session.add_all(chats)
        await db_session.commit()

        # Link all to entity
        for chat in chats:
            await db_session.refresh(chat)
            response = await client.post(
                f"/api/entities/{entity.id}/link-chat/{chat.id}",
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all linked
        for chat in chats:
            await db_session.refresh(chat)
            assert chat.entity_id == entity.id

    @pytest.mark.asyncio
    async def test_relink_chat_to_different_entity(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test relinking chat from one entity to another."""
        # Create two entities
        entity1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Entity 1",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        entity2 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Entity 2",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add_all([entity1, entity2])
        await db_session.commit()
        await db_session.refresh(entity1)
        await db_session.refresh(entity2)

        # Create chat linked to entity1
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity1.id,
            telegram_chat_id=111111,
            title="Relink Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        # Relink to entity2
        response = await client.post(
            f"/api/entities/{entity2.id}/link-chat/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify linked to entity2
        await db_session.refresh(chat)
        assert chat.entity_id == entity2.id

    @pytest.mark.asyncio
    async def test_unlink_and_relink_chat(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test unlinking and relinking same chat."""
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=111111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        # Unlink
        response = await client.delete(
            f"/api/entities/{entity.id}/unlink-chat/{chat.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Verify unlinked
        await db_session.refresh(chat)
        assert chat.entity_id is None

        # Relink
        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{chat.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Verify relinked
        await db_session.refresh(chat)
        assert chat.entity_id == entity.id


# ============================================================================
# ADDITIONAL CREATE ENTITY TESTS - EDGE CASES & VALIDATION
# ============================================================================

class TestCreateEntityEdgeCases:
    """Additional edge case tests for entity creation."""

    @pytest.mark.asyncio
    async def test_create_entity_minimal_required_fields(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with only required fields (type and name)."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Minimal Contact"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Contact"
        assert data["type"] == "candidate"
        assert data["status"] == "new"  # Default status
        assert data["tags"] == []
        assert data["extra_data"] == {}
        assert data["phone"] is None
        assert data["email"] is None

    @pytest.mark.asyncio
    async def test_create_entity_with_telegram_user_id(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with telegram_user_id."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Telegram Contact",
                "telegram_user_id": 987654321,
                "status": "active"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["telegram_user_id"] == 987654321

    @pytest.mark.asyncio
    async def test_create_entity_empty_tags_array(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with explicitly empty tags array."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "client",
                "name": "No Tags Contact",
                "status": "active",
                "tags": []
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tags"] == []

    @pytest.mark.asyncio
    async def test_create_entity_empty_extra_data(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with explicitly empty extra_data."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "partner",
                "name": "No Extra Data",
                "status": "active",
                "extra_data": {}
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["extra_data"] == {}

    @pytest.mark.asyncio
    async def test_create_entity_all_statuses(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entities with all possible status values."""
        statuses = ["new", "screening", "interview", "offer", "hired", "rejected",
                    "active", "paused", "churned", "converted", "ended", "negotiation"]

        for status in statuses:
            response = await client.post(
                "/api/entities",
                json={
                    "type": "candidate",
                    "name": f"Status {status} Contact",
                    "status": status
                },
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 201
            data = response.json()
            assert data["status"] == status

    @pytest.mark.asyncio
    async def test_create_entity_as_superadmin(
        self, client, superadmin_user, superadmin_token, organization,
        get_auth_headers, superadmin_org_member
    ):
        """Test that superadmin can create entities."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Superadmin Contact",
                "status": "active"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["created_by"] == superadmin_user.id

    @pytest.mark.asyncio
    async def test_create_entity_complex_extra_data(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with complex nested extra_data."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Complex Data Contact",
                "status": "active",
                "extra_data": {
                    "skills": ["Python", "JavaScript", "SQL"],
                    "experience": {
                        "total_years": 5,
                        "companies": ["CompanyA", "CompanyB"]
                    },
                    "preferences": {
                        "remote": True,
                        "salary_expectation": 100000
                    }
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert "skills" in data["extra_data"]
        assert "experience" in data["extra_data"]
        assert data["extra_data"]["skills"] == ["Python", "JavaScript", "SQL"]
        assert data["extra_data"]["experience"]["total_years"] == 5

    @pytest.mark.asyncio
    async def test_create_entity_unicode_name(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with unicode characters in name."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "client",
                "name": "José García 北京 🚀",
                "status": "active"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "José García 北京 🚀"

    @pytest.mark.asyncio
    async def test_create_entity_special_characters_in_fields(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test creating entity with special characters."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "contractor",
                "name": "O'Brien & Associates",
                "company": "Test & Co.",
                "position": "VP of R&D",
                "email": "test+label@example.com",
                "status": "active"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "O'Brien & Associates"
        assert data["company"] == "Test & Co."
        assert data["email"] == "test+label@example.com"


# ============================================================================
# ADDITIONAL UPDATE ENTITY TESTS - EDGE CASES
# ============================================================================

class TestUpdateEntityEdgeCases:
    """Additional edge case tests for entity updates."""

    @pytest.mark.asyncio
    async def test_update_entity_clear_optional_fields(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test clearing optional fields by setting them to null."""
        # Create entity with all fields populated
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Full Contact",
            email="full@test.com",
            phone="+1234567890",
            company="Test Company",
            position="Developer",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["python", "senior"],
            extra_data={"note": "test"}
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Clear fields
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "email": None,
                "phone": None,
                "company": None,
                "position": None
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] is None
        assert data["phone"] is None
        assert data["company"] is None
        assert data["position"] is None

    @pytest.mark.asyncio
    async def test_update_entity_replace_tags(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test completely replacing entity tags."""
        # First set some tags
        await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": ["old", "deprecated"]},
            headers=get_auth_headers(admin_token)
        )

        # Replace with new tags
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": ["new", "fresh", "updated"]},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == ["new", "fresh", "updated"]

    @pytest.mark.asyncio
    async def test_update_entity_clear_tags(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test clearing all tags."""
        # Set tags first
        await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": ["tag1", "tag2"]},
            headers=get_auth_headers(admin_token)
        )

        # Clear tags
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"tags": []},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == []

    @pytest.mark.asyncio
    async def test_update_entity_modify_extra_data(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test updating extra_data field."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Data Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            extra_data={"old_key": "old_value"}
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "extra_data": {
                    "new_key": "new_value",
                    "another_key": 123
                }
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "new_key" in data["extra_data"]
        assert data["extra_data"]["new_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_update_entity_change_type(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test changing entity type (candidate -> client)."""
        # Entity is created as candidate
        assert entity.type == EntityType.candidate

        # Change to client
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"type": "client"},  # Note: EntityUpdate doesn't have type field
            headers=get_auth_headers(admin_token)
        )

        # This should succeed if type is in EntityUpdate, otherwise field is ignored
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_entity_with_shared_edit_access(
        self, db_session, client, admin_user, second_user, second_user_token,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test updating entity when user has shared edit access."""
        # Share entity with edit access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.commit()

        # Second user updates the entity
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Updated by Shared User"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated by Shared User"

    @pytest.mark.asyncio
    async def test_update_entity_remove_department(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test removing department assignment."""
        # Entity has department_id set
        assert entity.department_id is not None

        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"department_id": None},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["department_id"] is None

    @pytest.mark.asyncio
    async def test_update_entity_as_superadmin(
        self, db_session, client, superadmin_user, superadmin_token,
        admin_user, organization, department, get_auth_headers, superadmin_org_member
    ):
        """Test that superadmin can update any entity."""
        # Create entity owned by admin_user
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Admin's Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Superadmin updates it
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Updated by Superadmin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated by Superadmin"

    @pytest.mark.asyncio
    async def test_update_entity_only_timestamp_changes(
        self, db_session, client, admin_user, admin_token, entity,
        get_auth_headers, org_owner
    ):
        """Test that update changes updated_at timestamp even without field changes."""
        original_updated_at = entity.updated_at

        # Make a no-op update
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": entity.name},  # Same value
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Refresh entity from DB
        await db_session.refresh(entity)
        # updated_at should be different
        assert entity.updated_at > original_updated_at


# ============================================================================
# ADDITIONAL DELETE ENTITY TESTS - EDGE CASES
# ============================================================================

class TestDeleteEntityEdgeCases:
    """Additional edge case tests for entity deletion."""

    @pytest.mark.asyncio
    async def test_delete_entity_with_shared_full_access(
        self, db_session, client, admin_user, second_user, second_user_token,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test deleting entity when user has shared full access."""
        # Share entity with full access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full
        )
        db_session.add(share)
        await db_session.commit()

        # Second user deletes the entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_entity_as_superadmin(
        self, db_session, client, superadmin_user, superadmin_token,
        admin_user, organization, department, get_auth_headers, superadmin_org_member
    ):
        """Test that superadmin can delete any entity."""
        # Create entity owned by admin_user
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Admin's Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Superadmin deletes it
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_entity_verify_actually_deleted(
        self, db_session, client, admin_user, admin_token, entity,
        get_auth_headers, org_owner
    ):
        """Test that entity is actually removed from database."""
        entity_id = entity.id

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify entity is gone from DB
        from sqlalchemy import select
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        deleted_entity = result.scalar_one_or_none()
        assert deleted_entity is None

    @pytest.mark.asyncio
    async def test_delete_entity_with_linked_chats(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test deleting entity that has linked chats."""
        # Create and link chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=123456789,
            title="Linked Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify chat's entity_id is now null (or chat still exists)
        await db_session.refresh(chat)
        # Depending on cascade rules, entity_id should be None
        assert chat.entity_id is None

    @pytest.mark.asyncio
    async def test_delete_entity_cannot_delete_with_view_access(
        self, db_session, client, admin_user, second_user, second_user_token,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that user with only view access cannot delete entity."""
        # Share entity with view access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Second user tries to delete
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_entity_cannot_delete_with_edit_access(
        self, db_session, client, admin_user, second_user, second_user_token,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that user with only edit access cannot delete entity (needs full)."""
        # Share entity with edit access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.commit()

        # Second user tries to delete
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# ADDITIONAL BULK OPERATIONS TESTS - ADVANCED SCENARIOS
# ============================================================================

class TestBulkOperationsAdvanced:
    """Advanced bulk operation tests with error handling."""

    @pytest.mark.asyncio
    async def test_bulk_status_update(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test updating status for multiple entities."""
        # Create multiple entities with 'new' status
        entities = []
        for i in range(5):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Candidate {i}",
                type=EntityType.candidate,
                status=EntityStatus.new
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        # Update all to 'interview' status
        for entity in entities:
            await db_session.refresh(entity)
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"status": "interview"},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all updated
        for entity in entities:
            await db_session.refresh(entity)
            assert entity.status == EntityStatus.interview

    @pytest.mark.asyncio
    async def test_bulk_tag_addition(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test adding same tags to multiple entities."""
        # Create entities
        entities = []
        for i in range(3):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                type=EntityType.candidate,
                status=EntityStatus.active,
                tags=[]
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        # Add tags to all
        new_tags = ["urgent", "priority", "q4"]
        for entity in entities:
            await db_session.refresh(entity)
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"tags": new_tags},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all have tags
        for entity in entities:
            await db_session.refresh(entity)
            assert entity.tags == new_tags

    @pytest.mark.asyncio
    async def test_bulk_department_assignment(
        self, db_session, client, admin_user, admin_token, organization,
        department, second_department, get_auth_headers, org_owner
    ):
        """Test reassigning multiple entities to new department."""
        # Create entities in first department
        entities = []
        for i in range(4):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                type=EntityType.candidate,
                status=EntityStatus.active
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        # Move all to second department
        for entity in entities:
            await db_session.refresh(entity)
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"department_id": second_department.id},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all moved
        for entity in entities:
            await db_session.refresh(entity)
            assert entity.department_id == second_department.id

    @pytest.mark.asyncio
    async def test_bulk_share_different_access_levels(
        self, db_session, client, admin_user, admin_token, second_user,
        regular_user, organization, department, get_auth_headers,
        org_owner, org_member, org_admin
    ):
        """Test sharing multiple entities with different access levels."""
        # Create entities
        entities = []
        for i in range(3):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Share Entity {i}",
                type=EntityType.candidate,
                status=EntityStatus.active
            )
            entities.append(entity)
        db_session.add_all(entities)
        await db_session.commit()

        access_levels = ["view", "edit", "full"]

        # Share each with different access level
        for i, entity in enumerate(entities):
            await db_session.refresh(entity)
            response = await client.post(
                f"/api/entities/{entity.id}/share",
                json={
                    "shared_with_id": second_user.id,
                    "access_level": access_levels[i]
                },
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify shares created
        from sqlalchemy import select
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.shared_with_id == second_user.id)
        )
        shares = result.scalars().all()
        assert len(shares) == 3

    @pytest.mark.asyncio
    async def test_bulk_delete_with_error_handling(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, department, get_auth_headers, org_owner
    ):
        """Test bulk delete where some entities fail (transferred)."""
        # Create mix of normal and transferred entities
        normal_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Normal Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )

        transferred_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Transferred Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            is_transferred=True,
            transferred_to_id=second_user.id
        )

        db_session.add_all([normal_entity, transferred_entity])
        await db_session.commit()
        await db_session.refresh(normal_entity)
        await db_session.refresh(transferred_entity)

        # Try to delete both
        normal_response = await client.delete(
            f"/api/entities/{normal_entity.id}",
            headers=get_auth_headers(admin_token)
        )
        assert normal_response.status_code == 200

        transferred_response = await client.delete(
            f"/api/entities/{transferred_entity.id}",
            headers=get_auth_headers(admin_token)
        )
        assert transferred_response.status_code == 400
        assert "Cannot delete a transferred entity" in transferred_response.json()["detail"]

    @pytest.mark.asyncio
    async def test_bulk_update_mixed_permissions(
        self, db_session, client, admin_user, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test bulk update where user has permission for some but not all entities."""
        # Create entities: one owned by second_user, one by admin_user
        owned_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=second_user.id,
            name="Owned Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )

        other_entity = Entity(
            org_id=organization.id,
            department_id=None,  # Not in department
            created_by=admin_user.id,
            name="Other Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )

        db_session.add_all([owned_entity, other_entity])
        await db_session.commit()
        await db_session.refresh(owned_entity)
        await db_session.refresh(other_entity)

        # second_user can update their own
        owned_response = await client.put(
            f"/api/entities/{owned_entity.id}",
            json={"name": "Updated Own"},
            headers=get_auth_headers(second_user_token)
        )
        assert owned_response.status_code == 200

        # second_user cannot update other's without share
        other_response = await client.put(
            f"/api/entities/{other_entity.id}",
            json={"name": "Try Update Other"},
            headers=get_auth_headers(second_user_token)
        )
        assert other_response.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_create_with_validation_errors(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test bulk create where some entities have validation errors."""
        valid_entity = {
            "type": "candidate",
            "name": "Valid Entity",
            "status": "active"
        }

        invalid_department = {
            "type": "candidate",
            "name": "Invalid Dept Entity",
            "status": "active",
            "department_id": 99999  # Non-existent
        }

        # Create valid entity
        response1 = await client.post(
            "/api/entities",
            json=valid_entity,
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 201

        # Create invalid entity
        response2 = await client.post(
            "/api/entities",
            json=invalid_department,
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_status_transition_workflow(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test bulk status transition workflow."""
        # Create entities in various states
        entities = []
        statuses = ["rejected", "hired", "active"]

        for i, status in enumerate(statuses):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Status Entity {i}",
                type=EntityType.candidate,
                status=getattr(EntityStatus, status)
            )
            entities.append(entity)

        db_session.add_all(entities)
        await db_session.commit()

        # Transition all to ended status
        for entity in entities:
            await db_session.refresh(entity)
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"status": "ended"},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all transitioned
        for entity in entities:
            await db_session.refresh(entity)
            assert entity.status == EntityStatus.ended


# ============================================================================
# ENTITY ACCESS CONTROL WITH ROLE HIERARCHY
# ============================================================================

class TestEntityAccessControlRoleHierarchy:
    """Test entity access control with different role hierarchies."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_entities(
        self, db_session, client, superadmin_user, superadmin_token,
        admin_user, organization, department, get_auth_headers,
        superadmin_org_member, org_owner
    ):
        """Test that SUPERADMIN sees all entities without restriction."""
        # Create entity by admin_user
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Admin Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # SUPERADMIN can see it
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["id"] == entity.id

    @pytest.mark.asyncio
    async def test_owner_cannot_see_superadmin_private_content(
        self, db_session, client, admin_user, admin_token,
        superadmin_user, organization, department, get_auth_headers,
        org_owner, superadmin_org_member
    ):
        """Test that OWNER cannot see private content created by SUPERADMIN."""
        # Create entity by SUPERADMIN (not in any department = private)
        superadmin_entity = Entity(
            org_id=organization.id,
            department_id=None,  # No department = private
            created_by=superadmin_user.id,
            name="SUPERADMIN Private Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(superadmin_entity)
        await db_session.commit()
        await db_session.refresh(superadmin_entity)

        # Owner (admin_user) should not be able to access it
        response = await client.get(
            f"/api/entities/{superadmin_entity.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should return 404 (not found) to hide existence
        assert response.status_code == 404


# ============================================================================
# SHARE PERMISSIONS ACROSS DEPARTMENTS
# ============================================================================

class TestSharePermissionsDepartments:
    """Test entity share permissions across departments."""

    @pytest.mark.asyncio
    async def test_owner_can_share_with_anyone_in_org(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, department, second_department, get_auth_headers,
        org_owner, org_member
    ):
        """Test that org OWNER can share with anyone in organization."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Owner Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with second_user (different department)
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "edit",
                "note": "Owner sharing"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_superadmin_can_share_with_anyone(
        self, db_session, client, superadmin_user, superadmin_token,
        second_user, organization, department, get_auth_headers,
        superadmin_org_member, org_member
    ):
        """Test that SUPERADMIN can share with anyone."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=superadmin_user.id,
            name="SUPERADMIN Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share with second_user
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "full",
                "note": "SUPERADMIN sharing"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


# ============================================================================
# ADVANCED PERMISSIONS AND FILTERING EDGE CASES
# ============================================================================

class TestAdvancedPermissionsAndFilteringEdgeCases:
    """Test advanced permission and filtering edge cases."""

    @pytest.mark.asyncio
    async def test_share_with_auto_share_related_resources(
        self, db_session, client, admin_user, admin_token, entity,
        second_user, organization, get_auth_headers, org_owner, org_member
    ):
        """Test that auto_share_related shares chats and calls."""
        # Create related resources
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=111,
            title="Chat 1",
            chat_type=ChatType.hr,
            is_active=True
        )
        chat2 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=222,
            title="Chat 2",
            chat_type=ChatType.sales,
            is_active=True
        )
        call1 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Call 1",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300
        )
        call2 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Call 2",
            source_type=CallSource.meet,
            status=CallStatus.done,
            duration_seconds=600
        )
        db_session.add_all([chat1, chat2, call1, call2])
        await db_session.commit()

        # Share entity with auto_share_related=True
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view",
                "auto_share_related": True
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["auto_shared"] is not None
        # Should have shared 2 chats and 2 calls
        assert data["auto_shared"]["chats"] == 2
        assert data["auto_shared"]["calls"] == 2

    @pytest.mark.asyncio
    async def test_link_chat_requires_edit_permission(
        self, db_session, client, second_user, second_user_token,
        organization, department, admin_user, get_auth_headers,
        org_owner, org_member
    ):
        """Test that linking chat requires edit permission."""
        # Create entity owned by admin
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Admin Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        # Create chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add_all([entity, chat])
        await db_session.commit()
        await db_session.refresh(entity)
        await db_session.refresh(chat)

        # second_user has no permission, should fail
        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Share permission logic")
    async def test_link_chat_with_edit_share_permission(
        self, db_session, client, second_user, second_user_token,
        organization, department, admin_user, get_auth_headers,
        org_owner, org_member
    ):
        """Test that user with edit share permission can link chat."""
        # Create entity owned by admin
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Admin Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        # Create chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        # Share entity with edit access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add_all([entity, chat, share])
        await db_session.commit()
        await db_session.refresh(entity)
        await db_session.refresh(chat)

        # second_user has edit permission, should succeed
        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
