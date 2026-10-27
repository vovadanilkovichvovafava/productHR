"""
Unit tests for WebSocket realtime routes and connection management.

Tests cover:
- ConnectionManager class methods
- WebSocket authentication
- Event broadcasting
- Access control
- Error handling
"""
import pytest
import pytest_asyncio
from datetime import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch, call
import json

from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.realtime import (
    ConnectionManager,
    authenticate_websocket,
    get_user_org_id,
    broadcast_entity_created,
    broadcast_entity_updated,
    broadcast_entity_deleted,
    broadcast_chat_message,
    broadcast_share_created,
    broadcast_share_revoked,
    broadcast_call_progress,
    broadcast_call_completed,
    broadcast_call_failed
)
from api.models.database import User, Organization, OrgMember, OrgRole


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.cookies = {}  # Empty cookies by default
    return ws


@pytest.fixture
def mock_websocket_with_cookie():
    """Create a mock WebSocket connection with cookie support."""
    def _create(cookie_token=None):
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_text = AsyncMock()
        ws.cookies = {"access_token": cookie_token} if cookie_token else {}
        return ws
    return _create


@pytest.fixture
def connection_manager():
    """Create a fresh ConnectionManager instance for testing."""
    return ConnectionManager()


@pytest_asyncio.fixture
async def user_with_org(db_session: AsyncSession, admin_user: User, organization: Organization) -> tuple[User, Organization]:
    """Create a user with organization membership."""
    member = OrgMember(
        org_id=organization.id,
        user_id=admin_user.id,
        role=OrgRole.owner,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return admin_user, organization


@pytest_asyncio.fixture
async def second_user_with_org(db_session: AsyncSession, second_user: User, organization: Organization) -> tuple[User, Organization]:
    """Create a second user with organization membership."""
    member = OrgMember(
        org_id=organization.id,
        user_id=second_user.id,
        role=OrgRole.member,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return second_user, organization


# ============================================================================
# 1. ConnectionManager Tests
# ============================================================================

class TestConnectionManager:
    """Test ConnectionManager class methods."""

    @pytest.mark.asyncio
    async def test_connect_new_user(self, connection_manager: ConnectionManager, mock_websocket, admin_user: User):
        """Test connecting a new user to WebSocket."""
        org_id = 1

        await connection_manager.connect(mock_websocket, admin_user, org_id)

        # Verify WebSocket was accepted
        mock_websocket.accept.assert_awaited_once()

        # Verify user was added to active connections
        assert admin_user.id in connection_manager.active_connections
        assert mock_websocket in connection_manager.active_connections[admin_user.id]
        assert connection_manager.user_orgs[admin_user.id] == org_id

    @pytest.mark.asyncio
    async def test_connect_multiple_connections_same_user(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test same user can have multiple WebSocket connections."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        org_id = 1

        await connection_manager.connect(ws1, admin_user, org_id)
        await connection_manager.connect(ws2, admin_user, org_id)

        # Verify both connections are tracked
        assert len(connection_manager.active_connections[admin_user.id]) == 2
        assert ws1 in connection_manager.active_connections[admin_user.id]
        assert ws2 in connection_manager.active_connections[admin_user.id]

    @pytest.mark.asyncio
    async def test_disconnect_user(self, connection_manager: ConnectionManager, mock_websocket, admin_user: User):
        """Test disconnecting a user from WebSocket."""
        org_id = 1

        # First connect
        await connection_manager.connect(mock_websocket, admin_user, org_id)
        assert admin_user.id in connection_manager.active_connections

        # Then disconnect
        await connection_manager.disconnect(mock_websocket, admin_user.id)

        # Verify user was removed
        assert admin_user.id not in connection_manager.active_connections
        assert admin_user.id not in connection_manager.user_orgs

    @pytest.mark.asyncio
    async def test_disconnect_one_of_multiple_connections(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test disconnecting one connection when user has multiple."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        org_id = 1

        # Connect both
        await connection_manager.connect(ws1, admin_user, org_id)
        await connection_manager.connect(ws2, admin_user, org_id)

        # Disconnect only first connection
        await connection_manager.disconnect(ws1, admin_user.id)

        # Verify first is removed but second remains
        assert admin_user.id in connection_manager.active_connections
        assert ws1 not in connection_manager.active_connections[admin_user.id]
        assert ws2 in connection_manager.active_connections[admin_user.id]
        assert connection_manager.user_orgs[admin_user.id] == org_id

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_user(self, connection_manager: ConnectionManager, mock_websocket):
        """Test disconnecting a user that isn't connected."""
        # Should not raise error
        await connection_manager.disconnect(mock_websocket, 999)

        # Manager should remain empty
        assert 999 not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_org_single_user(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting event to organization with single user."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        # Broadcast event
        event_type = "entity.created"
        payload = {"id": 123, "name": "Test Entity"}
        await connection_manager.broadcast_to_org(org_id, event_type, payload)

        # Verify message was sent
        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == event_type
        assert event_data["payload"] == payload
        assert "timestamp" in event_data

    @pytest.mark.asyncio
    async def test_broadcast_to_org_multiple_users(
        self,
        connection_manager: ConnectionManager,
        admin_user: User,
        second_user: User
    ):
        """Test broadcasting event to multiple users in same organization."""
        org_id = 1
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await connection_manager.connect(ws1, admin_user, org_id)
        await connection_manager.connect(ws2, second_user, org_id)

        # Broadcast event
        event_type = "chat.message"
        payload = {"text": "Hello"}
        await connection_manager.broadcast_to_org(org_id, event_type, payload)

        # Verify both users received message
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

        # Verify message content
        message1 = json.loads(ws1.send_text.call_args[0][0])
        message2 = json.loads(ws2.send_text.call_args[0][0])
        assert message1["type"] == event_type
        assert message2["type"] == event_type
        assert message1["payload"] == payload
        assert message2["payload"] == payload

    @pytest.mark.asyncio
    async def test_broadcast_to_org_different_org_not_received(
        self,
        connection_manager: ConnectionManager,
        admin_user: User,
        second_user: User
    ):
        """Test users in different organization don't receive events."""
        org1_id = 1
        org2_id = 2
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await connection_manager.connect(ws1, admin_user, org1_id)
        await connection_manager.connect(ws2, second_user, org2_id)

        # Broadcast to org1 only
        await connection_manager.broadcast_to_org(org1_id, "entity.created", {"id": 1})

        # Only user in org1 should receive
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_to_org_handles_send_failure(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test broadcasting handles WebSocket send failures gracefully."""
        org_id = 1
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock(side_effect=Exception("Connection lost"))

        await connection_manager.connect(mock_ws, admin_user, org_id)

        # Broadcast should not raise error
        await connection_manager.broadcast_to_org(org_id, "test.event", {})

        # Failed connection should be cleaned up
        assert admin_user.id not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_user_single_connection(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting event to specific user."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        # Broadcast to user
        event_type = "share.created"
        payload = {"resource_id": 456, "access_level": "view"}
        await connection_manager.broadcast_to_user(admin_user.id, event_type, payload)

        # Verify message was sent
        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == event_type
        assert event_data["payload"] == payload

    @pytest.mark.asyncio
    async def test_broadcast_to_user_multiple_connections(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test broadcasting to user with multiple connections."""
        org_id = 1
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await connection_manager.connect(ws1, admin_user, org_id)
        await connection_manager.connect(ws2, admin_user, org_id)

        # Broadcast to user
        await connection_manager.broadcast_to_user(admin_user.id, "notification", {"msg": "test"})

        # Both connections should receive message
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_user_not_connected(self, connection_manager: ConnectionManager):
        """Test broadcasting to user who is not connected."""
        # Should not raise error
        await connection_manager.broadcast_to_user(999, "test.event", {})

    @pytest.mark.asyncio
    async def test_broadcast_to_user_handles_send_failure(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test broadcasting to user handles send failures."""
        org_id = 1
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock(side_effect=Exception("Send failed"))

        await connection_manager.connect(mock_ws, admin_user, org_id)

        # Broadcast should not raise error
        await connection_manager.broadcast_to_user(admin_user.id, "test.event", {})

        # Failed connection should be cleaned up
        assert admin_user.id not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_send_to_connection_success(self, connection_manager: ConnectionManager):
        """Test sending event to specific WebSocket connection."""
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()

        event_type = "ping"
        payload = {"server_time": "2024-01-01T00:00:00Z"}
        await connection_manager.send_to_connection(mock_ws, event_type, payload)

        # Verify message was sent
        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == event_type
        assert event_data["payload"] == payload
        assert "timestamp" in event_data

    @pytest.mark.asyncio
    async def test_send_to_connection_handles_failure(self, connection_manager: ConnectionManager):
        """Test sending to connection handles failures gracefully."""
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock(side_effect=Exception("Send failed"))

        # Should not raise error
        await connection_manager.send_to_connection(mock_ws, "test", {})

    @pytest.mark.asyncio
    async def test_event_timestamp_format(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test that event timestamps are in correct ISO format."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        await connection_manager.broadcast_to_org(org_id, "test.event", {})

        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        # Verify timestamp format (ISO 8601 with Z suffix)
        assert "timestamp" in event_data
        assert event_data["timestamp"].endswith("Z")
        # Should be parseable as datetime
        datetime.fromisoformat(event_data["timestamp"].replace("Z", "+00:00"))


# ============================================================================
# 2. Authentication Tests
# ============================================================================

class TestWebSocketAuthentication:
    """Test WebSocket authentication functions."""

    @pytest.mark.asyncio
    async def test_authenticate_websocket_valid_token(
        self,
        db_session: AsyncSession,
        admin_user: User,
        admin_token: str,
        mock_websocket
    ):
        """Test authenticating WebSocket with valid token."""
        user = await authenticate_websocket(admin_token, mock_websocket, db_session)

        assert user is not None
        assert user.id == admin_user.id
        assert user.email == admin_user.email

    @pytest.mark.asyncio
    async def test_authenticate_websocket_no_token(self, db_session: AsyncSession, mock_websocket):
        """Test authenticating WebSocket without token."""
        user = await authenticate_websocket(None, mock_websocket, db_session)

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_empty_token(self, db_session: AsyncSession, mock_websocket):
        """Test authenticating WebSocket with empty token."""
        user = await authenticate_websocket("", mock_websocket, db_session)

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_invalid_token(self, db_session: AsyncSession, mock_websocket):
        """Test authenticating WebSocket with invalid token."""
        invalid_token = "invalid.jwt.token"
        user = await authenticate_websocket(invalid_token, mock_websocket, db_session)

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_malformed_token(self, db_session: AsyncSession, mock_websocket):
        """Test authenticating WebSocket with malformed token."""
        malformed_token = "not-a-jwt-token"
        user = await authenticate_websocket(malformed_token, mock_websocket, db_session)

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_cookie_auth(
        self,
        db_session: AsyncSession,
        admin_user: User,
        admin_token: str,
        mock_websocket_with_cookie
    ):
        """Test authenticating WebSocket with cookie-based auth."""
        ws = mock_websocket_with_cookie(admin_token)
        user = await authenticate_websocket(None, ws, db_session)

        assert user is not None
        assert user.id == admin_user.id
        assert user.email == admin_user.email

    @pytest.mark.asyncio
    async def test_get_user_org_id_with_membership(
        self,
        db_session: AsyncSession,
        user_with_org: tuple[User, Organization]
    ):
        """Test getting user's organization ID when user is member."""
        user, org = user_with_org

        org_id = await get_user_org_id(user, db_session)

        assert org_id is not None
        assert org_id == org.id

    @pytest.mark.asyncio
    async def test_get_user_org_id_without_membership(
        self,
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test getting user's organization ID when user has no organization."""
        org_id = await get_user_org_id(admin_user, db_session)

        # User not in any organization
        assert org_id is None

    @pytest.mark.asyncio
    async def test_get_user_org_id_multiple_memberships(
        self,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        second_organization: Organization
    ):
        """Test getting user's organization ID when user is in multiple orgs."""
        # Add user to first org
        member1 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(member1)
        await db_session.commit()

        # Add user to second org
        member2 = OrgMember(
            org_id=second_organization.id,
            user_id=admin_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member2)
        await db_session.commit()

        org_id = await get_user_org_id(admin_user, db_session)

        # Should return first organization ID
        assert org_id is not None
        assert org_id in [organization.id, second_organization.id]


# ============================================================================
# 3. Broadcast Helper Function Tests
# ============================================================================

class TestBroadcastHelpers:
    """Test helper functions for broadcasting events."""

    @pytest.mark.asyncio
    async def test_broadcast_entity_created(self, connection_manager: ConnectionManager, admin_user: User, monkeypatch):
        """Test broadcasting entity created event."""
        org_id = 1
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await connection_manager.connect(mock_ws, admin_user, org_id)

        entity_data = {
            "id": 123,
            "name": "New Entity",
            "email": "entity@test.com",
            "type": "candidate"
        }

        # Patch the global manager in the realtime module
        monkeypatch.setattr("api.routes.realtime.manager", connection_manager)

        await broadcast_entity_created(org_id, entity_data)

        # Verify message was sent
        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "entity.created"
        assert event_data["payload"] == entity_data

    @pytest.mark.asyncio
    async def test_broadcast_entity_updated(self, connection_manager: ConnectionManager, admin_user: User, monkeypatch):
        """Test broadcasting entity updated event."""
        org_id = 1
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await connection_manager.connect(mock_ws, admin_user, org_id)

        entity_data = {
            "id": 123,
            "name": "Updated Entity",
            "status": "active"
        }

        # Patch the global manager in the realtime module
        monkeypatch.setattr("api.routes.realtime.manager", connection_manager)

        await broadcast_entity_updated(org_id, entity_data)

        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "entity.updated"
        assert event_data["payload"] == entity_data

    @pytest.mark.asyncio
    async def test_broadcast_entity_deleted(self, connection_manager: ConnectionManager, admin_user: User, monkeypatch):
        """Test broadcasting entity deleted event."""
        org_id = 1
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await connection_manager.connect(mock_ws, admin_user, org_id)

        entity_id = 123

        # Patch the global manager in the realtime module
        monkeypatch.setattr("api.routes.realtime.manager", connection_manager)

        await broadcast_entity_deleted(org_id, entity_id)

        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "entity.deleted"
        assert event_data["payload"]["id"] == entity_id
        assert event_data["payload"]["resource_type"] == "entity"

    @pytest.mark.asyncio
    async def test_broadcast_chat_message(self, connection_manager: ConnectionManager, admin_user: User, monkeypatch):
        """Test broadcasting chat message event."""
        org_id = 1
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await connection_manager.connect(mock_ws, admin_user, org_id)

        message_data = {
            "chat_id": 456,
            "text": "Hello, world!",
            "sender_name": "Test User"
        }

        # Patch the global manager in the realtime module
        monkeypatch.setattr("api.routes.realtime.manager", connection_manager)

        await broadcast_chat_message(org_id, message_data)

        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "chat.message"
        assert event_data["payload"] == message_data

    @pytest.mark.asyncio
    async def test_broadcast_share_created(self, connection_manager: ConnectionManager, admin_user: User, monkeypatch):
        """Test broadcasting share created event."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await connection_manager.connect(mock_ws, admin_user, org_id=1)

        share_data = {
            "resource_type": "entity",
            "resource_id": 789,
            "access_level": "view",
            "shared_by_id": 1,
            "shared_with_id": admin_user.id
        }

        # Patch the global manager in the realtime module
        monkeypatch.setattr("api.routes.realtime.manager", connection_manager)

        await broadcast_share_created(admin_user.id, share_data)

        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "share.created"
        assert event_data["payload"] == share_data

    @pytest.mark.asyncio
    async def test_broadcast_share_revoked(self, connection_manager: ConnectionManager, admin_user: User, monkeypatch):
        """Test broadcasting share revoked event."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await connection_manager.connect(mock_ws, admin_user, org_id=1)

        share_data = {
            "share_id": 999,
            "resource_type": "entity",
            "resource_id": 789
        }

        # Patch the global manager in the realtime module
        monkeypatch.setattr("api.routes.realtime.manager", connection_manager)

        await broadcast_share_revoked(admin_user.id, share_data)

        mock_ws.send_text.assert_awaited_once()
        sent_message = mock_ws.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "share.revoked"
        assert event_data["payload"] == share_data


# ============================================================================
# 4. Edge Cases and Error Handling Tests
# ============================================================================

class TestEdgeCasesAndErrors:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_concurrent_connections(
        self,
        connection_manager: ConnectionManager,
        admin_user: User,
        second_user: User
    ):
        """Test handling multiple concurrent connections."""
        org_id = 1
        websockets = []

        # Connect multiple users concurrently
        for user in [admin_user, second_user]:
            for _ in range(3):  # 3 connections per user
                ws = AsyncMock()
                ws.accept = AsyncMock()
                ws.send_text = AsyncMock()
                await connection_manager.connect(ws, user, org_id)
                websockets.append(ws)

        # Verify all connections are tracked
        assert len(connection_manager.active_connections[admin_user.id]) == 3
        assert len(connection_manager.active_connections[second_user.id]) == 3

        # Broadcast should reach all connections
        await connection_manager.broadcast_to_org(org_id, "test.event", {})

        for ws in websockets:
            ws.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_with_empty_payload(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting with empty payload."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        # Empty payload should be valid
        await connection_manager.broadcast_to_org(org_id, "test.event", {})

        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "test.event"
        assert event_data["payload"] == {}

    @pytest.mark.asyncio
    async def test_broadcast_with_complex_payload(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting with complex nested payload."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        complex_payload = {
            "entity": {
                "id": 123,
                "name": "Test",
                "metadata": {
                    "tags": ["tag1", "tag2"],
                    "scores": [1, 2, 3],
                    "nested": {
                        "deep": "value"
                    }
                }
            },
            "timestamp": "2024-01-01T00:00:00Z"
        }

        await connection_manager.broadcast_to_org(org_id, "complex.event", complex_payload)

        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["payload"] == complex_payload

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_properly(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test that disconnect properly cleans up all data structures."""
        org_id = 1
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()

        # Connect
        await connection_manager.connect(ws1, admin_user, org_id)
        assert admin_user.id in connection_manager.active_connections
        assert admin_user.id in connection_manager.user_orgs

        # Disconnect
        await connection_manager.disconnect(ws1, admin_user.id)

        # Verify complete cleanup
        assert admin_user.id not in connection_manager.active_connections
        assert admin_user.id not in connection_manager.user_orgs

    @pytest.mark.asyncio
    async def test_multiple_orgs_isolation(
        self,
        connection_manager: ConnectionManager,
        admin_user: User,
        second_user: User
    ):
        """Test that events are properly isolated between organizations."""
        org1_id = 1
        org2_id = 2
        org3_id = 3

        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users to different orgs
        await connection_manager.connect(ws1, admin_user, org1_id)
        await connection_manager.connect(ws2, second_user, org2_id)

        # Broadcast to org1
        await connection_manager.broadcast_to_org(org1_id, "event.org1", {"data": "org1"})
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_not_awaited()

        ws1.send_text.reset_mock()
        ws2.send_text.reset_mock()

        # Broadcast to org2
        await connection_manager.broadcast_to_org(org2_id, "event.org2", {"data": "org2"})
        ws1.send_text.assert_not_awaited()
        ws2.send_text.assert_awaited_once()

        ws1.send_text.reset_mock()
        ws2.send_text.reset_mock()

        # Broadcast to org3 (no users)
        await connection_manager.broadcast_to_org(org3_id, "event.org3", {"data": "org3"})
        ws1.send_text.assert_not_awaited()
        ws2.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_thread_safety_with_concurrent_operations(
        self,
        connection_manager: ConnectionManager,
        admin_user: User
    ):
        """Test that ConnectionManager handles concurrent operations safely."""
        import asyncio

        org_id = 1
        websockets_list = []

        # Create multiple connections
        async def connect_user():
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_text = AsyncMock()
            await connection_manager.connect(ws, admin_user, org_id)
            websockets_list.append(ws)

        # Connect 5 users concurrently
        await asyncio.gather(*[connect_user() for _ in range(5)])

        # Verify all connections are tracked
        assert len(connection_manager.active_connections[admin_user.id]) == 5

        # Broadcast concurrently with disconnects
        async def broadcast_task():
            await connection_manager.broadcast_to_org(org_id, "concurrent.test", {})

        async def disconnect_task(ws):
            await connection_manager.disconnect(ws, admin_user.id)

        # Run broadcasts and disconnects concurrently
        tasks = [broadcast_task() for _ in range(3)]
        tasks += [disconnect_task(ws) for ws in websockets_list[:2]]

        await asyncio.gather(*tasks)

        # Should not crash and should handle cleanup
        assert len(connection_manager.active_connections.get(admin_user.id, set())) == 3

    @pytest.mark.asyncio
    async def test_special_characters_in_payload(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test handling special characters in event payload."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        payload = {
            "text": "Special chars: <>&\"'",
            "unicode": "Unicode: 你好世界 🌍",
            "newlines": "Line1\nLine2\nLine3",
            "tabs": "Tab\there"
        }

        await connection_manager.broadcast_to_org(org_id, "special.chars", payload)

        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        # Verify all special characters are preserved
        assert event_data["payload"] == payload


# ============================================================================
# 7. Call Processing Events Tests
# ============================================================================

class TestCallProcessingBroadcasts:
    """Tests for call processing broadcast functions."""

    @pytest.mark.asyncio
    async def test_broadcast_call_progress(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting call processing progress."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        call_data = {
            "id": 123,
            "progress": 50,
            "progress_stage": "Извлечение транскрипта...",
            "status": "processing"
        }

        with patch('api.routes.realtime.manager', connection_manager):
            await broadcast_call_progress(org_id, call_data)

        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "call.progress"
        assert event_data["payload"]["id"] == 123
        assert event_data["payload"]["progress"] == 50
        assert event_data["payload"]["progress_stage"] == "Извлечение транскрипта..."

    @pytest.mark.asyncio
    async def test_broadcast_call_completed(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting call processing completion."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        call_data = {
            "id": 456,
            "title": "Interview Call",
            "status": "done",
            "has_summary": True,
            "has_transcript": True,
            "duration_seconds": 1800,
            "speaker_stats": {"HR": {"total_seconds": 900, "percentage": 50}},
            "progress": 100,
            "progress_stage": "Готово"
        }

        with patch('api.routes.realtime.manager', connection_manager):
            await broadcast_call_completed(org_id, call_data)

        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "call.completed"
        assert event_data["payload"]["id"] == 456
        assert event_data["payload"]["status"] == "done"
        assert event_data["payload"]["has_summary"] is True
        assert event_data["payload"]["progress"] == 100

    @pytest.mark.asyncio
    async def test_broadcast_call_failed(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test broadcasting call processing failure."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        call_data = {
            "id": 789,
            "status": "failed",
            "error_message": "Could not extract transcript",
            "progress": 0,
            "progress_stage": "Ошибка"
        }

        with patch('api.routes.realtime.manager', connection_manager):
            await broadcast_call_failed(org_id, call_data)

        mock_websocket.send_text.assert_awaited_once()
        sent_message = mock_websocket.send_text.call_args[0][0]
        event_data = json.loads(sent_message)

        assert event_data["type"] == "call.failed"
        assert event_data["payload"]["id"] == 789
        assert event_data["payload"]["status"] == "failed"
        assert event_data["payload"]["error_message"] == "Could not extract transcript"
        assert event_data["payload"]["progress"] == 0

    @pytest.mark.asyncio
    async def test_call_events_only_sent_to_same_org(
        self,
        connection_manager: ConnectionManager,
        admin_user: User,
        second_user: User
    ):
        """Test that call events are only broadcast to users in the same org."""
        org_id_1 = 1
        org_id_2 = 2

        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await connection_manager.connect(ws1, admin_user, org_id_1)
        await connection_manager.connect(ws2, second_user, org_id_2)

        call_data = {"id": 123, "progress": 75, "progress_stage": "AI анализ..."}

        with patch('api.routes.realtime.manager', connection_manager):
            await broadcast_call_progress(org_id_1, call_data)

        # Only user in org_1 should receive the event
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_call_progress_multiple_updates(
        self,
        connection_manager: ConnectionManager,
        mock_websocket,
        admin_user: User
    ):
        """Test multiple progress updates are sent correctly."""
        org_id = 1
        await connection_manager.connect(mock_websocket, admin_user, org_id)

        progress_stages = [
            (5, "Запуск обработки..."),
            (10, "Загрузка страницы Fireflies..."),
            (30, "Извлечение транскрипта..."),
            (60, "AI анализ транскрипта..."),
            (90, "Сохранение результатов..."),
            (100, "Готово")
        ]

        with patch('api.routes.realtime.manager', connection_manager):
            for progress, stage in progress_stages:
                await broadcast_call_progress(org_id, {
                    "id": 123,
                    "progress": progress,
                    "progress_stage": stage,
                    "status": "processing" if progress < 100 else "done"
                })

        # Should have sent 6 messages
        assert mock_websocket.send_text.await_count == 6

        # Check last message is 100%
        last_message = mock_websocket.send_text.call_args_list[-1][0][0]
        event_data = json.loads(last_message)
        assert event_data["payload"]["progress"] == 100
        assert event_data["payload"]["progress_stage"] == "Готово"
