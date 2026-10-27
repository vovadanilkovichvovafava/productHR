"""
Tests for participants service - role identification and formatting.

This test suite covers:
- identify_participants: Identify participants from chat and messages
- get_role_icon: Get emoji icons for roles
- get_role_label: Get human-readable role labels
- format_participant_list: Format participants for AI context
- format_message_with_role: Format individual messages with role icons
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

import sys
sys.path.insert(0, '/home/user/HR-bot-/backend')

from api.services.participants import (
    identify_participants_from_objects,
    get_role_icon,  # класс TestGetRoleIcon проверяет его, а импорта не было
    get_role_label,
    format_participant_list,
    format_message_with_role
)


class TestIdentifyParticipants:
    """Tests for identify_participants function."""

    def test_identifies_owner_from_chat(self):
        """Should identify chat owner as 'owner' role."""
        # Mock chat with owner
        owner = MagicMock()
        owner.telegram_id = 111111111
        owner.name = "HR Manager"

        chat = MagicMock()
        chat.owner = owner
        chat.entity = None

        msg = MagicMock()
        msg.telegram_user_id = 111111111
        msg.first_name = "HR"
        msg.last_name = "Manager"
        msg.username = "hr_manager"

        messages = [msg]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)

        assert 111111111 in participants
        assert participants[111111111]["role"] == "owner"
        assert participants[111111111]["name"] == "HR Manager"

    def test_identifies_target_entity(self):
        """Should identify chat.entity as 'target' role."""
        # Mock entity
        entity = MagicMock()
        entity.telegram_user_id = 222222222
        entity.name = "Иван Петров"
        entity.type.value = "candidate"
        entity.id = 1

        # Mock chat
        chat = MagicMock()
        chat.owner = None
        chat.entity = entity

        msg = MagicMock()
        msg.telegram_user_id = 222222222
        msg.first_name = "Иван"
        msg.last_name = "Петров"
        msg.username = "ivan_p"

        messages = [msg]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)

        assert 222222222 in participants
        assert participants[222222222]["role"] == "target"
        assert participants[222222222]["name"] == "Иван Петров"
        assert participants[222222222]["entity_type"] == "candidate"

    def test_identifies_unknown_participant(self):
        """Should mark unidentified participant as 'unknown'."""
        chat = MagicMock()
        chat.owner = None
        chat.entity = None

        msg = MagicMock()
        msg.telegram_user_id = 333333333
        msg.first_name = "Unknown"
        msg.last_name = "User"
        msg.username = "unknown"

        messages = [msg]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)

        assert 333333333 in participants
        assert participants[333333333]["role"] == "unknown"
        assert participants[333333333]["name"] == "Unknown User"

    def test_handles_multiple_participants(self):
        """Should identify multiple participants correctly."""
        owner = MagicMock()
        owner.telegram_id = 111111111
        owner.name = "HR Manager"

        entity = MagicMock()
        entity.telegram_user_id = 222222222
        entity.name = "Candidate"
        entity.type.value = "candidate"
        entity.id = 1

        chat = MagicMock()
        chat.owner = owner
        chat.entity = entity

        msg1 = MagicMock()
        msg1.telegram_user_id = 111111111
        msg1.first_name = "HR"
        msg1.last_name = "Manager"
        msg1.username = "hr"

        msg2 = MagicMock()
        msg2.telegram_user_id = 222222222
        msg2.first_name = "Candidate"
        msg2.last_name = ""
        msg2.username = "candidate"

        msg3 = MagicMock()
        msg3.telegram_user_id = 333333333
        msg3.first_name = "Unknown"
        msg3.last_name = ""
        msg3.username = None

        messages = [msg1, msg2, msg3]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)

        assert len(participants) == 3
        assert participants[111111111]["role"] == "owner"
        assert participants[222222222]["role"] == "target"
        assert participants[333333333]["role"] == "unknown"

    def test_handles_message_without_name(self):
        """Should handle messages with no first/last name."""
        chat = MagicMock()
        chat.owner = None
        chat.entity = None

        msg = MagicMock()
        msg.telegram_user_id = 444444444
        msg.first_name = None
        msg.last_name = None
        msg.username = "user123"

        messages = [msg]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)

        assert 444444444 in participants
        # Should fall back to username
        assert participants[444444444]["name"] == "user123"

    def test_handles_message_with_no_username(self):
        """Should handle messages with no username."""
        chat = MagicMock()
        chat.owner = None
        chat.entity = None

        msg = MagicMock()
        msg.telegram_user_id = 555555555
        msg.first_name = None
        msg.last_name = None
        msg.username = None

        messages = [msg]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)

        assert 555555555 in participants
        # Should fall back to UserXXX format
        assert participants[555555555]["name"] == "User555555555"


class TestGetRoleIcon:
    """Tests for get_role_icon function."""

    def test_owner_icon(self):
        """Should return key icon for owner."""
        assert get_role_icon("owner") == "🔑"

    def test_target_icon(self):
        """Should return person icon for target."""
        assert get_role_icon("target") == "👤"

    def test_employee_icon(self):
        """Should return building icon for employee."""
        assert get_role_icon("employee") == "🏢"

    def test_unknown_icon(self):
        """Should return question mark for unknown."""
        assert get_role_icon("unknown") == "❓"

    def test_invalid_role_returns_unknown(self):
        """Should return unknown icon for invalid role."""
        assert get_role_icon("invalid_role") == "❓"


class TestGetRoleLabel:
    """Tests for get_role_label function."""

    def test_owner_label(self):
        """Should return 'HR Manager' for owner."""
        assert get_role_label("owner") == "HR Manager"

    def test_target_candidate_label(self):
        """Should return 'кандидат' for target with type=candidate."""
        assert get_role_label("target", "candidate") == "кандидат"

    def test_target_client_label(self):
        """Should return 'клиент' for target with type=client."""
        assert get_role_label("target", "client") == "клиент"

    def test_target_contractor_label(self):
        """Should return 'подрядчик' for target with type=contractor."""
        assert get_role_label("target", "contractor") == "подрядчик"

    def test_target_without_type(self):
        """Should return 'контакт' for target without entity_type."""
        assert get_role_label("target", None) == "контакт"

    def test_employee_label(self):
        """Should return 'сотрудник' for employee."""
        assert get_role_label("employee") == "сотрудник"

    def test_unknown_label(self):
        """Should return 'неизвестный' for unknown."""
        assert get_role_label("unknown") == "неизвестный"


class TestFormatParticipantList:
    """Tests for format_participant_list function."""

    def test_formats_single_participant(self):
        """Should format single participant correctly."""
        participants = {
            111111111: {
                "name": "HR Manager",
                "role": "owner",
                "entity_type": None,
                "entity_id": None
            }
        }

        result = format_participant_list(participants)

        assert "## Участники чата:" in result
        assert "🔑 HR Manager (HR Manager)" in result

    def test_formats_multiple_participants(self):
        """Should format multiple participants correctly."""
        participants = {
            111111111: {
                "name": "HR Manager",
                "role": "owner",
                "entity_type": None,
                "entity_id": None
            },
            222222222: {
                "name": "Иван Петров",
                "role": "target",
                "entity_type": "candidate",
                "entity_id": 1
            },
            333333333: {
                "name": "Unknown User",
                "role": "unknown",
                "entity_type": None,
                "entity_id": None
            }
        }

        result = format_participant_list(participants)

        assert "## Участники чата:" in result
        assert "🔑 HR Manager (HR Manager)" in result
        assert "👤 Иван Петров (кандидат)" in result
        assert "❓ Unknown User (неизвестный)" in result

    def test_empty_participants(self):
        """Should handle empty participants dict."""
        participants = {}
        result = format_participant_list(participants)

        assert "## Участники чата:" in result


class TestFormatMessageWithRole:
    """Tests for format_message_with_role function."""

    def test_formats_message_with_known_role(self):
        """Should format message with role icon for known participant."""
        msg = MagicMock()
        msg.telegram_user_id = 111111111
        msg.first_name = "HR"
        msg.last_name = "Manager"
        msg.username = "hr"
        msg.timestamp = datetime(2024, 1, 15, 10, 30)
        msg.content = "Hello!"

        participants = {
            111111111: {
                "name": "HR Manager",
                "role": "owner",
                "entity_type": None,
                "entity_id": None
            }
        }

        result = format_message_with_role(msg, participants)

        assert "[15.01 10:30] 🔑 HR Manager: Hello!" == result

    def test_formats_message_with_unknown_role(self):
        """Should format message with question mark for unknown participant."""
        msg = MagicMock()
        msg.telegram_user_id = 999999999
        msg.first_name = "Unknown"
        msg.last_name = "User"
        msg.username = "unknown"
        msg.timestamp = datetime(2024, 1, 15, 10, 30)
        msg.content = "Hi!"

        participants = {}

        result = format_message_with_role(msg, participants)

        assert "[15.01 10:30] ❓ Unknown User: Hi!" == result

    def test_formats_message_without_content(self):
        """Should handle message without text content."""
        msg = MagicMock()
        msg.telegram_user_id = 111111111
        msg.first_name = "User"
        msg.last_name = ""
        msg.username = None
        msg.timestamp = datetime(2024, 1, 15, 10, 30)
        msg.content = None

        participants = {}

        result = format_message_with_role(msg, participants)

        assert "[медиа]" in result


class TestIntegrationWithFormatMessagesOptimized:
    """Integration tests with format_messages_optimized from cache.py."""

    def test_format_messages_with_participants(self):
        """Should format messages with participant roles when participants provided."""
        from api.services.cache import format_messages_optimized

        owner = MagicMock()
        owner.telegram_id = 111111111
        owner.name = "HR Manager"

        entity = MagicMock()
        entity.telegram_user_id = 222222222
        entity.name = "Candidate"
        entity.type.value = "candidate"
        entity.id = 1

        chat = MagicMock()
        chat.owner = owner
        chat.entity = entity

        msg1 = MagicMock()
        msg1.telegram_user_id = 111111111
        msg1.first_name = "HR"
        msg1.last_name = "Manager"
        msg1.username = "hr"
        msg1.content = "Hello"
        msg1.content_type = "text"
        msg1.timestamp = datetime(2024, 1, 15, 10, 0)

        msg2 = MagicMock()
        msg2.telegram_user_id = 222222222
        msg2.first_name = "Candidate"
        msg2.last_name = ""
        msg2.username = "cand"
        msg2.content = "Hi!"
        msg2.content_type = "text"
        msg2.timestamp = datetime(2024, 1, 15, 10, 1)

        messages = [msg1, msg2]

        participants = identify_participants_from_objects(chat, messages, use_ai_fallback=False)
        result = format_messages_optimized(messages, max_per_message=500, participants=participants)

        assert "🔑 HR Manager" in result
        assert "👤 Candidate" in result

    def test_format_messages_without_participants(self):
        """Should format messages without roles when participants not provided."""
        from api.services.cache import format_messages_optimized

        msg = MagicMock()
        msg.telegram_user_id = 111111111
        msg.first_name = "John"
        msg.last_name = "Doe"
        msg.username = "john"
        msg.content = "Hello"
        msg.content_type = "text"
        msg.timestamp = datetime(2024, 1, 15, 10, 0)

        messages = [msg]

        result = format_messages_optimized(messages, max_per_message=500, participants=None)

        # Should not have role icon
        assert "🔑" not in result
        assert "👤" not in result
        assert "John Doe" in result
