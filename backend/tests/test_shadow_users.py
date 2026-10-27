"""
Tests for Shadow Users System

Tests cover:
- Shadow user CRUD operations
- Content isolation between main superadmin and shadow users
- Shadow users hidden from user listings
- Shadow users cannot impersonate
- Permission service correctly filters content
"""

import pytest
from datetime import datetime


class TestShadowUserModels:
    """Test shadow user model fields."""

    def test_user_model_has_shadow_fields(self):
        """Test that User model has is_shadow and shadow_owner_id fields."""
        from api.models.database import User

        # Check that the model has the new fields
        assert hasattr(User, 'is_shadow')
        assert hasattr(User, 'shadow_owner_id')

    def test_user_role_superadmin_exists(self):
        """Test that UserRole.superadmin exists."""
        from api.models.database import UserRole

        assert hasattr(UserRole, 'superadmin')
        assert UserRole.superadmin.value == 'superadmin'


class TestShadowUserRoutes:
    """Test shadow user API routes."""

    def test_shadow_users_router_exists(self):
        """Test that shadow users router can be imported."""
        from api.routes.admin.shadow_users import router

        assert router is not None

        # Check that routes are registered
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert len(routes) > 0

    def test_shadow_users_router_in_admin(self):
        """Test that shadow users router is included in admin router."""
        from api.routes.admin import router

        # Check that shadow-users prefix exists in routes
        route_paths = []
        for route in router.routes:
            if hasattr(route, 'path'):
                route_paths.append(route.path)
            elif hasattr(route, 'routes'):
                for sub_route in route.routes:
                    if hasattr(sub_route, 'path'):
                        route_paths.append(sub_route.path)

        # At least one route should contain shadow-users
        assert any('shadow' in path.lower() for path in route_paths)


class TestShadowUserSchemas:
    """Test shadow user Pydantic schemas."""

    def test_shadow_user_create_schema(self):
        """Test ShadowUserCreate schema validation."""
        from api.routes.admin.shadow_users import ShadowUserCreate

        # Valid data
        user = ShadowUserCreate(
            email="shadow@test.com",
            password="SecurePassword123!",
            name="Shadow User"
        )
        assert user.email == "shadow@test.com"
        assert user.name == "Shadow User"

    def test_shadow_user_create_password_validation(self):
        """Test that password must be at least 12 characters."""
        from api.routes.admin.shadow_users import ShadowUserCreate
        from pydantic import ValidationError

        # Password too short
        with pytest.raises(ValidationError):
            ShadowUserCreate(
                email="shadow@test.com",
                password="short",  # Less than 12 chars
                name="Shadow User"
            )

    def test_shadow_user_response_schema(self):
        """Test ShadowUserResponse schema."""
        from api.routes.admin.shadow_users import ShadowUserResponse

        response = ShadowUserResponse(
            id=1,
            email="shadow@test.com",
            name="Shadow User",
            is_active=True,
            created_at=datetime.utcnow()
        )
        assert response.id == 1
        assert response.email == "shadow@test.com"


