"""ABAC (Attribute-Based Access Control) models"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SQLEnum,
    ForeignKey, Index, Integer, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum

from .database import Base


class PolicyEffect(str, enum.Enum):
    """Effect of a policy when matched"""
    allow = "allow"
    deny = "deny"


class AttributeType(str, enum.Enum):
    """Type of attribute in policy condition"""
    subject = "subject"      # User attributes
    resource = "resource"    # Resource attributes
    action = "action"        # Action being performed
    environment = "environment"  # Context (time, IP, etc.)


class ConditionOperator(str, enum.Enum):
    """Operators for condition evaluation"""
    eq = "eq"                # Equal
    neq = "neq"              # Not equal
    in_ = "in"               # In list
    not_in = "not_in"        # Not in list
    gt = "gt"                # Greater than
    lt = "lt"                # Less than
    gte = "gte"              # Greater than or equal
    lte = "lte"              # Less than or equal
    contains = "contains"    # Contains (for strings/lists)
    not_contains = "not_contains"  # Does not contain
    is_null = "is_null"      # Is null/None
    is_not_null = "is_not_null"  # Is not null


class AccessDecision(str, enum.Enum):
    """Result of access check"""
    allow = "allow"
    deny = "deny"


class ABACResourceType(str, enum.Enum):
    """Resource types for ABAC"""
    entity = "entity"
    chat = "chat"
    call = "call"
    department = "department"
    organization = "organization"
    user = "user"


class ABACPolicy(Base):
    """Access control policy"""
    __tablename__ = "abac_policies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    effect = Column(SQLEnum(PolicyEffect), nullable=False, default=PolicyEffect.allow)
    priority = Column(Integer, nullable=False, default=0)  # Higher = evaluated first
    resource_type = Column(SQLEnum(ABACResourceType), nullable=True)  # NULL = applies to all
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)  # NULL = global
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_abac_policies_resource_type', 'resource_type'),
        Index('ix_abac_policies_org_id', 'org_id'),
        Index('ix_abac_policies_priority', 'priority', 'id'),
    )

    # Relationships
    organization = relationship("Organization")
    conditions = relationship("ABACPolicyCondition", back_populates="policy", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching/serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "effect": self.effect.value if self.effect else None,
            "priority": self.priority,
            "resource_type": self.resource_type.value if self.resource_type else None,
            "org_id": self.org_id,
            "is_active": self.is_active,
            "conditions": [c.to_dict() for c in self.conditions] if self.conditions else []
        }


class ABACPolicyCondition(Base):
    """Condition that must be met for policy to apply"""
    __tablename__ = "abac_policy_conditions"

    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("abac_policies.id", ondelete="CASCADE"), nullable=False)
    attribute_type = Column(SQLEnum(AttributeType), nullable=False)
    attribute_name = Column(String(255), nullable=False)
    operator = Column(SQLEnum(ConditionOperator), nullable=False)
    value = Column(JSONB, nullable=False)  # Can be any JSON value
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('ix_abac_policy_conditions_policy_id', 'policy_id'),
    )

    # Relationships
    policy = relationship("ABACPolicy", back_populates="conditions")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "attribute_type": self.attribute_type.value,
            "attribute_name": self.attribute_name,
            "operator": self.operator.value,
            "value": self.value
        }


class ABACResourceAttribute(Base):
    """Custom attributes for resources (beyond standard model fields)"""
    __tablename__ = "abac_resource_attributes"

    id = Column(Integer, primary_key=True)
    resource_type = Column(SQLEnum(ABACResourceType), nullable=False)
    resource_id = Column(Integer, nullable=False)
    attribute_name = Column(String(255), nullable=False)
    attribute_value = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_abac_resource_attrs_lookup', 'resource_type', 'resource_id'),
    )


class ABACAccessLog(Base):
    """Audit log for access decisions"""
    __tablename__ = "abac_audit_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(50), nullable=False)  # read, write, delete, share
    resource_type = Column(SQLEnum(ABACResourceType), nullable=False)
    resource_id = Column(Integer, nullable=False)
    decision = Column(SQLEnum(AccessDecision), nullable=False)
    policy_id = Column(Integer, ForeignKey("abac_policies.id", ondelete="SET NULL"), nullable=True)
    context = Column(JSONB, nullable=True)  # Full context for debugging
    processing_time_ms = Column(Integer, nullable=True)  # Performance tracking
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('ix_abac_audit_log_user', 'user_id', 'created_at'),
        Index('ix_abac_audit_log_resource', 'resource_type', 'resource_id'),
        Index('ix_abac_audit_log_created', 'created_at'),
    )

    # Relationships
    user = relationship("User")
    policy = relationship("ABACPolicy")
