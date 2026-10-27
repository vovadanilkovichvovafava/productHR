"""
Comprehensive tests for WebSocket realtime functionality.

These tests document the EXPECTED behavior of the WebSocket realtime event system.
Tests are marked as skipped until the WebSocket implementation is complete.

Expected WebSocket Architecture:
- Endpoint: ws://host/ws?token=<jwt_token>
- Authentication: JWT token in query parameter or header
- Event format: {"type": "event.type", "payload": {...}, "timestamp": "ISO8601"}
- Access control: Users only receive events for their organization and accessible resources
- Reconnection: Clients can reconnect and optionally request missed events
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json
import asyncio

# Note: websockets library needs to be installed: pip install websockets
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, Organization, Entity, Chat, Message, CallRecording, SharedAccess,
    EntityType, EntityStatus, ChatType, AccessLevel, ResourceType
)
from api.services.auth import create_access_token


# Skip all tests - WebSocket tests require a running server
# These are integration tests that should be run separately
pytestmark = pytest.mark.skip(
    reason="WebSocket tests require running server (integration tests)"
)


# ============================================================================
# WebSocket Test Helpers
# ============================================================================

class WebSocketTestHelper:
    """Helper class for WebSocket testing."""

    def __init__(self, base_url: str = "ws://localhost:8000"):
        self.base_url = base_url

    async def connect(self, token: str) -> "websockets.WebSocketClientProtocol":
        """Connect to WebSocket with authentication token."""
        ws_url = f"{self.base_url}/ws?token={token}"
        return await websockets.connect(ws_url)

    async def wait_for_event(
        self,
        ws: "websockets.WebSocketClientProtocol",
        event_type: str,
        timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Wait for a specific event type."""
        try:
            async with asyncio.timeout(timeout):
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    if data.get("type") == event_type:
                        return data
        except asyncio.TimeoutError:
            return None

    async def collect_events(
        self,
        ws: "websockets.WebSocketClientProtocol",
        duration: float = 1.0
    ) -> list[Dict[str, Any]]:
        """Collect all events received within a duration."""
        events = []
        try:
            async with asyncio.timeout(duration):
                while True:
                    message = await ws.recv()
                    events.append(json.loads(message))
        except asyncio.TimeoutError:
            pass
        return events


@pytest.fixture
def ws_helper():
    """WebSocket test helper fixture."""
    return WebSocketTestHelper()


# ============================================================================
# 1. WebSocket Connection Tests
# ============================================================================

