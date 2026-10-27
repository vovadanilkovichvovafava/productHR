"""
Shadow User Content Filtering Service

Provides utilities for filtering content based on shadow user isolation rules.

Content isolation rules:
- Main superadmin cannot see content created by shadow users
- Shadow users cannot see content created by main superadmin
- Shadow users cannot see content created by other shadow users
- All superadmins can see content created by regular users
"""

from typing import Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.database import User, UserRole


async def get_isolated_creator_ids(user: User, db: AsyncSession) -> Set[int]:
    """Get user IDs whose content should be hidden from the given user.

    Use this to filter resources by created_by/owner_id field.

    Args:
        user: Current user
        db: Database session

    Returns:
        Set of user IDs whose content should be filtered out.
        Empty set if no filtering needed.
    """
    # Only superadmins need content isolation
    if user.role != UserRole.superadmin:
        return set()

    is_shadow = getattr(user, 'is_shadow', False)

    if not is_shadow:
        # Main superadmin: hide all shadow users' content
        result = await db.execute(
            select(User.id).where(
                User.role == UserRole.superadmin,
                User.is_shadow == True
            )
        )
        return set(result.scalars().all())
    else:
        # Shadow user: hide main superadmin's + other shadows' content
        result = await db.execute(
            select(User.id).where(
                User.role == UserRole.superadmin,
                User.id != user.id  # Exclude self
            )
        )
        return set(result.scalars().all())


def is_content_visible_to_user(
    user: User,
    creator_id: Optional[int],
    creator_is_superadmin: bool,
    creator_is_shadow: bool
) -> bool:
    """Check if content created by creator should be visible to user.

    Args:
        user: Current user viewing content
        creator_id: ID of the content creator
        creator_is_superadmin: Whether creator has superadmin role
        creator_is_shadow: Whether creator is a shadow user

    Returns:
        True if content should be visible
    """
    # Non-superadmin content is always visible to superadmins
    if not creator_is_superadmin:
        return True

    # User is not superadmin - let normal permissions handle it
    if user.role != UserRole.superadmin:
        return True

    user_is_shadow = getattr(user, 'is_shadow', False)

    # Main superadmin viewing shadow's content - hidden
    if not user_is_shadow and creator_is_shadow:
        return False

    # Shadow viewing main superadmin's content - hidden
    if user_is_shadow and creator_is_superadmin and not creator_is_shadow:
        return False

    # Shadow viewing another shadow's content - hidden
    if user_is_shadow and creator_is_shadow and creator_id != user.id:
        return False

    return True
