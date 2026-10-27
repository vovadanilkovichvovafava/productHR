from .database import (
    Base, User, Chat, Message, CriteriaPreset,
    ChatCriteria, AIConversation, AnalysisHistory,
    ParseJob, ParseJobStatus,
    TimeOffRequest, TimeOffType, TimeOffStatus,
    Blocker, BlockerStatus,
)
from .schemas import *

# Import new models for Alembic to detect
from .email_templates import EmailTemplate, EmailLog, EmailTemplateType, EmailStatus
from .analytics import HRAnalyticsSnapshot, VacancyMetrics, SnapshotPeriod
from .database import EntityTag, entity_tag_association
