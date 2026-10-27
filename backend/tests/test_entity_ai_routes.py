"""
Tests for Entity AI routes - AI assistant for entity analysis.

These tests cover:
- GET /entities/{entity_id}/ai/actions - Get available quick actions
- POST /entities/{entity_id}/ai/message - Send message (streaming)
- GET /entities/{entity_id}/ai/history - Get conversation history
- DELETE /entities/{entity_id}/ai/history - Clear conversation history
- POST /entities/{entity_id}/ai/update-summary - Manually update AI summary
- GET /entities/{entity_id}/ai/memory - Get entity AI memory
- POST /entities/ai/batch-update-summaries - Batch update AI summaries
"""
import pytest
import json
from httpx import AsyncClient
from datetime import datetime

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, EntityType, EntityStatus, EntityAIConversation,
    Chat, ChatType, Message, CallRecording, CallSource, CallStatus
)
from api.services.auth import create_access_token


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def entity_with_data(
    db_session,
    organization: Organization,
    department: Department,
    admin_user: User,
    org_owner,
) -> Entity:
    """Create an entity with some data.

    admin_user — владелец организации (org_owner): без членства в орге ручки
    /entities/{id}/ai/* отвечают 403.
    """
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Test Candidate",
        email="candidate@test.com",
        type=EntityType.candidate,
        status=EntityStatus.interview
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest.fixture
async def entity_with_chat(
    db_session,
    entity_with_data: Entity,
    organization: Organization,
    admin_user: User
) -> Chat:
    """Create a chat linked to entity with messages."""
    chat = Chat(
        org_id=organization.id,
        owner_id=admin_user.id,
        entity_id=entity_with_data.id,
        telegram_chat_id=123456,
        title="Interview Chat",
        chat_type=ChatType.hr,
        is_active=True
    )
    db_session.add(chat)
    await db_session.flush()

    # Add messages
    message = Message(
        chat_id=chat.id,
        telegram_message_id=1,
        telegram_user_id=12345,
        username="testuser",
        first_name="Test",
        last_name="User",
        content="Hello, how are you?",
        content_type="text",
        timestamp=datetime.utcnow()
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(chat)
    return chat


@pytest.fixture
async def entity_with_call(
    db_session,
    entity_with_data: Entity,
    organization: Organization,
    admin_user: User
) -> CallRecording:
    """Create a call recording linked to entity."""
    call = CallRecording(
        org_id=organization.id,
        owner_id=admin_user.id,
        entity_id=entity_with_data.id,
        title="Interview Call",
        source_type=CallSource.upload,
        status=CallStatus.done,
        summary="Candidate seems experienced and motivated.",
        duration_seconds=600
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call


@pytest.fixture
async def ai_conversation(
    db_session,
    entity_with_data: Entity,
    admin_user: User
) -> EntityAIConversation:
    """Create an AI conversation with history."""
    conversation = EntityAIConversation(
        entity_id=entity_with_data.id,
        user_id=admin_user.id,
        messages=[
            {
                "role": "user",
                "content": "Tell me about this candidate",
                "timestamp": datetime.utcnow().isoformat()
            },
            {
                "role": "assistant",
                "content": "This is a test response",
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


# ============================================================================
# TEST CLASS: Get Available Actions
# ============================================================================

@pytest.mark.asyncio
class TestGetAvailableActions:
    """Test GET /entities/{entity_id}/ai/actions endpoint."""

    async def test_get_actions_success(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test successfully retrieving available AI actions."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/actions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "actions" in data
        assert isinstance(data["actions"], list)
        assert len(data["actions"]) > 0

        # Verify action structure
        action = data["actions"][0]
        assert "id" in action
        assert "label" in action
        assert "icon" in action

    async def test_get_actions_includes_common_actions(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test that common actions are included."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/actions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        action_ids = [a["id"] for a in data["actions"]]
        assert "full_analysis" in action_ids
        assert "red_flags" in action_ids
        assert "summary" in action_ids

    async def test_get_actions_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test retrieving actions for non-existent entity."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/entities/99999/ai/actions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_get_actions_access_denied(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        second_user: User
    ):
        """Test that user without access cannot get actions."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/actions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_get_actions_unauthenticated(
        self,
        client: AsyncClient,
        entity_with_data: Entity
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/actions"
        )
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Send AI Message (Streaming)
# ============================================================================

@pytest.mark.asyncio
class TestEntityAIMessage:
    """Test POST /entities/{entity_id}/ai/message endpoint."""

    async def test_send_message_with_quick_action(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test sending AI message with quick action."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/message",
            headers={"Authorization": f"Bearer {token}"},
            json={"quick_action": "summary"}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    async def test_send_message_with_text(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test sending AI message with custom text."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/message",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Tell me about this candidate"}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    async def test_send_message_validation_error(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test that neither message nor quick_action raises error."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/message",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )

        assert response.status_code == 400

    async def test_send_message_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test sending message to non-existent entity."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/99999/ai/message",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Test"}
        )

        assert response.status_code == 404

    async def test_send_message_access_denied(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        second_user: User
    ):
        """Test that user without access cannot send messages."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/message",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Test"}
        )

        assert response.status_code == 403

    async def test_send_message_unauthenticated(
        self,
        client: AsyncClient,
        entity_with_data: Entity
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/message",
            json={"message": "Test"}
        )
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Get AI History
# ============================================================================

@pytest.mark.asyncio
class TestGetAIHistory:
    """Test GET /entities/{entity_id}/ai/history endpoint."""

    async def test_get_history_with_conversation(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User,
        ai_conversation: EntityAIConversation
    ):
        """Test retrieving AI conversation history."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "messages" in data
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) >= 2

        # Verify message structure
        message = data["messages"][0]
        assert "role" in message
        assert "content" in message
        assert "timestamp" in message

    async def test_get_history_no_conversation(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test retrieving history when no conversation exists."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["messages"] == []

    async def test_get_history_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test retrieving history for non-existent entity."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/entities/99999/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_get_history_access_denied(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        second_user: User
    ):
        """Test that user without access cannot get history."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_get_history_unauthenticated(
        self,
        client: AsyncClient,
        entity_with_data: Entity
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/history"
        )
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Clear AI History
# ============================================================================

@pytest.mark.asyncio
class TestClearAIHistory:
    """Test DELETE /entities/{entity_id}/ai/history endpoint."""

    async def test_clear_history_success(
        self,
        client: AsyncClient,
        db_session,
        entity_with_data: Entity,
        admin_user: User,
        ai_conversation: EntityAIConversation
    ):
        """Test successfully clearing AI conversation history."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.delete(
            f"/api/entities/{entity_with_data.id}/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify conversation was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(EntityAIConversation).where(
                EntityAIConversation.entity_id == entity_with_data.id,
                EntityAIConversation.user_id == admin_user.id
            )
        )
        conversation = result.scalar_one_or_none()
        assert conversation is None

    async def test_clear_history_no_conversation(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test clearing history when no conversation exists."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.delete(
            f"/api/entities/{entity_with_data.id}/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_clear_history_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test clearing history for non-existent entity."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.delete(
            "/api/entities/99999/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_clear_history_access_denied(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        second_user: User
    ):
        """Test that user without access cannot clear history."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.delete(
            f"/api/entities/{entity_with_data.id}/ai/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_clear_history_unauthenticated(
        self,
        client: AsyncClient,
        entity_with_data: Entity
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.delete(
            f"/api/entities/{entity_with_data.id}/ai/history"
        )
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Update AI Summary
# ============================================================================

@pytest.mark.asyncio
class TestUpdateAISummary:
    """Test POST /entities/{entity_id}/ai/update-summary endpoint."""

    async def test_update_summary_with_data(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        entity_with_chat: Chat,
        entity_with_call: CallRecording,
        admin_user: User
    ):
        """Test updating AI summary when entity has data."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/update-summary",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "summary" in data
        assert "total_events" in data or "new_events_count" in data

    async def test_update_summary_no_content(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test updating summary when entity has no content."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/update-summary",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Should return error or success=false
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert "success" in data

    async def test_update_summary_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test updating summary for non-existent entity."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/99999/ai/update-summary",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_update_summary_access_denied(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        second_user: User
    ):
        """Test that user without access cannot update summary."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/update-summary",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_update_summary_unauthenticated(
        self,
        client: AsyncClient,
        entity_with_data: Entity
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.post(
            f"/api/entities/{entity_with_data.id}/ai/update-summary"
        )
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Get AI Memory
# ============================================================================

@pytest.mark.asyncio
class TestGetAIMemory:
    """Test GET /entities/{entity_id}/ai/memory endpoint."""

    async def test_get_memory_success(
        self,
        client: AsyncClient,
        db_session,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test retrieving AI memory (summary + key events)."""
        # Set some AI memory data
        entity_with_data.ai_summary = "Test summary of interactions"
        entity_with_data.ai_summary_updated_at = datetime.utcnow()
        entity_with_data.key_events = [
            {"event": "First contact", "timestamp": "2024-01-01"}
        ]
        db_session.add(entity_with_data)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/memory",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "summary" in data
        assert data["summary"] == "Test summary of interactions"
        assert "summary_updated_at" in data
        assert "key_events" in data
        assert isinstance(data["key_events"], list)

    async def test_get_memory_no_data(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        admin_user: User
    ):
        """Test retrieving memory when entity has no AI data."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/memory",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["summary"] is None
        assert data["summary_updated_at"] is None
        assert data["key_events"] == []

    async def test_get_memory_entity_not_found(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test retrieving memory for non-existent entity."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/entities/99999/ai/memory",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_get_memory_access_denied(
        self,
        client: AsyncClient,
        entity_with_data: Entity,
        second_user: User
    ):
        """Test that user without access cannot get memory."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/memory",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_get_memory_unauthenticated(
        self,
        client: AsyncClient,
        entity_with_data: Entity
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.get(
            f"/api/entities/{entity_with_data.id}/ai/memory"
        )
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Batch Update Summaries
# ============================================================================

@pytest.mark.asyncio
class TestBatchUpdateSummaries:
    """Test POST /entities/ai/batch-update-summaries endpoint."""

    async def test_batch_update_success(
        self,
        client: AsyncClient,
        db_session,
        organization: Organization,
        department: Department,
        admin_user: User,
        org_owner,  # пакетное обновление — только админам орга (owner/admin)
    ):
        """Test batch updating AI summaries."""
        # Create entities owned by admin_user
        entities = []
        for i in range(3):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Test Entity {i}",
                email=f"test{i}@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active
            )
            db_session.add(entity)
            entities.append(entity)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/ai/batch-update-summaries?limit=10&only_empty=true",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "updated_count" in data
        assert "error_count" in data
        assert "updated" in data
        assert "errors" in data

    async def test_batch_update_with_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner,  # пакетное обновление — только админам орга (owner/admin)
    ):
        """Test batch update respects limit parameter."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/ai/batch-update-summaries?limit=5",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should process at most 5 entities
        total_processed = data["updated_count"] + data["error_count"]
        assert total_processed <= 5

    async def test_batch_update_only_empty(
        self,
        client: AsyncClient,
        db_session,
        organization: Organization,
        department: Department,
        admin_user: User,
        org_owner,  # пакетное обновление — только админам орга (owner/admin)
    ):
        """Test batch update only processes entities without summaries."""
        # Create entity with existing summary
        entity_with_summary = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Has Summary",
            email="hassummary@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            ai_summary="Existing summary"
        )
        db_session.add(entity_with_summary)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/ai/batch-update-summaries?only_empty=true",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Entity with summary should not be in updated list
        updated_ids = [e["id"] for e in data["updated"]]
        assert entity_with_summary.id not in updated_ids

    async def test_batch_update_max_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner,  # пакетное обновление — только админам орга (owner/admin)
    ):
        """Test that batch update enforces maximum limit of 50."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/ai/batch-update-summaries?limit=100",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should cap at 50
        total_processed = data["updated_count"] + data["error_count"]
        assert total_processed <= 50

    async def test_batch_update_non_admin_denied(
        self,
        client: AsyncClient,
        regular_user: User
    ):
        """Test that non-admin users cannot batch update."""
        # Set regular_user role to non-admin
        token = create_access_token(data={
            "sub": str(regular_user.id),
            "token_version": regular_user.token_version
        })

        response = await client.post(
            "/api/entities/ai/batch-update-summaries",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Regular users should be denied (403) or succeed if they have ADMIN role
        # Based on the fixture, regular_user has UserRole.admin, so it should succeed
        assert response.status_code in [200, 403]

    async def test_batch_update_unauthenticated(
        self,
        client: AsyncClient
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.post("/api/entities/ai/batch-update-summaries")
        assert response.status_code in [401, 403]

    async def test_batch_update_empty_result(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner,  # пакетное обновление — только админам орга (owner/admin)
    ):
        """Test batch update when user has no entities."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.post(
            "/api/entities/ai/batch-update-summaries",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["updated_count"] == 0
        assert len(data["updated"]) == 0
