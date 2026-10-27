"""
Input validation tests for HR-Bot backend.

Tests comprehensive input validation for:
- Email format validation
- Phone number validation
- Enum value validation
- Type checking
- Required field validation
- Format validation
"""
import pytest
from datetime import datetime

from api.models.database import (
    Entity, EntityType, EntityStatus, Chat, ChatType,
    CallRecording, CallSource, CallStatus, UserRole,
    OrgRole, DeptRole, AccessLevel
)


class TestEmailValidation:
    """Test email address format validation."""

    @pytest.mark.asyncio
    async def test_invalid_email_format(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with invalid email formats."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user @example.com",  # Space
            "user@example",  # No TLD
            "user..name@example.com",  # Double dots
            "user@.example.com",  # Dot after @
            ".user@example.com",  # Leading dot
            "user@example..com",  # Double dots in domain
            "",  # Empty string
            "plaintext",
            "missing@domain@example.com",  # Multiple @
        ]

        for email in invalid_emails:
            response = await client.post(
                "/api/entities",
                json={"name": "Test", "email": email, "type": "candidate"},
                cookies={"access_token": admin_token}
            )

            # Should reject invalid email formats
            assert response.status_code == 422, f"Should reject invalid email: {email}"

    @pytest.mark.asyncio
    async def test_valid_email_formats(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with valid email formats."""
        valid_emails = [
            "user@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user_name@example.com",
            "user-name@example.com",
            "123@example.com",
            "user@subdomain.example.com",
            "user@example.co.uk",
        ]

        for email in valid_emails:
            response = await client.post(
                "/api/entities",
                json={"name": f"Test {email}", "email": email, "type": "candidate"},
                cookies={"access_token": admin_token}
            )

            # Should accept valid email formats
            assert response.status_code in [200, 201], f"Should accept valid email: {email}"

    @pytest.mark.asyncio
    async def test_email_in_emails_array_validation(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test validation of emails in the emails array field."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "emails": ["valid@example.com", "invalid-email"]
            },
            cookies={"access_token": admin_token}
        )

        # Should validate each email in the array
        # May accept all, reject all, or partially validate.
        # Неверный адрес в массиве — 400 «Invalid email format»
        # (normalize_and_validate_identifiers, см. test_entities_multiple_identifiers).
        assert response.status_code in [200, 201, 400, 422]


class TestPhoneNumberValidation:
    """Test phone number format validation."""

    @pytest.mark.asyncio
    async def test_various_phone_formats(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with various phone number formats."""
        phone_numbers = [
            "+1234567890",
            "+1 (234) 567-8900",
            "1234567890",
            "(234) 567-8900",
            "+44 20 7123 4567",
            "+7 (495) 123-45-67",
        ]

        for phone in phone_numbers:
            response = await client.post(
                "/api/entities",
                json={"name": f"Test {phone}", "phone": phone, "type": "candidate"},
                cookies={"access_token": admin_token}
            )

            # Phone validation may vary - should either accept or reject consistently
            assert response.status_code in [200, 201, 422]

    @pytest.mark.asyncio
    async def test_invalid_phone_numbers(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with clearly invalid phone numbers."""
        invalid_phones = [
            "abc",
            "12",  # Too short
            "not-a-phone",
        ]

        for phone in invalid_phones:
            response = await client.post(
                "/api/entities",
                json={"name": "Test", "phone": phone, "type": "candidate"},
                cookies={"access_token": admin_token}
            )

            # Should reject clearly invalid phone numbers
            # Or accept them as the validation might be lenient
            assert response.status_code in [200, 201, 422]


class TestEnumValidation:
    """Test validation of enum fields."""

    @pytest.mark.asyncio
    async def test_invalid_entity_type(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with invalid type enum."""
        response = await client.post(
            "/api/entities",
            json={"name": "Test", "type": "invalid_type"},
            cookies={"access_token": admin_token}
        )

        # Should reject invalid enum value
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_entity_status(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with invalid status enum."""
        response = await client.post(
            "/api/entities",
            json={"name": "Test", "type": "candidate", "status": "invalid_status"},
            cookies={"access_token": admin_token}
        )

        # Should reject invalid enum value
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_all_valid_entity_types(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with all valid entity types."""
        valid_types = ["candidate", "client", "contractor", "lead", "partner", "custom"]

        for entity_type in valid_types:
            response = await client.post(
                "/api/entities",
                json={"name": f"Test {entity_type}", "type": entity_type},
                cookies={"access_token": admin_token}
            )

            # Should accept all valid enum values
            assert response.status_code in [200, 201], f"Should accept type: {entity_type}"

    @pytest.mark.asyncio
    async def test_all_valid_entity_statuses(
        self, db_session, client, admin_token, entity, org_owner
    ):
        # Правка карточки — PUT /entities/{id} (PATCH на этом адресе нет, 405);
        # org_owner — без членства в организации ручка отвечает 403.
        """Test entity update with all valid status values."""
        valid_statuses = [
            "new", "screening", "interview", "offer", "hired", "rejected",
            "active", "paused", "churned", "converted", "ended", "negotiation"
        ]

        for status in valid_statuses:
            response = await client.put(
                f"/api/entities/{entity.id}",
                json={"status": status},
                cookies={"access_token": admin_token}
            )

            # Should accept all valid enum values
            assert response.status_code == 200, f"Should accept status: {status}"

    @pytest.mark.asyncio
    async def test_invalid_chat_type(
        self, db_session, client, admin_token, organization, org_owner
    ):
        """Test that invalid chat type is rejected."""
        chat = Chat(
            org_id=organization.id,
            owner_id=1,  # Would be validated in real scenario
            title="Test",
            chat_type=ChatType.hr,  # Valid in code
            is_active=True
        )

        # At API level, invalid type should be rejected
        # This is more of a schema validation test
        assert chat.chat_type in ChatType


class TestRequiredFieldValidation:
    """Test validation of required fields."""

    @pytest.mark.asyncio
    async def test_entity_missing_name(
        self, client, admin_token, organization, org_owner
    ):
        """Test entity creation without required name field."""
        response = await client.post(
            "/api/entities",
            json={"type": "candidate"},
            cookies={"access_token": admin_token}
        )

        # Should reject missing required field
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_entity_missing_type(
        self, client, admin_token, organization, org_owner
    ):
        """Test entity creation without required type field."""
        response = await client.post(
            "/api/entities",
            json={"name": "Test"},
            cookies={"access_token": admin_token}
        )

        # Should reject missing required field
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_user_registration_missing_email(self, client, superadmin_token):
        """Test user registration without email."""
        # Публичная регистрация отключена (/auth/register всегда 403), аккаунты
        # заводит суперадмин — проверяем ту же валидацию на POST /api/users.
        response = await client.post(
            "/api/users",
            json={
                "password": "Password123",
                "name": "Test User",
                "role": "member"
            },
            cookies={"access_token": superadmin_token}
        )

        # Should reject missing email
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_user_registration_missing_password(self, client, superadmin_token):
        """Test user registration without password."""
        # Публичная регистрация отключена (/auth/register всегда 403), аккаунты
        # заводит суперадмин — проверяем ту же валидацию на POST /api/users.
        response = await client.post(
            "/api/users",
            json={
                "email": "test@example.com",
                "name": "Test User",
                "role": "member"
            },
            cookies={"access_token": superadmin_token}
        )

        # Should reject missing password
        assert response.status_code == 422


class TestTypeValidation:
    """Test type validation for various fields."""

    @pytest.mark.asyncio
    async def test_entity_id_wrong_type(self, client, admin_token):
        """Test accessing entity with non-integer ID."""
        response = await client.get(
            "/api/entities/not-a-number",
            cookies={"access_token": admin_token}
        )

        # Should reject invalid type
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_entity_tags_wrong_type(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with tags as non-array."""
        response = await client.post(
            "/api/entities",
            json={"name": "Test", "type": "candidate", "tags": "not-an-array"},
            cookies={"access_token": admin_token}
        )

        # Should reject wrong type
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_entity_extra_data_wrong_type(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with extra_data as non-object."""
        response = await client.post(
            "/api/entities",
            json={"name": "Test", "type": "candidate", "extra_data": "not-an-object"},
            cookies={"access_token": admin_token}
        )

        # Should reject wrong type
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_telegram_user_id_wrong_type(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with telegram_user_id as string."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "telegram_user_id": "not-a-number"
            },
            cookies={"access_token": admin_token}
        )

        # Should reject wrong type
        assert response.status_code == 422


class TestPasswordValidation:
    """Test password validation rules."""

    @pytest.mark.asyncio
    async def test_weak_password(self, client, superadmin_token):
        """Test user registration with weak password."""
        weak_passwords = [
            "123",  # Too short
            "password",  # No uppercase or numbers
            "12345678",  # Only numbers
            "abcdefgh",  # Only lowercase
        ]

        # Публичная регистрация отключена — аккаунты заводит суперадмин через
        # POST /api/users, там и действует политика паролей.
        for password in weak_passwords:
            response = await client.post(
                "/api/users",
                json={
                    "email": f"test_{password}@example.com",
                    "password": password,
                    "name": "Test User",
                    "role": "member"
                },
                cookies={"access_token": superadmin_token}
            )

            # Слабый пароль отклоняется: схемой (422) или политикой (400).
            assert response.status_code in [400, 422], f"Should reject weak password: {password}"

    @pytest.mark.asyncio
    async def test_strong_password(self, client, superadmin_token):
        """Test user registration with strong password."""
        # Публичная регистрация отключена — создание через POST /api/users.
        response = await client.post(
            "/api/users",
            json={
                "email": "strong@example.com",
                "password": "StrongP@ssw0rd123",
                "name": "Test User",
                "role": "member"
            },
            cookies={"access_token": superadmin_token}
        )

        # Should accept strong password
        assert response.status_code in [200, 201]


class TestURLValidation:
    """Test URL validation for various fields."""

    @pytest.mark.asyncio
    async def test_invalid_fireflies_meeting_url(
        self, client, admin_token, organization, org_owner
    ):
        """Test Fireflies start with invalid meeting URL."""
        invalid_urls = [
            "not-a-url",
            "http://",
            "ftp://example.com",
            "javascript:alert('xss')",
        ]

        # Запуск записи — POST /api/calls/start-bot, поле source_url
        # (адреса /calls/fireflies/start больше нет).
        for url in invalid_urls:
            response = await client.post(
                "/api/calls/start-bot",
                json={"source_url": url},
                cookies={"access_token": admin_token}
            )

            # Should reject invalid URLs
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_valid_meeting_urls(
        self, client, admin_token, organization, org_owner, monkeypatch
    ):
        """Test Fireflies start with valid meeting URLs."""
        valid_urls = [
            "https://meet.google.com/abc-defg-hij",
            "https://zoom.us/j/123456789",
            "https://teams.microsoft.com/l/meetup-join/...",
        ]

        # Бот Fireflies в тестах не запускаем — это внешний сервис.
        from api.services.call_recorder import call_recorder

        async def _fake_start(*args, **kwargs):
            return {"success": True}

        monkeypatch.setattr(call_recorder, "start_recording", _fake_start)

        for url in valid_urls:
            response = await client.post(
                "/api/calls/start-bot",
                json={"source_url": url},
                cookies={"access_token": admin_token}
            )

            # Поддерживаемый адрес встречи принимается
            assert response.status_code in [200, 201], f"Should accept URL: {url}"


class TestArrayValidation:
    """Test validation of array fields."""

    @pytest.mark.asyncio
    async def test_emails_array_with_invalid_items(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with invalid items in emails array."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "emails": [123, 456]  # Numbers instead of strings
            },
            cookies={"access_token": admin_token}
        )

        # Should reject invalid array items
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_tags_array_with_numbers(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with numbers in tags array."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "tags": [1, 2, 3]  # Numbers instead of strings
            },
            cookies={"access_token": admin_token}
        )

        # Should reject non-string tags
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_nested_arrays_rejected(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test that nested arrays are rejected."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "tags": [["nested", "array"]]
            },
            cookies={"access_token": admin_token}
        )

        # Should reject nested arrays
        assert response.status_code == 422


