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
    NotificationType,
    PeriodType,
    Tier,
    WebhookEventStatus,
    WorkspaceStatus,
)
from app.models.imports import ImportJob
from app.models.inbound import LeadgenSubmission, WebhookEvent
from app.models.lead import Contact, Lead, LeadEvent, LeadPhone, Message
from app.models.member import Team, WorkspaceMember
from app.models.meta import AdAccount, BusinessManager, Page, PageAssignment, SyncRun
from app.models.notify import Notification, PushSubscription
from app.models.score import ScoreFormula, ScoreSnapshot
from app.models.session import AuthSession
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceSettings

__all__ = [
    "AdAccount",
    "AuditLog",
    "AuthSession",
    "Base",
    "BusinessManager",
    "ConnectionStatus",
    "Contact",
    "ImportJob",
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
    "Notification",
    "NotificationType",
    "Page",
    "PageAssignment",
    "PeriodType",
    "PushSubscription",
    "ScoreFormula",
    "ScoreSnapshot",
    "SyncRun",
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
