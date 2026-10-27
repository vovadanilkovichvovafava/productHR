"""
Tests for Pydantic schemas validation.
"""
import pytest
from pydantic import ValidationError

from api.models.schemas import (
    LoginRequest,
    UserResponse,
    ChatUpdate,
    CriterionItem,
    AnalyzeRequest,
)
from api.routes.entities import EntityCreate, EntityUpdate
from api.routes.organizations import InviteMemberRequest, OrganizationUpdate
from api.routes.departments import DepartmentCreate
from api.routes.sharing import ShareRequest


class TestLoginRequestSchema:
    """Test LoginRequest schema validation."""

    def test_valid_login_request(self):
        """Test valid login request."""
        data = LoginRequest(email="test@test.com", password="password123")
        assert data.email == "test@test.com"
        assert data.password == "password123"

    def test_invalid_email_format(self):
        """Test that invalid email format is rejected."""
        with pytest.raises(ValidationError):
            LoginRequest(email="notanemail", password="password123")

    def test_empty_password(self):
        """Test that empty password is accepted (validation on server)."""
        # Pydantic might accept empty string, validation happens on server
        data = LoginRequest(email="test@test.com", password="")
        assert data.password == ""

    def test_missing_email(self):
        """Test that missing email raises error."""
        with pytest.raises(ValidationError):
            LoginRequest(password="password123")

    def test_missing_password(self):
        """Test that missing password raises error."""
        with pytest.raises(ValidationError):
            LoginRequest(email="test@test.com")


class TestUserResponseSchema:
    """Test UserResponse schema."""

    def test_valid_user_response(self):
        """Test valid user response with all required fields."""
        from datetime import datetime
        data = UserResponse(
            id=1,
            email="test@test.com",
            name="Test User",
            role="member",  # роли «user» в UserRole нет: обычный пользователь — member
            is_active=True,
            telegram_id=None,
            telegram_username=None,
            created_at=datetime.now()
        )
        assert data.id == 1
        assert data.email == "test@test.com"

    def test_telegram_id_large_value(self):
        """Test that large Telegram IDs (> 2^31) work correctly."""
        from datetime import datetime
        large_telegram_id = 5000000000  # 5 billion

        data = UserResponse(
            id=1,
            email="test@test.com",
            name="Test User",
            role="member",  # роли «user» в UserRole нет: обычный пользователь — member
            is_active=True,
            telegram_id=large_telegram_id,
            telegram_username="testuser",
            created_at=datetime.now()
        )

        # Python int can handle this
        assert data.telegram_id == large_telegram_id


class TestEntityCreateSchema:
    """Test EntityCreate schema validation."""

    def test_valid_entity_create(self):
        """Test valid entity creation."""
        data = EntityCreate(
            name="Test Contact",
            type="candidate",
            email="contact@test.com"
        )
        assert data.name == "Test Contact"

    def test_entity_with_all_fields(self):
        """Test entity with all optional fields."""
        data = EntityCreate(
            name="Full Contact",
            type="client",
            email="contact@test.com",
            phone="+1234567890",
            position="Manager",
            company="Test Corp",
            status="active"
        )
        assert data.company == "Test Corp"

    def test_entity_missing_name(self):
        """Test that missing name raises error."""
        with pytest.raises(ValidationError):
            EntityCreate(type="candidate")

    def test_entity_missing_type(self):
        """Test that missing type raises error."""
        with pytest.raises(ValidationError):
            EntityCreate(name="Contact")


class TestEntityUpdateSchema:
    """Test EntityUpdate schema validation."""

    def test_partial_update(self):
        """Test partial entity update."""
        data = EntityUpdate(name="Updated Name")
        assert data.name == "Updated Name"
        assert data.email is None

    def test_empty_update(self):
        """Test empty update (all None)."""
        data = EntityUpdate()
        assert data.name is None


class TestCriterionItemSchema:
    """Test CriterionItem schema validation."""

    def test_valid_criterion(self):
        """Test valid criterion."""
        data = CriterionItem(
            name="Communication",
            description="Communication skills",
            weight=8
        )
        assert data.weight == 8

    def test_default_weight(self):
        """Test default weight value."""
        data = CriterionItem(
            name="Test",
            description="Test criterion"
        )
        assert data.weight == 5  # Default

    def test_weight_out_of_range_low(self):
        """Weight below 1 should raise ValidationError."""
        with pytest.raises(ValidationError):
            CriterionItem(
                name="Test",
                description="Test",
                weight=0  # Below minimum
            )

    def test_weight_out_of_range_high(self):
        """Weight above 10 should raise ValidationError."""
        with pytest.raises(ValidationError):
            CriterionItem(
                name="Test",
                description="Test",
                weight=100  # Above maximum
            )

    def test_negative_weight(self):
        """Negative weight should raise ValidationError."""
        with pytest.raises(ValidationError):
            CriterionItem(
                name="Test",
                description="Test",
                weight=-5
            )


