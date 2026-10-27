"""
Email Templates Models

Provides models for email template management:
- EmailTemplate: Template definitions with placeholders
- EmailLog: History of sent emails
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SQLEnum,
    ForeignKey, Index, Integer, String, Text, JSON, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


class EmailTemplateType(str, enum.Enum):
    """Type of email template"""
    interview_invite = "interview_invite"      # Приглашение на собеседование
    interview_reminder = "interview_reminder"  # Напоминание о собеседовании
    offer = "offer"                            # Оффер
    rejection = "rejection"                    # Отказ
    screening_request = "screening_request"    # Запрос на скрининг
    test_assignment = "test_assignment"        # Тестовое задание
    welcome = "welcome"                        # Приветственное письмо
    follow_up = "follow_up"                    # Фоллоу-ап
    custom = "custom"                          # Пользовательский


class EmailStatus(str, enum.Enum):
    """Status of sent email"""
    pending = "pending"      # В очереди
    sent = "sent"            # Отправлено
    delivered = "delivered"  # Доставлено
    opened = "opened"        # Открыто
    clicked = "clicked"      # Кликнули по ссылке
    bounced = "bounced"      # Отклонено
    failed = "failed"        # Ошибка


class EmailTemplate(Base):
    """Email template with placeholders for personalization.

    Available placeholders:
    - {{candidate_name}} - Имя кандидата
    - {{candidate_email}} - Email кандидата
    - {{vacancy_title}} - Название вакансии
    - {{company_name}} - Название компании
    - {{interview_date}} - Дата собеседования
    - {{interview_time}} - Время собеседования
    - {{interview_link}} - Ссылка на собеседование
    - {{hr_name}} - Имя HR менеджера
    - {{hr_email}} - Email HR менеджера
    - {{salary_offer}} - Предложенная зарплата
    - {{start_date}} - Дата начала работы
    - {{rejection_reason}} - Причина отказа
    - {{custom_field}} - Любое кастомное поле
    """
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Template info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    template_type = Column(SQLEnum(EmailTemplateType), default=EmailTemplateType.custom, index=True)

    # Email content
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)  # HTML version
    body_text = Column(Text, nullable=True)   # Plain text fallback

    # Settings
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default template for this type

    # Metadata
    variables = Column(JSON, default=list)  # List of variable names used in template
    tags = Column(JSON, default=list)

    # Audit
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Only one default template per type per org
        Index('ix_email_template_org_type', 'org_id', 'template_type'),
        UniqueConstraint('org_id', 'name', name='uq_email_template_name'),
    )

    # Relationships
    organization = relationship("Organization")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    email_logs = relationship("EmailLog", back_populates="template", cascade="all, delete-orphan")


class EmailLog(Base):
    """Log of sent emails for tracking and analytics.

    Stores complete email history including:
    - Template used
    - Recipient (candidate)
    - Vacancy context
    - Rendered content (for audit)
    - Delivery status
    """
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Template reference
    template_id = Column(Integer, ForeignKey("email_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    template_name = Column(String(255), nullable=True)  # Snapshot of template name
    template_type = Column(SQLEnum(EmailTemplateType), nullable=True)

    # Recipient
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    recipient_email = Column(String(255), nullable=False)
    recipient_name = Column(String(255), nullable=True)

    # Context
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="SET NULL"), nullable=True, index=True)
    application_id = Column(Integer, ForeignKey("vacancy_applications.id", ondelete="SET NULL"), nullable=True)

    # Email content (rendered)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=True)  # Rendered HTML (for audit)

    # Variables used for rendering
    variables_used = Column(JSON, default=dict)

    # Delivery info
    status = Column(SQLEnum(EmailStatus), default=EmailStatus.pending, index=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # External tracking
    message_id = Column(String(255), nullable=True)  # From email provider

    # Audit
    sent_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        # For listing emails by candidate
        Index('ix_email_log_entity', 'entity_id', 'created_at'),
        # For listing emails by vacancy
        Index('ix_email_log_vacancy', 'vacancy_id', 'created_at'),
        # For analytics
        Index('ix_email_log_status_date', 'org_id', 'status', 'created_at'),
    )

    # Relationships
    organization = relationship("Organization")
    template = relationship("EmailTemplate", back_populates="email_logs")
    entity = relationship("Entity")
    vacancy = relationship("Vacancy")
    application = relationship("VacancyApplication")
    sender = relationship("User", foreign_keys=[sent_by])
