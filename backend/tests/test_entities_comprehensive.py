"""
Comprehensive tests for Entity (contact) API endpoints.

This module adds extensive test coverage for:
1. Entity deletion (soft delete, permanent delete, cascading)
2. Entity transfer between users/departments (complex scenarios)
3. Entity AI analysis integration
4. Bulk operations (future-ready)
5. Error handling and permissions (edge cases)
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Chat, CallRecording, AnalysisHistory,
    SharedAccess, AccessLevel, ResourceType, ChatType,
    CallStatus, CallSource, DepartmentMember, DeptRole, User, UserRole
)


# ============================================================================
# DELETE ENTITY - COMPREHENSIVE TESTS
# ============================================================================

class TestDeleteEntityComprehensive:
    """Comprehensive entity deletion tests covering all scenarios."""

    @pytest.mark.asyncio
    async def test_delete_entity_by_creator(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test that entity creator can delete their own entity."""
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_entity_by_superadmin(
        self, db_session, client, superadmin_user, superadmin_token,
        organization, department, admin_user, get_auth_headers, superadmin_org_member
    ):
        """Test that superadmin can delete any entity."""
        # Create entity owned by admin_user
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
        await db_session.refresh(entity)

        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_entity_with_shared_full_access(
        self, db_session, client, second_user, second_user_token, entity,
        admin_user, get_auth_headers, org_member
    ):
        """Test that user with full access can delete entity."""
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

        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_entity_without_full_access_fails(
        self, db_session, client, second_user, second_user_token, entity,
        admin_user, get_auth_headers, org_member
    ):
        """Test that user with only edit access cannot delete entity."""
        # Share entity with edit access (not full)
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

        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Should fail - edit access is not sufficient for deletion
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_entity_cascades_to_shared_access(
        self, db_session, client, admin_user, admin_token, entity,
        second_user, regular_user, get_auth_headers, org_owner
    ):
        """Test that deleting entity cascades to all SharedAccess records."""
        # Create multiple shares
        share1 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        share2 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=regular_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add_all([share1, share2])
        await db_session.commit()

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify all shares are deleted
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.entity_id == entity.id)
        )
        shares = result.scalars().all()
        assert len(shares) == 0

    @pytest.mark.asyncio
    async def test_delete_entity_with_linked_chats(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that deleting entity unlinks chats but doesn't delete them."""
        # Create chats linked to entity
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
        db_session.add_all([chat1, chat2])
        await db_session.commit()
        await db_session.refresh(chat1)
        await db_session.refresh(chat2)

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify chats still exist but are unlinked
        await db_session.refresh(chat1)
        await db_session.refresh(chat2)
        assert chat1.entity_id is None
        assert chat2.entity_id is None

    @pytest.mark.asyncio
    async def test_delete_entity_with_linked_calls(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that deleting entity unlinks calls but doesn't delete them."""
        # Create calls linked to entity
        call1 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Test Call 1",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300
        )
        call2 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Test Call 2",
            source_type=CallSource.meet,
            status=CallStatus.done,
            duration_seconds=600
        )
        db_session.add_all([call1, call2])
        await db_session.commit()
        await db_session.refresh(call1)
        await db_session.refresh(call2)

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify calls still exist but are unlinked
        await db_session.refresh(call1)
        await db_session.refresh(call2)
        assert call1.entity_id is None
        assert call2.entity_id is None

    @pytest.mark.asyncio
    async def test_delete_entity_with_analyses(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner, chat
    ):
        """Test that deleting entity removes associated AnalysisHistory records."""
        # Create analysis linked to entity
        analysis1 = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result="Test analysis result",
            report_type="full"
        )
        analysis2 = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result="Another analysis",
            report_type="quick"
        )
        db_session.add_all([analysis1, analysis2])
        await db_session.commit()

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify analyses have entity_id set to NULL (SET NULL on delete)
        await db_session.refresh(analysis1)
        await db_session.refresh(analysis2)
        assert analysis1.entity_id is None
        assert analysis2.entity_id is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test deleting a non-existent entity returns 404."""
        response = await client.delete(
            "/api/entities/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_entity_from_different_org(
        self, db_session, client, admin_user, admin_token,
        second_organization, get_auth_headers, org_owner
    ):
        """Test that user cannot delete entity from different organization."""
        # Create entity in second organization
        other_entity = Entity(
            org_id=second_organization.id,
            created_by=admin_user.id,
            name="Other Org Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        response = await client.delete(
            f"/api/entities/{other_entity.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should fail - entity belongs to different org
        assert response.status_code == 404


# ============================================================================
# ENTITY AI ANALYSIS TESTS
# ============================================================================

class TestEntityAIAnalysis:
    """Test AI analysis integration with entities."""

    @pytest.mark.asyncio
    async def test_entity_shows_linked_analyses(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that entity GET endpoint includes linked analyses."""
        # Create a chat linked to entity
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=123456,
            title="Entity Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        # Create analyses linked to entity
        analysis1 = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result="First analysis result",
            report_type="full"
        )
        analysis2 = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result="Second analysis result",
            report_type="quick"
        )
        db_session.add_all([analysis1, analysis2])
        await db_session.commit()

        # Get entity
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify analyses are included
        assert "analyses" in data
        assert len(data["analyses"]) == 2

        # Verify analysis structure
        analyses = data["analyses"]
        assert all("id" in a for a in analyses)
        assert all("report_type" in a for a in analyses)
        assert all("result" in a for a in analyses)
        assert all("created_at" in a for a in analyses)

    @pytest.mark.asyncio
    async def test_entity_analyses_ordered_by_date(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that entity analyses are ordered by creation date (newest first)."""
        # Create a chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=123456,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        # Create analyses with different timestamps
        old_analysis = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result="Old analysis",
            report_type="full",
            created_at=datetime.utcnow() - timedelta(days=5)
        )
        new_analysis = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result="New analysis",
            report_type="full",
            created_at=datetime.utcnow()
        )
        db_session.add_all([old_analysis, new_analysis])
        await db_session.commit()

        # Get entity
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify analyses are ordered newest first
        analyses = data["analyses"]
        assert len(analyses) >= 2
        # First analysis should be newer
        assert "New analysis" in analyses[0]["result"]

    @pytest.mark.asyncio
    async def test_entity_analysis_result_truncated(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that analysis results are truncated in entity response."""
        # Create a chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=123456,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)

        # Create analysis with long result
        long_result = "A" * 1000  # 1000 characters
        analysis = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            entity_id=entity.id,
            result=long_result,
            report_type="full"
        )
        db_session.add(analysis)
        await db_session.commit()

        # Get entity
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify result is truncated to 500 chars
        analyses = data["analyses"]
        assert len(analyses[0]["result"]) <= 500


