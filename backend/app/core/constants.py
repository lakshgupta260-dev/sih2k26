"""Domain enumerations shared across models, schemas and services.

These are the canonical values. SQLAlchemy columns and Pydantic schemas both
reference these members so a value can never drift between the two layers.
"""
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Exactly the three roles the platform recognises."""

    ADMIN = "ADMIN"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    SITE_SUPERVISOR = "SITE_SUPERVISOR"


class ProjectStatus(StrEnum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class JobStatus(StrEnum):
    """Lifecycle of an asynchronous processing job."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ActivityStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"


class MatchStatus(StrEnum):
    """Outcome of linking an extracted field item to a schedule activity."""

    AUTO_MATCHED = "AUTO_MATCHED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNMATCHED = "UNMATCHED"
    MANUALLY_CONFIRMED = "MANUALLY_CONFIRMED"
    MANUALLY_REJECTED = "MANUALLY_REJECTED"


class MatchMethod(StrEnum):
    EXACT_ID = "EXACT_ID"
    EXACT_CODE = "EXACT_CODE"
    KEYWORD = "KEYWORD"
    FUZZY = "FUZZY"
    SEMANTIC = "SEMANTIC"
    HYBRID = "HYBRID"
    MANUAL = "MANUAL"


class Discipline(StrEnum):
    CIVIL = "CIVIL"
    PIPING = "PIPING"
    ELECTRICAL = "ELECTRICAL"
    MECHANICAL = "MECHANICAL"
    INSTRUMENTATION = "INSTRUMENTATION"
    STRUCTURAL = "STRUCTURAL"
    WELDING_NDT = "WELDING_NDT"
    SURVEY = "SURVEY"
    COATING = "COATING"
    TESTING_PRECOMMISSIONING = "TESTING_PRECOMMISSIONING"
    OTHER = "OTHER"


class WBSLevel(StrEnum):
    """Hierarchy depth of a schedule node (L1 coarsest, L6 finest)."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"


class DependencyType(StrEnum):
    FINISH_TO_START = "FS"
    START_TO_START = "SS"
    FINISH_TO_FINISH = "FF"
    START_TO_FINISH = "SF"


class DocumentType(StrEnum):
    SCHEDULE = "SCHEDULE"
    DAILY_PROGRESS_REPORT = "DAILY_PROGRESS_REPORT"
    SITE_DIARY = "SITE_DIARY"
    DISCIPLINE_SHEET = "DISCIPLINE_SHEET"
    OTHER = "OTHER"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    MATCH_CONFIRM = "MATCH_CONFIRM"
    MATCH_REJECT = "MATCH_REJECT"
    UPLOAD = "UPLOAD"
    EXPORT = "EXPORT"
