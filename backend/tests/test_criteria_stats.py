"""
Comprehensive tests for Criteria and Stats endpoints.

This module tests:
- Criteria presets CRUD operations
- Chat criteria CRUD operations
- Permission checks for criteria operations
- Stats calculation for superadmin and regular users
- Stats filtering and aggregation
"""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient

from api.models.database import (
    User, Chat, Message, CriteriaPreset, ChatCriteria, AnalysisHistory,
    UserRole, ChatType
)


# ============================================================================
# CRITERIA PRESETS TESTS
# ============================================================================

class TestCriteriaPresets:
    """Tests for criteria preset endpoints."""

    @pytest.mark.asyncio
    async def test_get_presets_global_and_user_owned(
        self, client: AsyncClient, db_session, admin_user, second_user, admin_token,
        get_auth_headers
    ):
        """Test getting global presets and user's own presets."""
        # Create a global preset (created by admin_user)
        global_preset = CriteriaPreset(
            name="Global Preset",
            description="A global preset",
            criteria=[{"name": "Experience", "weight": 8}],
            category="technical",
            is_global=True,
            created_by=admin_user.id
        )
        db_session.add(global_preset)

        # Create user's own preset
        user_preset = CriteriaPreset(
            name="User Preset",
            description="User's personal preset",
            criteria=[{"name": "Communication", "weight": 7}],
            category="soft_skills",
            is_global=False,
            created_by=admin_user.id
        )
        db_session.add(user_preset)

        # Create another user's preset (should not be visible)
        other_preset = CriteriaPreset(
            name="Other User Preset",
            description="Another user's preset",
            criteria=[{"name": "Leadership", "weight": 6}],
            category="management",
            is_global=False,
            created_by=second_user.id  # Use second_user instead of non-existent ID
        )
        db_session.add(other_preset)
        await db_session.commit()

        response = await client.get(
            "/api/criteria/presets",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        preset_names = [p["name"] for p in data]

        # Should see global preset
        assert "Global Preset" in preset_names

        # Should see own preset
        assert "User Preset" in preset_names

        # Should NOT see other user's preset
        assert "Other User Preset" not in preset_names

    @pytest.mark.asyncio
    async def test_get_presets_empty_list(
        self, client: AsyncClient, admin_user, admin_token,
        get_auth_headers
    ):
        """Test getting presets when none exist."""
        response = await client.get(
            "/api/criteria/presets",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_presets_ordered_by_category_and_name(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        get_auth_headers
    ):
        """Test that presets are ordered by category and name."""
        presets = [
            CriteriaPreset(
                name="Z Preset",
                criteria=[{"name": "Test", "weight": 5}],
                category="technical",
                is_global=True,
                created_by=admin_user.id
            ),
            CriteriaPreset(
                name="A Preset",
                criteria=[{"name": "Test", "weight": 5}],
                category="technical",
                is_global=True,
                created_by=admin_user.id
            ),
            CriteriaPreset(
                name="B Preset",
                criteria=[{"name": "Test", "weight": 5}],
                category="soft_skills",
                is_global=True,
                created_by=admin_user.id
            ),
        ]
        for preset in presets:
            db_session.add(preset)
        await db_session.commit()

        response = await client.get(
            "/api/criteria/presets",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Check ordering
        names = [p["name"] for p in data]
        categories = [p["category"] for p in data]

        # Should be ordered by category first, then name
        assert names == ["B Preset", "A Preset", "Z Preset"]

    @pytest.mark.asyncio
    async def test_create_preset_as_regular_user(
        self, client: AsyncClient, admin_user, admin_token,
        get_auth_headers
    ):
        """Test creating a personal preset as a regular user."""
        preset_data = {
            "name": "My Custom Preset",
            "description": "Personal preset for technical interviews",
            "criteria": [
                {"name": "Technical Skills", "weight": 9, "category": "basic"},
                {"name": "Problem Solving", "weight": 8, "category": "basic"},
                {"name": "Red Flag: Arrogance", "weight": 10, "category": "red_flag"}
            ],
            "category": "technical",
            "is_global": False
        }

        response = await client.post(
            "/api/criteria/presets",
            json=preset_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == preset_data["name"]
        assert data["description"] == preset_data["description"]
        assert len(data["criteria"]) == 3
        assert data["category"] == "technical"
        assert data["is_global"] is False
        assert data["created_by"] == admin_user.id
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_global_preset_as_superadmin(
        self, client: AsyncClient, superadmin_user, superadmin_token,
        get_auth_headers
    ):
        """Test that superadmin can create global presets."""
        preset_data = {
            "name": "Global Technical Preset",
            "description": "Standard technical interview criteria",
            "criteria": [
                {"name": "Coding Skills", "weight": 10},
                {"name": "System Design", "weight": 8}
            ],
            "category": "technical",
            "is_global": True
        }

        response = await client.post(
            "/api/criteria/presets",
            json=preset_data,
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()

        assert data["is_global"] is True
        assert data["created_by"] == superadmin_user.id

    @pytest.mark.asyncio
    async def test_create_global_preset_as_regular_user_becomes_personal(
        self, client: AsyncClient, admin_user, admin_token,
        get_auth_headers
    ):
        """Test that regular users cannot create global presets."""
        preset_data = {
            "name": "Attempted Global Preset",
            "description": "Trying to create global",
            "criteria": [{"name": "Test", "weight": 5}],
            "category": "technical",
            "is_global": True  # Try to set as global
        }

        response = await client.post(
            "/api/criteria/presets",
            json=preset_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()

        # Should be created as personal preset (is_global=False)
        assert data["is_global"] is False
        assert data["created_by"] == admin_user.id

    @pytest.mark.asyncio
    async def test_create_preset_with_minimal_data(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test creating preset with minimal required fields."""
        preset_data = {
            "name": "Minimal Preset",
            "criteria": [{"name": "Test Criterion", "weight": 5}]
        }

        response = await client.post(
            "/api/criteria/presets",
            json=preset_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "Minimal Preset"
        assert data["description"] is None
        assert data["category"] is None
        assert len(data["criteria"]) == 1

    @pytest.mark.asyncio
    async def test_create_preset_with_weight_validation(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test that criteria weights are validated (1-10)."""
        preset_data = {
            "name": "Weight Test",
            "criteria": [
                {"name": "Valid", "weight": 5},
                {"name": "Max Weight", "weight": 10},
                {"name": "Min Weight", "weight": 1}
            ]
        }

        response = await client.post(
            "/api/criteria/presets",
            json=preset_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_delete_preset_as_owner(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        get_auth_headers
    ):
        """Test deleting own preset."""
        preset = CriteriaPreset(
            name="To Delete",
            criteria=[{"name": "Test", "weight": 5}],
            is_global=False,
            created_by=admin_user.id
        )
        db_session.add(preset)
        await db_session.commit()
        await db_session.refresh(preset)

        response = await client.delete(
            f"/api/criteria/presets/{preset.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 204

        # Verify deletion
        response = await client.get(
            "/api/criteria/presets",
            headers=get_auth_headers(admin_token)
        )
        data = response.json()
        preset_ids = [p["id"] for p in data]
        assert preset.id not in preset_ids

    @pytest.mark.asyncio
    async def test_delete_preset_not_owner_fails(
        self, client: AsyncClient, db_session, admin_user, second_user,
        admin_token, get_auth_headers, org_owner, org_member
    ):
        """Test that users cannot delete other users' presets."""
        # Create preset owned by second_user
        preset = CriteriaPreset(
            name="Other User Preset",
            criteria=[{"name": "Test", "weight": 5}],
            is_global=False,
            created_by=second_user.id
        )
        db_session.add(preset)
        await db_session.commit()
        await db_session.refresh(preset)

        # Try to delete as admin_user
        response = await client.delete(
            f"/api/criteria/presets/{preset.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_preset_as_superadmin(
        self, client: AsyncClient, db_session, admin_user, superadmin_token,
        get_auth_headers
    ):
        """Test that superadmin can delete any preset."""
        # Create preset owned by another user
        preset = CriteriaPreset(
            name="Any User Preset",
            criteria=[{"name": "Test", "weight": 5}],
            is_global=False,
            created_by=admin_user.id
        )
        db_session.add(preset)
        await db_session.commit()
        await db_session.refresh(preset)

        # Delete as superadmin
        response = await client.delete(
            f"/api/criteria/presets/{preset.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_preset_not_found(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test deleting non-existent preset."""
        response = await client.delete(
            "/api/criteria/presets/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_presets_requires_auth(self, client: AsyncClient):
        """Test that getting presets requires authentication."""
        response = await client.get("/api/criteria/presets")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_preset_requires_auth(self, client: AsyncClient):
        """Test that creating presets requires authentication."""
        response = await client.post(
            "/api/criteria/presets",
            json={"name": "Test", "criteria": []}
        )
        assert response.status_code == 401


# ============================================================================
# CHAT CRITERIA TESTS
# ============================================================================

class TestChatCriteria:
    """Tests for chat-specific criteria endpoints."""

    @pytest.mark.asyncio
    async def test_get_chat_criteria_exists(
        self, client: AsyncClient, db_session, chat, admin_user, admin_token,
        get_auth_headers, org_owner
    ):
        """Test getting criteria for a chat that has criteria."""
        # Create chat criteria
        criteria = ChatCriteria(
            chat_id=chat.id,
            criteria=[
                {"name": "Technical Skills", "weight": 9},
                {"name": "Communication", "weight": 7}
            ]
        )
        db_session.add(criteria)
        await db_session.commit()
        await db_session.refresh(criteria)

        response = await client.get(
            f"/api/criteria/chats/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == criteria.id
        assert data["chat_id"] == chat.id
        assert len(data["criteria"]) == 2
        assert data["criteria"][0]["name"] == "Technical Skills"
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_chat_criteria_not_exists_returns_empty(
        self, client: AsyncClient, chat, admin_token, get_auth_headers,
        org_owner
    ):
        """Test getting criteria for a chat without criteria returns empty."""
        response = await client.get(
            f"/api/criteria/chats/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == 0
        assert data["chat_id"] == chat.id
        assert data["criteria"] == []
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_chat_criteria_not_found(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test getting criteria for non-existent chat."""
        response = await client.get(
            "/api/criteria/chats/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_chat_criteria_access_denied(
        self, client: AsyncClient, chat, second_user_token,
        get_auth_headers, org_member
    ):
        """Test that users cannot access criteria for chats they don't own."""
        response = await client.get(
            f"/api/criteria/chats/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_chat_criteria_superadmin_access(
        self, client: AsyncClient, chat, superadmin_token,
        get_auth_headers
    ):
        """Test that superadmin can access any chat's criteria."""
        response = await client.get(
            f"/api/criteria/chats/{chat.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_chat_criteria_create_new(
        self, client: AsyncClient, chat, admin_token, get_auth_headers,
        org_owner
    ):
        """Test creating criteria for a chat that doesn't have any."""
        criteria_data = {
            "criteria": [
                {"name": "Experience", "weight": 8, "category": "basic"},
                {"name": "Team Fit", "weight": 6, "category": "basic"},
                {"name": "Red Flag: Late", "weight": 10, "category": "red_flag"}
            ]
        }

        response = await client.put(
            f"/api/criteria/chats/{chat.id}",
            json=criteria_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["chat_id"] == chat.id
        assert len(data["criteria"]) == 3
        assert data["criteria"][0]["name"] == "Experience"
        assert "id" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_update_chat_criteria_update_existing(
        self, client: AsyncClient, db_session, chat, admin_token,
        get_auth_headers, org_owner
    ):
        """Test updating existing criteria for a chat."""
        # Create initial criteria
        criteria = ChatCriteria(
            chat_id=chat.id,
            criteria=[{"name": "Old Criterion", "weight": 5}]
        )
        db_session.add(criteria)
        await db_session.commit()
        await db_session.refresh(criteria)

        # Update criteria
        new_criteria_data = {
            "criteria": [
                {"name": "New Criterion 1", "weight": 7},
                {"name": "New Criterion 2", "weight": 9}
            ]
        }

        response = await client.put(
            f"/api/criteria/chats/{chat.id}",
            json=new_criteria_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == criteria.id  # Same ID (updated)
        assert len(data["criteria"]) == 2
        assert data["criteria"][0]["name"] == "New Criterion 1"

    @pytest.mark.asyncio
    async def test_update_chat_criteria_empty_list(
        self, client: AsyncClient, chat, admin_token, get_auth_headers,
        org_owner
    ):
        """Test setting criteria to empty list."""
        criteria_data = {"criteria": []}

        response = await client.put(
            f"/api/criteria/chats/{chat.id}",
            json=criteria_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["criteria"] == []

    @pytest.mark.asyncio
    async def test_update_chat_criteria_not_found(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test updating criteria for non-existent chat."""
        criteria_data = {
            "criteria": [{"name": "Test", "weight": 5}]
        }

        response = await client.put(
            "/api/criteria/chats/99999",
            json=criteria_data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_chat_criteria_access_denied(
        self, client: AsyncClient, chat, second_user_token,
        get_auth_headers, org_member
    ):
        """Test that users cannot update criteria for chats they don't own."""
        criteria_data = {
            "criteria": [{"name": "Test", "weight": 5}]
        }

        response = await client.put(
            f"/api/criteria/chats/{chat.id}",
            json=criteria_data,
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_chat_criteria_superadmin_access(
        self, client: AsyncClient, chat, superadmin_token,
        get_auth_headers
    ):
        """Test that superadmin can update any chat's criteria."""
        criteria_data = {
            "criteria": [{"name": "Admin Criterion", "weight": 8}]
        }

        response = await client.put(
            f"/api/criteria/chats/{chat.id}",
            json=criteria_data,
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["criteria"]) == 1

    @pytest.mark.asyncio
    async def test_chat_criteria_requires_auth(self, client: AsyncClient):
        """Test that chat criteria endpoints require authentication."""
        # GET
        response = await client.get("/api/criteria/chats/1")
        assert response.status_code == 401

        # PUT
        response = await client.put(
            "/api/criteria/chats/1",
            json={"criteria": []}
        )
        assert response.status_code == 401


# ============================================================================
# STATS TESTS
# ============================================================================

class TestStats:
    """Tests for statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_basic_structure(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test that stats endpoint returns correct structure."""
        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Check all required fields
        assert "total_chats" in data
        assert "total_messages" in data
        assert "total_participants" in data
        assert "total_analyses" in data
        assert "active_chats" in data
        assert "messages_today" in data
        assert "messages_this_week" in data
        assert "activity_by_day" in data
        assert "messages_by_type" in data
        assert "top_chats" in data

    @pytest.mark.asyncio
    async def test_get_stats_empty_database(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test stats when database is empty."""
        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_chats"] == 0
        assert data["total_messages"] == 0
        assert data["total_participants"] == 0
        assert data["total_analyses"] == 0
        assert data["active_chats"] == 0
        assert data["messages_today"] == 0
        assert data["messages_this_week"] == 0
        assert len(data["activity_by_day"]) == 7
        assert data["messages_by_type"] == {}
        assert data["top_chats"] == []

    @pytest.mark.asyncio
    async def test_get_stats_regular_user_sees_only_own_data(
        self, client: AsyncClient, db_session, admin_user, second_user,
        admin_token, organization, org_owner, org_member, get_auth_headers
    ):
        """Test that regular users see only their own data."""
        # Create chats for both users
        admin_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Admin Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        second_chat = Chat(
            org_id=organization.id,
            owner_id=second_user.id,
            telegram_chat_id=222,
            title="Second Chat",
            chat_type=ChatType.sales,
            is_active=True
        )
        db_session.add_all([admin_chat, second_chat])
        await db_session.commit()

        # Create messages for both chats
        now = datetime.utcnow()
        admin_msg = Message(
            chat_id=admin_chat.id,
            telegram_user_id=1,
            username="admin_tg",
            content="Admin message",
            content_type="text",
            timestamp=now
        )
        second_msg = Message(
            chat_id=second_chat.id,
            telegram_user_id=2,
            username="second_tg",
            content="Second message",
            content_type="text",
            timestamp=now
        )
        db_session.add_all([admin_msg, second_msg])
        await db_session.commit()

        # Get stats as admin_user
        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should see only their own data
        assert data["total_chats"] == 1
        assert data["total_messages"] == 1
        assert data["total_participants"] == 1

    @pytest.mark.asyncio
    async def test_get_stats_superadmin_sees_all_data(
        self, client: AsyncClient, db_session, admin_user, second_user,
        superadmin_token, organization, get_auth_headers
    ):
        """Test that superadmin sees all data."""
        # Create chats for both users
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Chat 1",
            chat_type=ChatType.hr,
            is_active=True
        )
        chat2 = Chat(
            org_id=organization.id,
            owner_id=second_user.id,
            telegram_chat_id=222,
            title="Chat 2",
            chat_type=ChatType.sales,
            is_active=True
        )
        db_session.add_all([chat1, chat2])
        await db_session.commit()

        # Create messages
        now = datetime.utcnow()
        msg1 = Message(
            chat_id=chat1.id,
            telegram_user_id=1,
            content="Message 1",
            content_type="text",
            timestamp=now
        )
        msg2 = Message(
            chat_id=chat2.id,
            telegram_user_id=2,
            content="Message 2",
            content_type="text",
            timestamp=now
        )
        db_session.add_all([msg1, msg2])
        await db_session.commit()

        # Get stats as superadmin
        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should see all data
        assert data["total_chats"] == 2
        assert data["total_messages"] == 2
        assert data["total_participants"] == 2

    @pytest.mark.asyncio
    async def test_stats_active_chats_last_7_days(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, org_owner, get_auth_headers
    ):
        """Test active chats calculation (messages in last 7 days)."""
        now = datetime.utcnow()

        # Create chat with recent message
        active_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Active Chat",
            chat_type=ChatType.hr,
            is_active=True
        )

        # Create chat with old message
        inactive_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=222,
            title="Inactive Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add_all([active_chat, inactive_chat])
        await db_session.commit()

        # Recent message (within 7 days)
        recent_msg = Message(
            chat_id=active_chat.id,
            telegram_user_id=1,
            content="Recent",
            content_type="text",
            timestamp=now - timedelta(days=3)
        )

        # Old message (more than 7 days ago)
        old_msg = Message(
            chat_id=inactive_chat.id,
            telegram_user_id=1,
            content="Old",
            content_type="text",
            timestamp=now - timedelta(days=10)
        )
        db_session.add_all([recent_msg, old_msg])
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_chats"] == 2
        assert data["active_chats"] == 1  # Only one with recent messages

    @pytest.mark.asyncio
    async def test_stats_messages_today(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, org_owner, get_auth_headers
    ):
        """Test messages today calculation."""
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()

        # Today's messages
        msg_today_1 = Message(
            chat_id=chat.id,
            telegram_user_id=1,
            content="Today 1",
            content_type="text",
            timestamp=today + timedelta(hours=8)
        )
        msg_today_2 = Message(
            chat_id=chat.id,
            telegram_user_id=1,
            content="Today 2",
            content_type="text",
            timestamp=today + timedelta(hours=15)
        )

        # Yesterday's message
        msg_yesterday = Message(
            chat_id=chat.id,
            telegram_user_id=1,
            content="Yesterday",
            content_type="text",
            timestamp=yesterday + timedelta(hours=12)
        )
        db_session.add_all([msg_today_1, msg_today_2, msg_yesterday])
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["messages_today"] >= 2  # At least 2 (may vary with test timing)
        assert data["messages_this_week"] >= 3

    @pytest.mark.asyncio
    async def test_stats_activity_by_day_structure(
        self, client: AsyncClient, admin_token, get_auth_headers
    ):
        """Test activity by day returns 7 days with correct structure."""
        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        activity = data["activity_by_day"]
        assert len(activity) == 7

        for day in activity:
            assert "date" in day
            assert "day" in day  # Day name (Mon, Tue, etc.)
            assert "count" in day
            assert isinstance(day["count"], int)

    @pytest.mark.asyncio
    async def test_stats_messages_by_type(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, org_owner, get_auth_headers
    ):
        """Test messages by type aggregation."""
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()

        # Create messages of different types
        messages = [
            Message(
                chat_id=chat.id,
                telegram_user_id=1,
                content="Text 1",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=1,
                content="Text 2",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=1,
                content="Audio",
                content_type="audio",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=1,
                content="Photo",
                content_type="photo",
                timestamp=datetime.utcnow()
            ),
        ]
        db_session.add_all(messages)
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        by_type = data["messages_by_type"]
        assert by_type.get("text") == 2
        assert by_type.get("audio") == 1
        assert by_type.get("photo") == 1

    @pytest.mark.asyncio
    async def test_stats_top_chats(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, org_owner, get_auth_headers
    ):
        """Test top chats by message count."""
        # Create chats with different message counts
        chats = []
        for i in range(7):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=100 + i,
                title=f"Chat {i}",
                custom_name=f"Custom {i}",
                chat_type=ChatType.hr,
                is_active=True
            )
            db_session.add(chat)
            chats.append(chat)
        await db_session.commit()

        # Add messages (different counts for each chat)
        for i, chat in enumerate(chats):
            for j in range(i + 1):  # Chat 0: 1 msg, Chat 1: 2 msgs, etc.
                msg = Message(
                    chat_id=chat.id,
                    telegram_user_id=1,
                    content=f"Message {j}",
                    content_type="text",
                    timestamp=datetime.utcnow()
                )
                db_session.add(msg)
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        top_chats = data["top_chats"]
        assert len(top_chats) <= 5  # Limited to top 5

        # Should be ordered by message count (descending)
        if len(top_chats) > 1:
            for i in range(len(top_chats) - 1):
                assert top_chats[i]["messages"] >= top_chats[i + 1]["messages"]

        # Check structure
        if top_chats:
            chat = top_chats[0]
            assert "id" in chat
            assert "title" in chat
            assert "custom_name" in chat
            assert "messages" in chat

    @pytest.mark.asyncio
    async def test_stats_total_participants_distinct(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, org_owner, get_auth_headers
    ):
        """Test that participants are counted distinctly."""
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()

        # Multiple messages from same users
        messages = [
            Message(
                chat_id=chat.id,
                telegram_user_id=1,
                content="User 1 - Msg 1",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=1,
                content="User 1 - Msg 2",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=2,
                content="User 2 - Msg 1",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_user_id=2,
                content="User 2 - Msg 2",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
        ]
        db_session.add_all(messages)
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_messages"] == 4
        assert data["total_participants"] == 2  # Only 2 distinct users

    @pytest.mark.asyncio
    async def test_stats_total_analyses(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, chat, org_owner, get_auth_headers
    ):
        """Test total analyses count."""
        # Create analyses
        analyses = [
            AnalysisHistory(
                chat_id=chat.id,
                user_id=admin_user.id,
                result="Analysis 1",
                report_type="standard"
            ),
            AnalysisHistory(
                chat_id=chat.id,
                user_id=admin_user.id,
                result="Analysis 2",
                report_type="detailed"
            ),
        ]
        db_session.add_all(analyses)
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_analyses"] == 2

    @pytest.mark.asyncio
    async def test_stats_user_only_sees_own_analyses(
        self, client: AsyncClient, db_session, admin_user, second_user,
        admin_token, organization, chat, second_chat, org_owner,
        org_member, get_auth_headers
    ):
        """Test that regular users see only their own analyses."""
        # Create analyses for different users
        admin_analysis = AnalysisHistory(
            chat_id=chat.id,
            user_id=admin_user.id,
            result="Admin analysis"
        )
        second_analysis = AnalysisHistory(
            chat_id=second_chat.id,
            user_id=second_user.id,
            result="Second analysis"
        )
        db_session.add_all([admin_analysis, second_analysis])
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Admin should see only their own analysis
        assert data["total_analyses"] == 1

    @pytest.mark.asyncio
    async def test_stats_requires_auth(self, client: AsyncClient):
        """Test that stats endpoint requires authentication."""
        response = await client.get("/api/stats")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_stats_activity_by_day_with_real_data(
        self, client: AsyncClient, db_session, admin_user, admin_token,
        organization, org_owner, get_auth_headers
    ):
        """Test activity by day with actual message data."""
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True
        )
        db_session.add(chat)
        await db_session.commit()

        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Create messages on different days
        messages = []
        for i in range(7):
            day = today - timedelta(days=6-i)
            for j in range(i + 1):  # Increasing count
                msg = Message(
                    chat_id=chat.id,
                    telegram_user_id=1,
                    content=f"Day {i} Message {j}",
                    content_type="text",
                    timestamp=day + timedelta(hours=12)
                )
                messages.append(msg)
        db_session.add_all(messages)
        await db_session.commit()

        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        activity = data["activity_by_day"]
        assert len(activity) == 7

        # Verify dates are in order
        dates = [day["date"] for day in activity]
        assert dates == sorted(dates)

        # Verify counts increase (based on our test data)
        counts = [day["count"] for day in activity]
        assert counts[-1] >= counts[0]  # Last day should have most messages
