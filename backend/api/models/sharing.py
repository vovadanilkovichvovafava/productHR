"""Common sharing schemas used across the application.

This module provides base Pydantic schemas for sharing resources (chats, calls, entities)
between users, eliminating duplication across route files.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from .database import AccessLevel, ResourceType


class BaseShareRequest(BaseModel):
    """Base schema for sharing a resource with another user.

    Used by: calls, chats, entities endpoints for single-resource sharing.
    """
    shared_with_id: int
    access_level: AccessLevel = AccessLevel.view
    note: Optional[str] = None
    expires_at: Optional[datetime] = None


class ShareRequestWithRelated(BaseShareRequest):
    """Share request with option to auto-share related resources.

    Used by: entities endpoint where sharing can cascade to linked chats/calls.
    """
    auto_share_related: bool = True  # Auto-share related chats and calls


class GenericShareRequest(ShareRequestWithRelated):
    """Full share request for the generic sharing endpoint.

    Used by: /sharing endpoint which can share any resource type.
    """
    resource_type: ResourceType
    resource_id: int


class ShareResponse(BaseModel):
    """Response schema for share operations."""
    id: int
    resource_type: ResourceType
    resource_id: int
    resource_name: Optional[str] = None
    shared_by_id: int
    shared_by_name: str
    shared_with_id: int
    shared_with_name: str
    access_level: AccessLevel
    note: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateShareRequest(BaseModel):
    """Schema for updating an existing share."""
    access_level: AccessLevel
    note: Optional[str] = None
    expires_at: Optional[datetime] = None


class UserSimple(BaseModel):
    """Simple user representation for sharing UI."""
    id: int
    name: str
    email: str
    org_role: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    department_role: Optional[str] = None

    class Config:
        from_attributes = True
