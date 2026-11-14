"""Shared enum types used by the ORM models and API schemas."""
import enum


class AccountType(str, enum.Enum):
    CHECKING = "checking"
    DEBIT_CARD = "debit_card"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    INVESTMENT = "investment"
    OTHER = "other"


class CategoryKind(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class AssetClass(str, enum.Enum):
    """Net-worth categories tracked manually (Cash is derived from Account
    balances instead — see services/net_worth_service.py)."""

    INVESTMENTS = "investments"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    VEHICLES = "vehicles"
    PRECIOUS_METALS = "precious_metals"
    OTHER = "other"


class CapitalRole(str, enum.Enum):
    """How an asset behaves month to month — set by the user, not inferred:
    the same laptop can be a productive work tool (NEUTRAL) or dead weight
    (DRAIN) depending on how it's actually used, which isn't derivable from
    any stored data."""

    INCOME = "income"  # e.g. a rented-out apartment
    NEUTRAL = "neutral"  # e.g. a laptop used for work, furniture
    DRAIN = "drain"  # e.g. a personal car, an idle depreciating gadget


class RecurringFrequency(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class CryptoTransactionType(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class WidgetType(str, enum.Enum):
    """Chart shape a dashboard widget renders as — see
    services/diagrams.py's Diagram subclasses, one per member here."""

    PIE = "pie"
    BAR = "bar"
    LINE = "line"


class WidgetDimension(str, enum.Enum):
    """What a widget breaks its totals down by. TOTAL means "no breakdown,
    one line" — exclusive to WidgetType.LINE, where a per-category/account/tag
    breakdown would mean multiple series, not supported yet (see
    services/diagrams.py)."""

    CATEGORY = "category"
    SUBCATEGORY = "subcategory"
    ACCOUNT = "account"
    TAG = "tag"
    TYPE = "type"
    TOTAL = "total"


class WidgetMetric(str, enum.Enum):
    SUM = "sum"
    COUNT = "count"


class WidgetGranularity(str, enum.Enum):
    """Time-bucket size for a WidgetType.LINE widget's x-axis."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class RiskLevel(str, enum.Enum):
    """Risk of loss, not asset class — set by the user, not inferred: real
    estate can be a paid-off primary home (LOW) or a leveraged rental
    (HIGH), the same asset_class doesn't determine which. Cash is always
    LOW (see services/net_worth_service.py) — it's the zero-risk anchor an
    80/20-style allocation rule is measured against."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
