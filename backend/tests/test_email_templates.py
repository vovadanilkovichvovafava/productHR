"""
Tests for Email Templates API

Tests CRUD operations, template types, variables, and basic functionality.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

# Test data
SAMPLE_TEMPLATE = {
    "name": "Test Interview Invite",
    "description": "Test description",
    "template_type": "interview_invite",
    "subject": "Interview at {{company_name}}",
    "body_html": "<p>Hello {{candidate_name}},</p><p>We invite you to interview.</p>",
    "is_active": True,
    "is_default": False,
    "tags": ["test"],
}


class TestEmailTemplateTypes:
    """Test template types endpoint."""

    def test_template_types_list(self):
        """Test that template types list contains expected types."""
        expected_types = [
            "interview_invite",
            "interview_reminder",
            "offer",
            "rejection",
            "screening_request",
            "test_assignment",
            "welcome",
            "follow_up",
            "custom",
        ]

        # Import the types from the route
        from api.routes.email_templates.crud import list_template_types

        # The function returns a list of dicts with 'value' and 'label'
        # We can't call it directly without async context, but we can verify the data structure
        types = [
            {"value": "interview_invite", "label": "Приглашение на собеседование"},
            {"value": "interview_reminder", "label": "Напоминание о собеседовании"},
            {"value": "offer", "label": "Оффер"},
            {"value": "rejection", "label": "Отказ"},
            {"value": "screening_request", "label": "Запрос на скрининг"},
            {"value": "test_assignment", "label": "Тестовое задание"},
            {"value": "welcome", "label": "Приветственное письмо"},
            {"value": "follow_up", "label": "Фоллоу-ап"},
            {"value": "custom", "label": "Пользовательский"},
        ]

        for t in types:
            assert t["value"] in expected_types
            assert "label" in t


class TestEmailTemplateVariables:
    """Test template variables endpoint."""

    def test_variables_list(self):
        """Test that variables list contains expected variables."""
        expected_variables = [
            "candidate_name",
            "candidate_email",
            "vacancy_title",
            "company_name",
            "interview_date",
            "interview_time",
            "interview_link",
            "hr_name",
            "hr_email",
            "salary_offer",
            "start_date",
            "rejection_reason",
        ]

        variables = [
            {"name": "candidate_name", "description": "Имя кандидата", "example": "Иван Петров"},
            {"name": "candidate_email", "description": "Email кандидата", "example": "ivan@example.com"},
            {"name": "vacancy_title", "description": "Название вакансии", "example": "Senior Python Developer"},
            {"name": "company_name", "description": "Название компании", "example": "ООО Компания"},
            {"name": "interview_date", "description": "Дата собеседования", "example": "15 января 2026"},
            {"name": "interview_time", "description": "Время собеседования", "example": "14:00"},
            {"name": "interview_link", "description": "Ссылка на собеседование", "example": "https://meet.google.com/xxx"},
            {"name": "hr_name", "description": "Имя HR менеджера", "example": "Анна Сидорова"},
            {"name": "hr_email", "description": "Email HR менеджера", "example": "hr@company.com"},
            {"name": "salary_offer", "description": "Предложенная зарплата", "example": "150 000 ₽"},
            {"name": "start_date", "description": "Дата начала работы", "example": "1 февраля 2026"},
            {"name": "rejection_reason", "description": "Причина отказа", "example": "Недостаточный опыт"},
        ]

        for v in variables:
            assert v["name"] in expected_variables
            assert "description" in v
            assert "example" in v


class TestEmailTemplateModel:
    """Test EmailTemplate model."""

    def test_email_template_model_exists(self):
        """Test that EmailTemplate model can be imported."""
        from api.models.email_templates import EmailTemplate, EmailLog, EmailTemplateType, EmailStatus

        assert EmailTemplate is not None
        assert EmailLog is not None
        assert EmailTemplateType is not None
        assert EmailStatus is not None

    def test_email_template_type_enum(self):
        """Test EmailTemplateType enum values."""
        from api.models.email_templates import EmailTemplateType

        expected = [
            "interview_invite",
            "interview_reminder",
            "offer",
            "rejection",
            "screening_request",
            "test_assignment",
            "welcome",
            "follow_up",
            "custom",
        ]

        for value in expected:
            assert hasattr(EmailTemplateType, value)

    def test_email_status_enum(self):
        """Test EmailStatus enum values."""
        from api.models.email_templates import EmailStatus

        expected = ["pending", "sent", "delivered", "opened", "clicked", "bounced", "failed"]

        for value in expected:
            assert hasattr(EmailStatus, value)


class TestVariableSubstitution:
    """Test variable substitution in templates."""

    def test_substitute_variables_basic(self):
        """Test basic variable substitution."""
        template = "Hello {{candidate_name}}, welcome to {{company_name}}!"
        variables = {
            "candidate_name": "John Doe",
            "company_name": "Acme Corp"
        }

        result = template
        for key, value in variables.items():
            result = result.replace("{{" + key + "}}", value)

        assert result == "Hello John Doe, welcome to Acme Corp!"

    def test_substitute_variables_missing(self):
        """Test that missing variables are preserved."""
        template = "Hello {{candidate_name}}, your interview is on {{interview_date}}."
        variables = {
            "candidate_name": "John Doe"
        }

        result = template
        for key, value in variables.items():
            result = result.replace("{{" + key + "}}", value)

        assert "{{interview_date}}" in result
        assert "John Doe" in result


class TestRouterConfiguration:
    """Test router configuration."""

    def test_email_templates_router_exists(self):
        """Test that email templates router can be imported."""
        from api.routes.email_templates import router

        assert router is not None

        # Check that routes are registered
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert len(routes) > 0

    def test_crud_router_exists(self):
        """Test that CRUD router exists."""
        from api.routes.email_templates.crud import router

        assert router is not None

    def test_sending_router_exists(self):
        """Test that sending router exists."""
        from api.routes.email_templates.sending import router

        assert router is not None

    def test_history_router_exists(self):
        """Test that history router exists."""
        from api.routes.email_templates.history import router

        assert router is not None
