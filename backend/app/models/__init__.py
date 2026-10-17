"""Import mọi model để Alembic và test thấy đủ metadata."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.enums import (
    ConnectionStatus,
    LeadEventType,
    LeadgenFetchStatus,
    LeadSource,
    LeadStatus,
    LostReason,
    MemberRole,
    MemberStatus,
    MessageDirection,
    PeriodType,
    Tier,
    WebhookEventStatus,
    WorkspaceStatus,
)
from app.models.inbound import LeadgenSubmission, WebhookEvent
from app.models.lead import Contact, Lead, LeadEvent, LeadPhone, Message
from app.models.member import Team, WorkspaceMember
from app.models.meta import BusinessManager, Page, PageAssignment
from app.models.score import ScoreFormula, ScoreSnapshot
from app.models.session import AuthSession
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceSettings

__all__ = [
    "AuditLog",
    "AuthSession",
    "Base",
    "BusinessManager",
    "ConnectionStatus",
    "Contact",
    "Lead",
    "LeadEvent",
    "LeadEventType",
    "LeadPhone",
    "LeadSource",
    "LeadStatus",
    "LeadgenFetchStatus",
    "LeadgenSubmission",
    "LostReason",
    "MemberRole",
    "MemberStatus",
    "Message",
    "MessageDirection",
    "Page",
    "PageAssignment",
    "PeriodType",
    "ScoreFormula",
    "ScoreSnapshot",
    "Team",
    "Tier",
    "User",
    "WebhookEvent",
    "WebhookEventStatus",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceSettings",
    "WorkspaceStatus",
]
