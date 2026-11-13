from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class OrgType(StrEnum):
    LEGAL_ENTITY = "legal_entity"
    SOLE_PROPRIETOR = "sole_proprietor"
    SELF_EMPLOYED = "self_employed"


class OrgStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class VerificationLevel(StrEnum):
    NONE = "none"
    PHONE = "phone"
    INN = "inn"
    MODERATOR = "moderator"


class MemberStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DocumentKind(StrEnum):
    EGRUL = "egrul"
    EGRIP = "egrip"
    SELF_EMPLOYED = "self_employed"
    OTHER = "other"


class ListingType(StrEnum):
    SALE = "sale"
    RENT_OUT = "rent_out"
    WANTED_BUY = "wanted_buy"
    WANTED_RENT = "wanted_rent"
    SERVICE_OFFER = "service_offer"
    SERVICE_WANTED = "service_wanted"
    TENDER = "tender"
    PARTNERSHIP = "partnership"


class ListingStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class PromotionType(StrEnum):
    TOP = "top"
    HIGHLIGHT = "highlight"
    BUMP = "bump"


class ComplaintStatus(StrEnum):
    NEW = "new"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class AttributeType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    ENUM = "enum"
    MULTI_ENUM = "multi_enum"
    BOOL = "bool"
    RANGE = "range"
    DATE = "date"


class Region(StrEnum):
    DNR = "dnr"
    LNR = "lnr"
    KHERSON = "kherson"
    ZAPOROZHYE = "zaporozhye"


class LoginStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class AuthProviderName(StrEnum):
    TELEGRAM = "telegram"
    SMS = "sms"
    EMAIL = "email"


class ModerationDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


def enum_type(enum_class: type[StrEnum], length: int = 32) -> SAEnum:
    return SAEnum(
        enum_class,
        native_enum=False,
        length=length,
        values_callable=lambda items: [item.value for item in items],
        validate_strings=True,
    )