class TestAnalyzeRequestSchema:
    """Test AnalyzeRequest schema validation."""

    def test_valid_analyze_request(self):
        """Test valid analyze request."""
        data = AnalyzeRequest(report_type="detailed")
        assert data.report_type == "detailed"
        assert data.include_quotes is True

    def test_default_report_type(self):
        """Test default report type."""
        data = AnalyzeRequest()
        assert data.report_type == "standard"

    def test_invalid_report_type(self):
        """Invalid report_type should raise ValidationError."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(report_type="invalid_type")


class TestInviteMemberRequestSchema:
    """Test InviteMemberRequest schema validation."""

    def test_valid_invite(self):
        """Test valid invite request with 8+ character password."""
        data = InviteMemberRequest(
            email="new@test.com",
            name="New User",
            password="password123",  # 11 chars, valid
            role="member"
        )
        assert data.email == "new@test.com"

    def test_weak_password_rejected(self):
        """Password less than 8 characters should raise ValidationError."""
        with pytest.raises(ValidationError):
            InviteMemberRequest(
                email="new@test.com",
                name="New User",
                password="123",  # Too short
                role="member"
            )

    def test_empty_password_rejected(self):
        """Empty password should raise ValidationError."""
        with pytest.raises(ValidationError):
            InviteMemberRequest(
                email="new@test.com",
                name="New User",
                password="",  # Empty
                role="member"
            )


class TestOrganizationUpdateSchema:
    """Test OrganizationUpdate schema validation."""

    def test_valid_update(self):
        """Test valid organization update."""
        data = OrganizationUpdate(name="New Org Name")
        assert data.name == "New Org Name"

    def test_empty_name_rejected(self):
        """Empty name should raise ValidationError."""
        with pytest.raises(ValidationError):
            OrganizationUpdate(name="")

    def test_very_long_name_rejected(self):
        """Name longer than 255 characters should raise ValidationError."""
        long_name = "A" * 1000
        with pytest.raises(ValidationError):
            OrganizationUpdate(name=long_name)


class TestDepartmentCreateSchema:
    """Test DepartmentCreate schema validation."""

    def test_valid_department(self):
        """Test valid department creation."""
        data = DepartmentCreate(name="New Department")
        assert data.name == "New Department"

    def test_department_with_parent(self):
        """Test department with parent."""
        data = DepartmentCreate(name="Sub Department", parent_id=1)
        assert data.parent_id == 1

    def test_empty_name_rejected(self):
        """Empty department name should raise ValidationError."""
        with pytest.raises(ValidationError):
            DepartmentCreate(name="")


class TestShareRequestSchema:
    """Test ShareRequest schema validation."""

    def test_valid_share_request(self):
        """Test valid share request."""
        data = ShareRequest(
            resource_type="entity",
            resource_id=1,
            shared_with_id=2,
            access_level="view"
        )
        assert data.access_level == "view"

    def test_all_access_levels(self):
        """Test all valid access levels."""
        for level in ["view", "edit", "full"]:
            data = ShareRequest(
                resource_type="entity",
                resource_id=1,
                shared_with_id=2,
                access_level=level
            )
            assert data.access_level == level

    def test_invalid_access_level(self):
        """Test invalid access level."""
        with pytest.raises(ValidationError):
            ShareRequest(
                resource_type="entity",
                resource_id=1,
                shared_with_id=2,
                access_level="invalid"
            )

    def test_invalid_resource_type(self):
        """Test invalid resource type."""
        with pytest.raises(ValidationError):
            ShareRequest(
                resource_type="invalid",
                resource_id=1,
                shared_with_id=2,
                access_level="view"
            )


class TestChatUpdateSchema:
    """Test ChatUpdate schema validation."""

    def test_partial_update(self):
        """Test partial chat update."""
        data = ChatUpdate(custom_name="New Name")
        assert data.custom_name == "New Name"

    def test_invalid_chat_type_rejected(self):
        """Invalid chat_type should raise ValidationError."""
        with pytest.raises(ValidationError):
            ChatUpdate(chat_type="invalid_type")


class TestEmailValidation:
    """Test email validation across schemas."""

    def test_valid_emails(self):
        """Test various valid email formats."""
        valid_emails = [
            "test@test.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
        ]
        for email in valid_emails:
            data = LoginRequest(email=email, password="password")
            assert data.email == email

    def test_invalid_emails(self):
        """Test invalid email formats."""
        invalid_emails = [
            "notanemail",
            "@nodomain.com",
            "no@",
            "spaces in@email.com",
        ]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                LoginRequest(email=email, password="password")


class TestTypeCoercion:
    """Test type coercion in schemas."""

    def test_string_to_int_coercion(self):
        """Test that string numbers are coerced to int where expected."""
        # EntityCreate might accept string for department_id
        # Test depends on schema configuration

    def test_int_to_string_coercion(self):
        """Test that int is coerced to string where expected."""
        # Some fields might accept both


class TestOptionalFields:
    """Test optional field handling."""

    def test_none_vs_missing(self):
        """Test difference between None and missing field."""
        # EntityUpdate with name=None vs no name field
        data1 = EntityUpdate(name=None)
        data2 = EntityUpdate()

        # Both should have name as None
        assert data1.name is None
        assert data2.name is None

    def test_exclude_unset(self):
        """Test model_dump with exclude_unset."""
        data = EntityUpdate(name="Updated")
        dump = data.model_dump(exclude_unset=True)

        assert "name" in dump
        assert "email" not in dump  # Not set, so excluded