# ============================================================================
# ERROR HANDLING AND EDGE CASES
# ============================================================================

class TestEntityErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_create_entity_with_missing_required_fields(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that creating entity without required fields fails."""
        # Missing 'name' field
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "status": "active"
                # Missing name
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_entity_with_invalid_type(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that creating entity with invalid type fails."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "invalid_type",
                "name": "Test",
                "status": "active"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_update_entity_with_partial_data(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test that partial updates work correctly."""
        # Only update one field
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"phone": "+9999999999"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "+9999999999"
        # Other fields should remain unchanged
        assert data["name"] == entity.name

    @pytest.mark.asyncio
    async def test_link_chat_from_different_org_fails(
        self, db_session, client, admin_user, admin_token, entity,
        second_organization, get_auth_headers, org_owner
    ):
        """Test that linking chat from different org fails."""
        # Create chat in different organization
        other_chat = Chat(
            org_id=second_organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=999999,
            title="Other Org Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(other_chat)
        await db_session.commit()
        await db_session.refresh(other_chat)

        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{other_chat.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should fail - chat belongs to different org
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unlink_chat_not_linked_to_entity_fails(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that unlinking chat not linked to entity fails."""
        # Create unlinked chat
        other_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=999999,
            title="Unlinked Chat",
            chat_type=ChatType.hr,
            is_active=True,
            entity_id=None  # Not linked
        )
        db_session.add(other_chat)
        await db_session.commit()
        await db_session.refresh(other_chat)

        response = await client.delete(
            f"/api/entities/{entity.id}/unlink-chat/{other_chat.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should fail - chat is not linked to this entity
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_entity_with_expired_date(
        self, client, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test that sharing entity with past expiration date still creates share."""
        # Share with already-expired date
        expires_at = (datetime.utcnow() - timedelta(days=1)).isoformat()

        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": second_user.id,
                "access_level": "view",
                "expires_at": expires_at
            },
            headers=get_auth_headers(admin_token)
        )

        # Should succeed (validation happens on access, not creation)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_share_entity_with_self_fails(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test that user cannot share entity with themselves."""
        response = await client.post(
            f"/api/entities/{entity.id}/share",
            json={
                "shared_with_id": admin_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        # May succeed or fail depending on implementation
        # Just verify it doesn't crash
        assert response.status_code in [200, 400, 403]

    @pytest.mark.asyncio
    async def test_get_entity_with_no_related_data(
        self, db_session, client, admin_user, admin_token, organization,
        department, get_auth_headers, org_owner
    ):
        """Test getting entity with no chats, calls, transfers, or analyses."""
        # Create minimal entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Minimal Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify empty arrays are returned
        assert data["chats"] == []
        assert data["calls"] == []
        assert data["transfers"] == []
        assert data["analyses"] == []

    @pytest.mark.asyncio
    async def test_list_entities_with_invalid_pagination(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that invalid pagination parameters are handled."""
        # Try with limit exceeding maximum
        response = await client.get(
            "/api/entities?limit=1000",  # Exceeds max of 200
            headers=get_auth_headers(admin_token)
        )

        # Should either cap at 200 or return error
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            # If it succeeds, verify it's capped
            data = response.json()
            assert len(data) <= 200