class TestWebSocketConnection:
    """Test WebSocket connection establishment and authentication."""

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_websocket_connect_with_valid_token(
        self,
        admin_token: str,
        ws_helper: WebSocketTestHelper
    ):
        """Test successful WebSocket connection with valid JWT token.

        Expected behavior:
        - Client provides valid JWT token in query parameter
        - Server validates token and establishes WebSocket connection
        - Connection remains open for bidirectional communication
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Should connect without error
            assert ws.open
            assert ws.state.name == "OPEN"

            # Connection should remain stable
            await asyncio.sleep(0.5)
            assert ws.open

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_websocket_reject_without_token(self, ws_helper: WebSocketTestHelper):
        """Test WebSocket connection rejection without authentication token.

        Expected behavior:
        - Client attempts to connect without token
        - Server rejects connection with 401/403 status
        - Connection is not established
        """
        ws_url = f"{ws_helper.base_url}/ws"

        with pytest.raises(websockets.exceptions.InvalidStatusCode) as exc_info:
            async with websockets.connect(ws_url):
                pass

        # Should return 401 Unauthorized or 403 Forbidden
        assert exc_info.value.status_code in [401, 403]

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_websocket_reject_invalid_token(self, ws_helper: WebSocketTestHelper):
        """Test WebSocket connection rejection with invalid JWT token.

        Expected behavior:
        - Client provides malformed or invalid token
        - Server validates token and rejects connection
        - Connection is not established
        """
        invalid_token = "invalid.jwt.token"

        with pytest.raises(websockets.exceptions.InvalidStatusCode) as exc_info:
            async with await ws_helper.connect(invalid_token):
                pass

        assert exc_info.value.status_code in [401, 403]

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_websocket_disconnect_on_token_expiry(
        self,
        admin_user: User,
        ws_helper: WebSocketTestHelper
    ):
        """Test WebSocket disconnection when JWT token expires.

        Expected behavior:
        - Client connects with short-lived token
        - Connection is active while token is valid
        - Server closes connection when token expires
        - Client receives close code indicating token expiry
        """
        # Create token that expires in 2 seconds
        short_lived_token = create_access_token(
            data={"sub": str(admin_user.id)},
            expires_delta=timedelta(seconds=2)
        )

        async with await ws_helper.connect(short_lived_token) as ws:
            # Initially connected
            assert ws.open

            # Wait for token to expire
            await asyncio.sleep(3)

            # Server should close connection
            # Either already closed or will close on next message
            try:
                await ws.ping()
                await asyncio.sleep(0.5)
            except websockets.exceptions.ConnectionClosed:
                pass

            assert not ws.open
            # Close code should indicate authentication failure
            assert ws.close_code in [1008, 4001, 4002]  # Policy violation or custom auth codes


# ============================================================================
# 2. Event Broadcasting Tests
# ============================================================================

class TestEventBroadcasting:
    """Test real-time event broadcasting for various resource changes."""

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_receive_entity_created_event(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_token: str,
        organization: Organization,
        department: "Department",
        ws_helper: WebSocketTestHelper
    ):
        """Test receiving real-time event when entity is created.

        Expected behavior:
        - User connects to WebSocket
        - Entity is created via REST API
        - WebSocket receives 'entity.created' event with entity data
        - Event includes all relevant entity fields
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Create entity via API
            entity_data = {
                "name": "New Contact",
                "email": "newcontact@test.com",
                "type": EntityType.candidate.value,
                "status": EntityStatus.active.value,
                "department_id": department.id
            }

            response = await client.post(
                f"/organizations/{organization.id}/entities",
                json=entity_data,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 201

            # Should receive entity.created event
            event = await ws_helper.wait_for_event(ws, "entity.created", timeout=3.0)

            assert event is not None
            assert event["type"] == "entity.created"
            assert event["payload"]["name"] == "New Contact"
            assert event["payload"]["email"] == "newcontact@test.com"
            assert "id" in event["payload"]
            assert "timestamp" in event

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_receive_entity_updated_event(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        entity: Entity,
        ws_helper: WebSocketTestHelper
    ):
        """Test receiving real-time event when entity is updated.

        Expected behavior:
        - User connects to WebSocket
        - Entity is updated via REST API
        - WebSocket receives 'entity.updated' event
        - Event includes updated entity data
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Update entity via API
            update_data = {
                "name": "Updated Name",
                "status": EntityStatus.interview.value
            }

            response = await client.put(
                f"/organizations/{organization.id}/entities/{entity.id}",
                json=update_data,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 200

            # Should receive entity.updated event
            event = await ws_helper.wait_for_event(ws, "entity.updated", timeout=3.0)

            assert event is not None
            assert event["type"] == "entity.updated"
            assert event["payload"]["id"] == entity.id
            assert event["payload"]["name"] == "Updated Name"
            assert event["payload"]["status"] == EntityStatus.interview.value

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_receive_entity_deleted_event(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        entity: Entity,
        ws_helper: WebSocketTestHelper
    ):
        """Test receiving real-time event when entity is deleted.

        Expected behavior:
        - User connects to WebSocket
        - Entity is deleted via REST API
        - WebSocket receives 'entity.deleted' event
        - Event includes entity ID and minimal info
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Delete entity via API
            response = await client.delete(
                f"/organizations/{organization.id}/entities/{entity.id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 204

            # Should receive entity.deleted event
            event = await ws_helper.wait_for_event(ws, "entity.deleted", timeout=3.0)

            assert event is not None
            assert event["type"] == "entity.deleted"
            assert event["payload"]["id"] == entity.id
            assert event["payload"]["resource_type"] == "entity"

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_receive_chat_message_event(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_token: str,
        organization: Organization,
        chat: Chat,
        ws_helper: WebSocketTestHelper
    ):
        """Test receiving real-time event for new chat message.

        Expected behavior:
        - User connects to WebSocket
        - New message is added to chat
        - WebSocket receives 'chat.message' event
        - Event includes message content and metadata
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Create message in chat
            message = Message(
                chat_id=chat.id,
                sender_name="Test User",
                text="New message in chat",
                timestamp=datetime.utcnow(),
                is_from_bot=False
            )
            db_session.add(message)
            await db_session.commit()
            await db_session.refresh(message)

            # Should receive chat.message event
            event = await ws_helper.wait_for_event(ws, "chat.message", timeout=3.0)

            assert event is not None
            assert event["type"] == "chat.message"
            assert event["payload"]["chat_id"] == chat.id
            assert event["payload"]["text"] == "New message in chat"
            assert event["payload"]["sender_name"] == "Test User"

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_receive_share_created_event(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        entity: Entity,
        second_user: User,
        ws_helper: WebSocketTestHelper
    ):
        """Test receiving event when resource is shared with user.

        Expected behavior:
        - User connects to WebSocket
        - Resource is shared with the user
        - WebSocket receives 'share.created' event
        - Event includes share details and resource info
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Share entity via API
            share_data = {
                "resource_type": ResourceType.entity.value,
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": AccessLevel.view.value
            }

            response = await client.post(
                f"/organizations/{organization.id}/shares",
                json=share_data,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 201

            # Should receive share.created event
            event = await ws_helper.wait_for_event(ws, "share.created", timeout=3.0)

            assert event is not None
            assert event["type"] == "share.created"
            assert event["payload"]["resource_type"] == ResourceType.entity.value
            assert event["payload"]["resource_id"] == entity.id
            assert event["payload"]["access_level"] == AccessLevel.view.value

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_receive_share_revoked_event(
        self,
        client: AsyncClient,
        admin_token: str,
        organization: Organization,
        entity_share_view: SharedAccess,
        ws_helper: WebSocketTestHelper
    ):
        """Test receiving event when share is revoked.

        Expected behavior:
        - User connects to WebSocket
        - Share is revoked via API
        - WebSocket receives 'share.revoked' event
        - Event includes share ID and resource info
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Revoke share via API
            response = await client.delete(
                f"/organizations/{organization.id}/shares/{entity_share_view.id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 204

            # Should receive share.revoked event
            event = await ws_helper.wait_for_event(ws, "share.revoked", timeout=3.0)

            assert event is not None
            assert event["type"] == "share.revoked"
            assert event["payload"]["share_id"] == entity_share_view.id
            assert event["payload"]["resource_type"] == ResourceType.entity.value


# ============================================================================
# 3. Access Control Tests
# ============================================================================

class TestAccessControl:
    """Test WebSocket access control and event filtering."""

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_only_receive_own_org_events(
        self,
        db_session: AsyncSession,
        admin_token: str,
        second_user_token: str,
        organization: Organization,
        second_organization: Organization,
        department: "Department",
        ws_helper: WebSocketTestHelper
    ):
        """Test users only receive events for their own organization.

        Expected behavior:
        - User from Org A connects to WebSocket
        - Entity created in Org B
        - User from Org A does NOT receive the event
        - Only users in Org B receive the event
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Create entity in different organization
            other_entity = Entity(
                org_id=second_organization.id,
                department_id=department.id,
                created_by=1,
                name="Other Org Contact",
                email="other@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(other_entity)
            await db_session.commit()

            # Should NOT receive event for other organization
            events = await ws_helper.collect_events(ws, duration=2.0)
            entity_events = [e for e in events if e.get("type") == "entity.created"]

            # No entity.created events should be received
            assert len(entity_events) == 0

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_only_receive_accessible_resource_events(
        self,
        db_session: AsyncSession,
        second_user_token: str,
        second_user: User,
        entity: Entity,
        entity_share_view: SharedAccess,
        ws_helper: WebSocketTestHelper
    ):
        """Test users only receive events for resources they can access.

        Expected behavior:
        - User has view access to shared entity
        - Entity is updated
        - User receives the update event
        - Access control is enforced at event broadcast level
        """
        async with await ws_helper.connect(second_user_token) as ws:
            # Update shared entity
            entity.name = "Updated Shared Entity"
            entity.updated_at = datetime.utcnow()
            await db_session.commit()

            # Trigger event (in real implementation, this happens automatically)
            # Should receive event because user has access via share
            event = await ws_helper.wait_for_event(ws, "entity.updated", timeout=3.0)

            assert event is not None
            assert event["type"] == "entity.updated"
            assert event["payload"]["id"] == entity.id

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_no_events_for_unshared_resources(
        self,
        db_session: AsyncSession,
        second_user_token: str,
        entity: Entity,
        ws_helper: WebSocketTestHelper
    ):
        """Test users don't receive events for resources not shared with them.

        Expected behavior:
        - User does NOT have access to entity (not owner, not shared)
        - Entity is updated
        - User does NOT receive the update event
        - Access control prevents event delivery
        """
        async with await ws_helper.connect(second_user_token) as ws:
            # Update entity that is NOT shared with second_user
            entity.name = "Private Update"
            entity.updated_at = datetime.utcnow()
            await db_session.commit()

            # Should NOT receive event
            events = await ws_helper.collect_events(ws, duration=2.0)
            entity_events = [
                e for e in events
                if e.get("type") == "entity.updated" and e["payload"]["id"] == entity.id
            ]

            assert len(entity_events) == 0


# ============================================================================
# 4. Event Format Tests
# ============================================================================

class TestEventFormat:
    """Test WebSocket event message format and structure."""

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_event_has_type_field(
        self,
        db_session: AsyncSession,
        admin_token: str,
        organization: Organization,
        department: "Department",
        admin_user: User,
        ws_helper: WebSocketTestHelper
    ):
        """Test all events include 'type' field with event name.

        Expected behavior:
        - All events have a 'type' field
        - Type follows pattern: resource.action (e.g., entity.created)
        - Type is a string identifier for event categorization
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Create entity to trigger event
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name="Test Entity",
                email="test@example.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
            await db_session.commit()

            # Collect event
            events = await ws_helper.collect_events(ws, duration=1.0)

            # All events must have 'type' field
            assert len(events) > 0
            for event in events:
                assert "type" in event
                assert isinstance(event["type"], str)
                assert "." in event["type"]  # Format: resource.action

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_event_has_payload_field(
        self,
        db_session: AsyncSession,
        admin_token: str,
        organization: Organization,
        department: "Department",
        admin_user: User,
        ws_helper: WebSocketTestHelper
    ):
        """Test all events include 'payload' field with resource data.

        Expected behavior:
        - All events have a 'payload' field
        - Payload contains relevant resource data
        - Payload is a dictionary with resource-specific fields
        """
        async with await ws_helper.connect(admin_token) as ws:
            # Create entity to trigger event
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name="Payload Test Entity",
                email="payload@example.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
            await db_session.commit()

            # Get event
            event = await ws_helper.wait_for_event(ws, "entity.created", timeout=3.0)

            assert event is not None
            assert "payload" in event
            assert isinstance(event["payload"], dict)
            assert "id" in event["payload"]
            assert event["payload"]["name"] == "Payload Test Entity"

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_event_has_timestamp(
        self,
        db_session: AsyncSession,
        admin_token: str,
        organization: Organization,
        department: "Department",
        admin_user: User,
        ws_helper: WebSocketTestHelper
    ):
        """Test all events include timestamp field.

        Expected behavior:
        - All events have a 'timestamp' field
        - Timestamp is in ISO 8601 format
        - Timestamp reflects when event was generated
        """
        async with await ws_helper.connect(admin_token) as ws:
            before_create = datetime.utcnow()

            # Create entity to trigger event
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name="Timestamp Test",
                email="timestamp@example.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
            await db_session.commit()

            after_create = datetime.utcnow()

            # Get event
            event = await ws_helper.wait_for_event(ws, "entity.created", timeout=3.0)

            assert event is not None
            assert "timestamp" in event

            # Validate timestamp format and value
            timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            assert before_create <= timestamp <= after_create + timedelta(seconds=1)


# ============================================================================
# 5. Reconnection Tests
# ============================================================================

class TestReconnection:
    """Test WebSocket reconnection handling and event recovery."""

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_can_reconnect_after_disconnect(
        self,
        admin_token: str,
        ws_helper: WebSocketTestHelper
    ):
        """Test client can reconnect after disconnection.

        Expected behavior:
        - Client connects to WebSocket
        - Client disconnects (intentionally or due to network)
        - Client can establish new connection with same token
        - New connection works normally
        """
        # First connection
        async with await ws_helper.connect(admin_token) as ws1:
            assert ws1.open
            # Normal disconnect

        assert not ws1.open

        # Reconnect with same token
        async with await ws_helper.connect(admin_token) as ws2:
            assert ws2.open

            # Verify connection works
            await asyncio.sleep(0.5)
            assert ws2.open

    @pytest.mark.asyncio
    # WebSocket endpoint now implemented
    async def test_missed_events_queue(
        self,
        db_session: AsyncSession,
        admin_token: str,
        organization: Organization,
        department: "Department",
        admin_user: User,
        ws_helper: WebSocketTestHelper
    ):
        """Test option to retrieve missed events after reconnection.

        Expected behavior:
        - Client connects, then disconnects
        - Events occur while client is disconnected
        - Client reconnects with last_event_id or timestamp
        - Server sends missed events to client

        Note: This is an optional advanced feature. Implementation may vary.
        Possible approaches:
        - Client sends last received event ID on reconnect
        - Server maintains short-term event buffer per user
        - Events sent in chronological order
        """
        # Initial connection to get last event ID
        async with await ws_helper.connect(admin_token) as ws:
            # Wait briefly to establish connection
            await asyncio.sleep(0.5)
            last_event_id = None

        # Disconnect
        assert not ws.open

        # Create events while disconnected
        entity1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Missed Event 1",
            email="missed1@example.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        entity2 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Missed Event 2",
            email="missed2@example.com",
            type=EntityType.client,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add_all([entity1, entity2])
        await db_session.commit()

        # Reconnect and request missed events
        # URL format: ws://host/ws?token=<token>&since_event_id=<id>
        # or: ws://host/ws?token=<token>&since=<timestamp>
        ws_url = f"{ws_helper.base_url}/ws?token={admin_token}&since_event_id={last_event_id or 0}"
        async with websockets.connect(ws_url) as ws_reconnect:
            # Should receive missed events
            events = await ws_helper.collect_events(ws_reconnect, duration=2.0)
            entity_created_events = [
                e for e in events if e.get("type") == "entity.created"
            ]

            # Should have received both missed events
            assert len(entity_created_events) >= 2
            event_names = [e["payload"]["name"] for e in entity_created_events]
            assert "Missed Event 1" in event_names
            assert "Missed Event 2" in event_names