class TestShadowFilterService:
    """Test shadow filter service functions."""

    def test_shadow_filter_module_exists(self):
        """Test that shadow filter module can be imported."""
        from api.services.shadow_filter import get_isolated_creator_ids, is_content_visible_to_user

        assert get_isolated_creator_ids is not None
        assert is_content_visible_to_user is not None

    def test_is_content_visible_non_superadmin_creator(self):
        """Test that non-superadmin content is always visible."""
        from api.services.shadow_filter import is_content_visible_to_user
        from api.models.database import User, UserRole

        # Create mock user
        user = User()
        user.id = 1
        user.role = UserRole.superadmin
        user.is_shadow = False

        # Non-superadmin creator content should be visible
        visible = is_content_visible_to_user(
            user=user,
            creator_id=2,
            creator_is_superadmin=False,
            creator_is_shadow=False
        )
        assert visible is True

    def test_is_content_visible_main_viewing_shadow(self):
        """Test that main superadmin cannot see shadow user content."""
        from api.services.shadow_filter import is_content_visible_to_user
        from api.models.database import User, UserRole

        # Main superadmin
        main_admin = User()
        main_admin.id = 1
        main_admin.role = UserRole.superadmin
        main_admin.is_shadow = False

        # Shadow user's content should be hidden from main
        visible = is_content_visible_to_user(
            user=main_admin,
            creator_id=2,
            creator_is_superadmin=True,
            creator_is_shadow=True
        )
        assert visible is False

    def test_is_content_visible_shadow_viewing_main(self):
        """Test that shadow user cannot see main superadmin content."""
        from api.services.shadow_filter import is_content_visible_to_user
        from api.models.database import User, UserRole

        # Shadow superadmin
        shadow_admin = User()
        shadow_admin.id = 2
        shadow_admin.role = UserRole.superadmin
        shadow_admin.is_shadow = True

        # Main superadmin's content should be hidden from shadow
        visible = is_content_visible_to_user(
            user=shadow_admin,
            creator_id=1,
            creator_is_superadmin=True,
            creator_is_shadow=False
        )
        assert visible is False

    def test_is_content_visible_shadow_viewing_other_shadow(self):
        """Test that shadow user cannot see other shadow user content."""
        from api.services.shadow_filter import is_content_visible_to_user
        from api.models.database import User, UserRole

        # Shadow superadmin 1
        shadow_admin = User()
        shadow_admin.id = 2
        shadow_admin.role = UserRole.superadmin
        shadow_admin.is_shadow = True

        # Other shadow's content should be hidden
        visible = is_content_visible_to_user(
            user=shadow_admin,
            creator_id=3,  # Different shadow user
            creator_is_superadmin=True,
            creator_is_shadow=True
        )
        assert visible is False

    def test_is_content_visible_shadow_viewing_own(self):
        """Test that shadow user can see their own content."""
        from api.services.shadow_filter import is_content_visible_to_user
        from api.models.database import User, UserRole

        # Shadow superadmin
        shadow_admin = User()
        shadow_admin.id = 2
        shadow_admin.role = UserRole.superadmin
        shadow_admin.is_shadow = True

        # Own content should be visible
        visible = is_content_visible_to_user(
            user=shadow_admin,
            creator_id=2,  # Same user
            creator_is_superadmin=True,
            creator_is_shadow=True
        )
        assert visible is True


class TestPermissionServiceShadowIntegration:
    """Test PermissionService shadow user integration."""

    def test_permission_service_has_shadow_methods(self):
        """Test that PermissionService has shadow-related methods."""
        from api.services.permissions import PermissionService

        # Check that the class has the new methods
        assert hasattr(PermissionService, '_is_main_superadmin')
        assert hasattr(PermissionService, '_is_shadow_superadmin')
        assert hasattr(PermissionService, '_is_content_isolated_from_user')
        assert hasattr(PermissionService, '_get_isolated_user_ids')


class TestAuthServiceShadowIntegration:
    """Test auth service shadow user integration."""

    def test_get_main_superadmin_dependency_exists(self):
        """Test that get_main_superadmin dependency exists."""
        from api.services.auth import get_main_superadmin

        assert get_main_superadmin is not None


class TestMigration:
    """Test migration file."""

    def test_migration_file_exists(self):
        """Test that shadow users migration file exists."""
        import os
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "add_shadow_users.py"
        assert migration_path.exists()

    def test_migration_has_correct_revision(self):
        """Test that migration has correct revision ID."""
        # Папка backend/alembic — не пакет: «import alembic» берёт установленную
        # библиотеку alembic, где versions нет. Грузим файл миграции по пути.
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parent.parent / "alembic" / "versions" / "add_shadow_users.py"
        spec = importlib.util.spec_from_file_location("add_shadow_users", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        revision, down_revision = module.revision, module.down_revision

        assert revision == 'add_shadow_users'
        assert down_revision == 'add_embeddings'