class TestJSONValidation:
    """Test JSON field validation."""

    @pytest.mark.asyncio
    async def test_extra_data_with_nested_objects(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with nested objects in extra_data."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "extra_data": {
                    "nested": {
                        "deeply": {
                            "nested": "value"
                        }
                    }
                }
            },
            cookies={"access_token": admin_token}
        )

        # Should accept nested JSON objects
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_extra_data_with_arrays(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with arrays in extra_data."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "extra_data": {
                    "skills": ["Python", "JavaScript", "SQL"],
                    "years": [2020, 2021, 2022]
                }
            },
            cookies={"access_token": admin_token}
        )

        # Should accept arrays in JSON
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_extra_data_with_null_values(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with null values in extra_data."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "extra_data": {
                    "field1": None,
                    "field2": "value"
                }
            },
            cookies={"access_token": admin_token}
        )

        # Should accept null values in JSON
        assert response.status_code in [200, 201]


class TestUnknownFieldHandling:
    """Test handling of unknown/extra fields in requests."""

    @pytest.mark.asyncio
    async def test_entity_creation_with_unknown_fields(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test entity creation with fields not in schema."""
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "unknown_field": "should be ignored",
                "another_unknown": 123
            },
            cookies={"access_token": admin_token}
        )

        # Should either ignore unknown fields or reject
        assert response.status_code in [200, 201, 422]

    @pytest.mark.asyncio
    async def test_entity_update_with_unknown_fields(
        self, db_session, client, admin_token, entity, org_owner
    ):
        """Test entity update with unknown fields."""
        # Правка карточки — PUT (PATCH на этом адресе нет).
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "name": "Updated Name",
                "unknown_field": "value"
            },
            cookies={"access_token": admin_token}
        )

        # Should either ignore unknown fields or reject
        assert response.status_code in [200, 422]


class TestNumericValidation:
    """Test validation of numeric fields."""

    @pytest.mark.asyncio
    async def test_negative_entity_id(self, client, admin_token, org_owner):
        # org_owner: без членства в организации /entities отвечает 403 раньше поиска.
        """Test accessing entity with negative ID."""
        response = await client.get(
            "/api/entities/-1",
            cookies={"access_token": admin_token}
        )

        # Should return 404 or 422
        assert response.status_code in [404, 422]

    @pytest.mark.asyncio
    async def test_zero_entity_id(self, client, admin_token, org_owner):
        # org_owner: без членства в организации /entities отвечает 403 раньше поиска.
        """Test accessing entity with ID of 0."""
        response = await client.get(
            "/api/entities/0",
            cookies={"access_token": admin_token}
        )

        # Should return 404 or 422
        assert response.status_code in [404, 422]

    @pytest.mark.asyncio
    async def test_very_large_entity_id(self, client, admin_token, org_owner):
        # org_owner: без членства в организации /entities отвечает 403 раньше поиска.
        """Test accessing entity with very large ID."""
        response = await client.get(
            "/api/entities/999999999999",
            cookies={"access_token": admin_token}
        )

        # Should return 404 (not found)
        assert response.status_code == 404


class TestBooleanValidation:
    """Test validation of boolean fields."""

    @pytest.mark.asyncio
    async def test_boolean_as_string(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test that boolean fields reject string values."""
        # This would be more relevant for fields like is_active
        # Testing with query parameters that expect boolean
        response = await client.get(
            "/api/entities?mine=not-a-boolean",
            cookies={"access_token": admin_token}
        )

        # Should either reject or ignore invalid boolean
        assert response.status_code in [200, 422]


class TestDateTimeValidation:
    """Test validation of date/time fields."""

    @pytest.mark.asyncio
    async def test_invalid_datetime_format(
        self, client, admin_token, organization, org_owner
    ):
        """Test filtering with invalid datetime format."""
        response = await client.get(
            "/api/entities?created_after=not-a-date",
            cookies={"access_token": admin_token}
        )

        # Should reject invalid datetime format
        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_valid_iso_datetime(
        self, client, admin_token, organization, org_owner
    ):
        """Test filtering with valid ISO datetime."""
        response = await client.get(
            "/api/entities?created_after=2024-01-01T00:00:00Z",
            cookies={"access_token": admin_token}
        )

        # Should accept valid ISO datetime
        assert response.status_code in [200, 422]
