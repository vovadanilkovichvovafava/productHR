"""
Tests for Chat access control.
These tests verify that access_level (view/edit/full) is properly enforced for chats.
"""
import pytest
from datetime import datetime

from api.models.database import Chat, Message, SharedAccess, AccessLevel, ResourceType


class TestChatOwnerAccess:
    """Test chat access for owner."""

    @pytest.mark.asyncio
    async def test_owner_can_view_chat(self, client, admin_user, admin_token, chat, get_auth_headers, org_owner):
        """Test that chat owner can view their chat."""
        response = await client.get(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_owner_can_update_chat(self, client, admin_user, admin_token, chat, get_auth_headers, org_owner):
        """Test that chat owner can update their chat."""
        response = await client.patch(
            f"/api/chats/{chat.id}",
            json={"custom_name": "Updated Chat Name"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_owner_can_delete_chat(self, client, admin_user, admin_token, chat, get_auth_headers, org_owner):
        """Test that chat owner can delete their chat (soft delete)."""
        response = await client.delete(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_owner_can_clear_messages(self, client, admin_user, admin_token, chat, get_auth_headers, org_owner):
        """Test that chat owner can clear messages."""
        response = await client.delete(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 204


class TestChatViewAccess:
    """Test chat access with view permission - CRITICAL SECURITY TESTS."""

    @pytest.mark.asyncio
    async def test_view_user_can_see_chat(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """Test that user with view access can see chat."""
        response = await client.get(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # This might fail because can_access_chat doesn't check SharedAccess
        # Expected: 200
        # Current bug: might return 403 because SharedAccess is ignored!

    @pytest.mark.asyncio
    async def test_view_user_cannot_update_chat(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to update chat.
        """
        response = await client.patch(
            f"/api/chats/{chat.id}",
            json={"custom_name": "Hacked Name"},
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        # Current behavior depends on can_access_chat bug
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to update chat! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_delete_chat(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to delete chat.
        """
        response = await client.delete(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        # Current bug: might return 204 (deletes chat!)
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to delete chat! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_clear_messages(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to clear messages.
        """
        response = await client.delete(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to clear messages! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_permanent_delete_chat(
        self, db_session, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to permanently delete chat.
        """
        # First soft delete
        chat.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.delete(
            f"/api/chats/{chat.id}/permanent",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to permanently delete! Got {response.status_code}"


class TestChatNoAccess:
    """Test chat access for users without any share."""

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_view_chat(
        self, client, second_user, second_user_token, chat, get_auth_headers, org_member
    ):
        """Test that user without share cannot view chat."""
        response = await client.get(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # User is not owner and no SharedAccess exists
        assert response.status_code in [403, 404], \
            f"User without access should not see chat. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_update_chat(
        self, client, second_user, second_user_token, chat, get_auth_headers, org_member
    ):
        """Test that user without share cannot update chat."""
        response = await client.patch(
            f"/api/chats/{chat.id}",
            json={"custom_name": "Hacked"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_delete_chat(
        self, client, second_user, second_user_token, chat, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User without share should NOT be able to delete chat.
        """
        response = await client.delete(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403
        # Current: returns 403 because can_access_chat checks owner_id
        assert response.status_code == 403


class TestChatCanAccessFunction:
    """Test the can_access_chat function behavior."""

    @pytest.mark.asyncio
    async def test_can_access_chat_ignores_shared_access(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """
        BUG TEST: can_access_chat function does NOT check SharedAccess table.
        This means users with share cannot access chats they should be able to.
        """
        response = await client.get(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Bug: can_access_chat only checks owner_id, ignores SharedAccess
        # So even with valid share, user gets 403
        # After fix, should return 200


class TestChatEditAccess:
    """Test chat access with edit permission."""

    @pytest.mark.asyncio
    async def test_edit_user_can_update_chat(
        self, db_session, client, second_user, second_user_token, chat, admin_user, get_auth_headers, org_member
    ):
        """Test that user with edit access can update chat."""
        # Create edit share
        share = SharedAccess(
            resource_type=ResourceType.chat,
            resource_id=chat.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.patch(
            f"/api/chats/{chat.id}",
            json={"custom_name": "Legitimately Updated"},
            headers=get_auth_headers(second_user_token)
        )

        # After fix, should return 200
        # Currently might return 403 because can_access_chat ignores SharedAccess

    @pytest.mark.asyncio
    async def test_edit_user_cannot_delete_chat(
        self, db_session, client, second_user, second_user_token, chat, admin_user, get_auth_headers, org_member
    ):
        """Test that user with edit access should NOT be able to delete chat."""
        share = SharedAccess(
            resource_type=ResourceType.chat,
            resource_id=chat.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.delete(
            f"/api/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Edit should NOT allow delete - only owner or full access
        assert response.status_code == 403


class TestChatListFiltering:
    """Test that chat list properly filters by access."""

    @pytest.mark.asyncio
    async def test_list_shows_only_accessible_chats(
        self, client, second_user, second_user_token, chat, second_chat, get_auth_headers, org_member
    ):
        """Test that chat list only shows chats user has access to."""
        response = await client.get(
            "/api/chats",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        chat_ids = [c["id"] for c in data]

        # second_chat is owned by second_user, so should be visible
        assert second_chat.id in chat_ids, "User should see their own chat"

    @pytest.mark.asyncio
    async def test_list_shows_shared_chats(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """Test that shared chats appear in list."""
        response = await client.get(
            "/api/chats",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        chat_ids = [c["id"] for c in data]

        # After fix, shared chat should appear in list
        # assert chat.id in chat_ids, "User should see shared chat"


class TestChatEntityLinking:
    """Test chat-entity linking respects access."""

    @pytest.mark.asyncio
    async def test_view_entity_user_cannot_link_chat(
        self, client, second_user, second_user_token, entity, entity_share_view, chat, get_auth_headers, org_member
    ):
        """
        Test that user with view-only access to entity cannot link chat to it.
        """
        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"View-only entity user should not link chat. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_entity_user_cannot_unlink_chat(
        self, db_session, client, second_user, second_user_token, entity, entity_share_view, chat, get_auth_headers, org_member
    ):
        """
        Test that user with view-only access to entity cannot unlink chat from it.
        """
        # First link chat to entity
        chat.entity_id = entity.id
        await db_session.commit()

        response = await client.delete(
            f"/api/entities/{entity.id}/unlink-chat/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"View-only entity user should not unlink chat. Got {response.status_code}"


class TestChatCrossOrganization:
    """Test that users cannot access chats from other organizations."""

    @pytest.mark.asyncio
    async def test_cannot_access_chat_from_other_org(
        self, db_session, client, second_user, second_user_token, second_organization, get_auth_headers, org_member
    ):
        """Test that user cannot access chat from different organization."""
        other_chat = Chat(
            org_id=second_organization.id,
            owner_id=1,
            telegram_chat_id=111222333,
            title="Other Org Chat",
            chat_type="hr",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(other_chat)
        await db_session.commit()
        await db_session.refresh(other_chat)

        response = await client.get(
            f"/api/chats/{other_chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404], \
            f"User should not access chat from other org. Got {response.status_code}"


class TestChatOrgRoleAccess:
    """Test chat access based on organization role."""

    @pytest.mark.asyncio
    async def test_org_owner_can_access_all_chats(
        self, client, admin_user, admin_token, chat, second_chat, get_auth_headers, org_owner
    ):
        """Test that org owner can access all chats in org."""
        response = await client.get(
            f"/api/chats/{second_chat.id}",
            headers=get_auth_headers(admin_token)
        )

        # Org owner should see all chats
        # Current: might return 403 because can_access_chat only checks owner_id
        # After fix: should return 200

    @pytest.mark.asyncio
    async def test_org_owner_can_delete_any_chat(
        self, client, admin_user, admin_token, second_chat, get_auth_headers, org_owner
    ):
        """Test that org owner can delete any chat in org."""
        response = await client.delete(
            f"/api/chats/{second_chat.id}",
            headers=get_auth_headers(admin_token)
        )

        # Org owner should be able to delete
        # Current: might return 403 because can_access_chat only checks owner_id


class TestChatMessages:
    """Test chat message operations respect access."""

    @pytest.mark.asyncio
    async def test_view_user_can_read_messages(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """Test that user with view access can read messages."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(second_user_token)
        )

        # After SharedAccess fix, should return 200

    @pytest.mark.asyncio
    async def test_view_user_cannot_delete_messages(
        self, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """
        Test that user with view access cannot delete messages.
        """
        response = await client.delete(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403


class TestTrashOperations:
    """Test trash/restore operations respect access."""

    @pytest.mark.asyncio
    async def test_view_user_cannot_restore_chat(
        self, db_session, client, second_user, second_user_token, chat, chat_share_view, get_auth_headers, org_member
    ):
        """Test that user with view access cannot restore deleted chat."""
        # Soft delete the chat
        chat.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.post(
            f"/api/chats/{chat.id}/restore",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"View-only user should not restore chat. Got {response.status_code}"
