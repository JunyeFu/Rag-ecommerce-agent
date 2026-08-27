"""Frozen PostgreSQL schema for domain revision 20260826_0001."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()


def uid(name: str, target: str | None = None, ondelete: str = "RESTRICT") -> Column:
    args = [ForeignKey(target, ondelete=ondelete)] if target else []
    return Column(name, UUID(as_uuid=True), *args, nullable=False, primary_key=target is None)


marketplaces = Table(
    "marketplaces",
    metadata,
    uid("id"),
    Column("code", String(32), nullable=False, unique=True),
    Column("display_name", String(256), nullable=False),
    Column("allowed_hosts", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
merchants = Table(
    "merchants",
    metadata,
    uid("id"),
    uid("marketplace_id", "marketplaces.id"),
    Column("external_key", String(160), nullable=False),
    Column("display_name", String(256), nullable=False),
    Column("verified", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("marketplace_id", "external_key", name="uq_merchant_marketplace_external"),
)
products = Table(
    "products",
    metadata,
    uid("id"),
    Column("canonical_name", String(256), nullable=False),
    Column("category_key", String(96), nullable=False),
    Column("brand_key", String(96)),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
product_variants = Table(
    "product_variants",
    metadata,
    uid("id"),
    uid("product_id", "products.id"),
    Column("variant_key", String(160), nullable=False),
    Column("attributes", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("product_id", "variant_key", name="uq_variant_product_key"),
)
offers = Table(
    "offers",
    metadata,
    uid("id"),
    uid("variant_id", "product_variants.id"),
    uid("merchant_id", "merchants.id"),
    Column("external_key", String(200), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("merchant_id", "external_key", name="uq_offer_merchant_external"),
)
offer_quotes = Table(
    "offer_quotes",
    metadata,
    uid("id"),
    uid("offer_id", "offers.id"),
    Column("verification", String(32), nullable=False),
    Column("availability", String(24), nullable=False),
    Column("price_minor", BigInteger),
    Column("shipping_minor", BigInteger),
    Column("currency", String(3), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("source_ref", String(512), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("currency = 'CNY'", name="ck_quote_currency_cny"),
    CheckConstraint("expires_at > collected_at", name="ck_quote_time_order"),
    CheckConstraint(
        "verification <> 'DISCOVERY_ONLY' OR (price_minor IS NULL AND shipping_minor IS NULL)",
        name="ck_discovery_has_no_money",
    ),
    CheckConstraint(
        "availability <> 'UNAVAILABLE' OR price_minor IS NULL", name="ck_unavailable_has_no_price"
    ),
)
deep_links = Table(
    "deep_links",
    metadata,
    uid("id"),
    uid("offer_id", "offers.id"),
    Column("url", Text, nullable=False),
    Column("host", String(253), nullable=False),
    Column("disclosure", String(300), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
shopping_missions = Table(
    "shopping_missions",
    metadata,
    uid("id"),
    Column("user_ref", String(128), nullable=False),
    Column("goal", String(500), nullable=False),
    Column("budget_minor", BigInteger),
    Column("currency", String(3)),
    Column("hard_constraints", JSON, nullable=False),
    Column("exclusions", JSON, nullable=False),
    Column("consented_preferences", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "budget_minor IS NULL OR budget_minor >= 0", name="ck_mission_budget_nonnegative"
    ),
)
shopping_lists = Table(
    "shopping_lists",
    metadata,
    uid("id"),
    uid("mission_id", "shopping_missions.id"),
    Column("name", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
shopping_list_items = Table(
    "shopping_list_items",
    metadata,
    uid("list_id", "shopping_lists.id", "CASCADE"),
    uid("variant_id", "product_variants.id"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("list_id", "variant_id", name="uq_list_variant"),
)
carts = Table(
    "carts",
    metadata,
    uid("id"),
    uid("mission_id", "shopping_missions.id"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("mission_id", name="uq_cart_mission"),
)
cart_items = Table(
    "cart_items",
    metadata,
    uid("cart_id", "carts.id", "CASCADE"),
    uid("offer_id", "offers.id"),
    Column("quantity", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("cart_id", "offer_id", name="uq_cart_offer"),
    CheckConstraint("quantity BETWEEN 1 AND 99", name="ck_cart_quantity"),
)
conversations = Table(
    "conversations",
    metadata,
    uid("id"),
    uid("mission_id", "shopping_missions.id"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
agent_runs = Table(
    "agent_runs",
    metadata,
    uid("id"),
    uid("conversation_id", "conversations.id"),
    Column("idempotency_key", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("model_version", String(128), nullable=False),
    Column("prompt_version", String(128), nullable=False),
    Column("policy_version", String(128), nullable=False),
    Column("contract_version", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("conversation_id", "idempotency_key", name="uq_run_conversation_idempotency"),
)
agent_steps = Table(
    "agent_steps",
    metadata,
    uid("id"),
    uid("run_id", "agent_runs.id"),
    Column("sequence", Integer, nullable=False),
    Column("kind", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("run_id", "sequence", name="uq_step_run_sequence"),
    CheckConstraint("sequence >= 0", name="ck_step_sequence"),
)
tool_invocations = Table(
    "tool_invocations",
    metadata,
    uid("id"),
    uid("step_id", "agent_steps.id"),
    Column("tool_name", String(100), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("arguments_sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("step_id", "idempotency_key", name="uq_tool_step_idempotency"),
)
evidence_refs = Table(
    "evidence_refs",
    metadata,
    uid("id"),
    uid("run_id", "agent_runs.id"),
    uid("step_id", "agent_steps.id"),
    Column("evidence_type", String(64), nullable=False),
    Column("source_ref", String(512), nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

FORBIDDEN_TRANSACTION_TABLES = frozenset(
    {"orders", "payments", "refunds", "shipments", "addresses"}
)
