"""
Enterprise Multi-Tenant Billing and Subscription Gateway Service.
Handles customer subscription lifecycles, tiered usage metering, Stripe/Adyen webhook ingestion,
cryptographic signature verification, idempotent invoice generation, and RBAC enforcement.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger("enterprise.billing.service")


class SubscriptionTier(str, Enum):
    FREE_TIER = "tier_free"
    DEVELOPER = "tier_developer"
    PROFESSIONAL = "tier_pro"
    ENTERPRISE = "tier_enterprise"
    UNLIMITED_DEDICATED = "tier_dedicated"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    PENDING_SETTLEMENT = "pending"
    PAID = "paid"
    FAILED_PAYMENT = "failed"
    VOIDED = "voided"
    REFUNDED = "refunded"


class PaymentProvider(str, Enum):
    STRIPE = "stripe"
    ADYEN = "adyen"
    BRAINTREE = "braintree"
    INTERNAL_LEDGER = "internal_ledger"


class TenantIsolationViolation(Exception):
    """Raised when an operation attempts to cross tenant schema boundaries."""
    pass


class IdempotencyConflictError(Exception):
    """Raised when an operation with an active idempotency key is already in flight."""
    pass


class CryptographicSignatureError(Exception):
    """Raised when incoming webhook signature fails SHA-256 HMAC verification."""
    pass


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    organization_slug: str
    region: str
    tier: SubscriptionTier
    feature_flags: Set[str] = field(default_factory=set)
    created_at_epoch: float = field(default_factory=time.time)

    def is_feature_enabled(self, feature_key: str) -> bool:
        if self.tier == SubscriptionTier.ENTERPRISE:
            return True
        return feature_key in self.feature_flags


@dataclass
class UsageRecord:
    record_id: str
    tenant_id: str
    metric_name: str
    quantity: int
    timestamp_utc: datetime
    dimensions: Dict[str, str] = field(default_factory=dict)


@dataclass
class InvoiceLineItem:
    item_id: str
    description: str
    unit_amount_cents: int
    quantity: int
    subtotal_cents: int
    tax_rate_percent: float = 0.0

    @property
    def total_cents(self) -> int:
        tax_cents = int(self.subtotal_cents * (self.tax_rate_percent / 100.0))
        return self.subtotal_cents + tax_cents


@dataclass
class Invoice:
    invoice_id: str
    tenant_id: str
    provider: PaymentProvider
    status: InvoiceStatus
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    idempotency_key: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    settled_at: Optional[datetime] = None

    @property
    def total_amount_cents(self) -> int:
        return sum(item.total_cents for item in self.line_items)


class CryptographicWebhookValidator:
    """Validates multi-provider webhook payloads using constant-time HMAC comparison."""

    def __init__(self, stripe_secret: str, adyen_secret: str):
        self._stripe_secret = stripe_secret.encode("utf-8")
        self._adyen_secret = adyen_secret.encode("utf-8")

    def verify_stripe_signature(
        self, payload: bytes, signature_header: str, tolerance_seconds: int = 300
    ) -> bool:
        try:
            elements = dict(item.split("=", 1) for item in signature_header.split(","))
            timestamp_str = elements.get("t")
            signature_v1 = elements.get("v1")

            if not timestamp_str or not signature_v1:
                return False

            timestamp = int(timestamp_str)
            current_time = int(time.time())
            if abs(current_time - timestamp) > tolerance_seconds:
                logger.warning("Webhook timestamp out of acceptable tolerance window: %s", timestamp)
                return False

            signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
            expected_hmac = hmac.new(self._stripe_secret, signed_payload, hashlib.sha256).hexdigest()

            return hmac.compare_digest(expected_hmac, signature_v1)
        except Exception as exc:
            logger.error("Failed to parse Stripe webhook signature header: %s", exc)
            return False

    def verify_adyen_signature(self, payload: bytes, signature_header: str) -> bool:
        try:
            expected_hmac = hmac.new(self._adyen_secret, payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected_hmac, signature_header)
        except Exception as exc:
            logger.error("Failed to parse Adyen webhook signature: %s", exc)
            return False


class DistributedIdempotencyStore:
    """Simulates distributed lock and token deduplication for API requests."""

    def __init__(self):
        self._store: Dict[str, Tuple[str, float]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def acquire_or_get(
        self, key: str, tenant_id: str, ttl_seconds: int = 86400
    ) -> Optional[str]:
        composite_key = f"{tenant_id}:{key}"
        now = time.time()

        if composite_key in self._store:
            stored_response, expiry = self._store[composite_key]
            if now < expiry:
                return stored_response
            else:
                del self._store[composite_key]

        return None

    async def save_response(
        self, key: str, tenant_id: str, response_payload: str, ttl_seconds: int = 86400
    ) -> None:
        composite_key = f"{tenant_id}:{key}"
        self._store[composite_key] = (response_payload, time.time() + ttl_seconds)


class RateLimiterRegistry:
    """Sliding-window counter rate limiter for enterprise tenant API endpoints."""

    def __init__(self, requests_per_minute: int = 1200):
        self.default_rpm = requests_per_minute
        self._windows: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, tenant_id: str, custom_limit: Optional[int] = None) -> bool:
        async with self._lock:
            limit = custom_limit or self.default_rpm
            now = time.time()
            window_start = now - 60.0

            if tenant_id not in self._windows:
                self._windows[tenant_id] = []

            # Prune events older than window start
            self._windows[tenant_id] = [t for t in self._windows[tenant_id] if t > window_start]

            if len(self._windows[tenant_id]) >= limit:
                return False

            self._windows[tenant_id].append(now)
            return True


class SubscriptionManager:
    """Core state machine managing lifecycle transitions of SaaS tenant subscriptions."""

    def __init__(self, idempotency_store: DistributedIdempotencyStore):
        self._idempotency = idempotency_store
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._invoices: Dict[str, Invoice] = {}
        self._audit_trail: List[Dict[str, Any]] = []

    async def create_subscription(
        self,
        tenant_context: TenantContext,
        target_tier: SubscriptionTier,
        billing_cycle_months: int = 1,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if idempotency_key:
            existing = await self._idempotency.acquire_or_get(idempotency_key, tenant_context.tenant_id)
            if existing:
                logger.info("Returning cached idempotent subscription creation response")
                return {"cached": True, "payload": existing}

        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        pricing_cents_map = {
            SubscriptionTier.FREE_TIER: 0,
            SubscriptionTier.DEVELOPER: 4900,
            SubscriptionTier.PROFESSIONAL: 29900,
            SubscriptionTier.ENTERPRISE: 149900,
            SubscriptionTier.UNLIMITED_DEDICATED: 499900,
        }

        monthly_cents = pricing_cents_map.get(target_tier, 0)
        total_cents = monthly_cents * billing_cycle_months

        record = {
            "subscription_id": sub_id,
            "tenant_id": tenant_context.tenant_id,
            "tier": target_tier.value,
            "billing_cycle_months": billing_cycle_months,
            "amount_cents": total_cents,
            "status": "active",
            "activated_at": now.isoformat(),
            "auto_renew": True,
        }

        self._subscriptions[sub_id] = record
        self._record_audit_event(tenant_context.tenant_id, "subscription.created", record)

        if idempotency_key:
            await self._idempotency.save_response(idempotency_key, tenant_context.tenant_id, sub_id)

        return record

    async def generate_invoice_for_cycle(
        self,
        tenant_id: str,
        subscription_id: str,
        usage_records: Sequence[UsageRecord],
    ) -> Invoice:
        if subscription_id not in self._subscriptions:
            raise KeyError(f"Subscription {subscription_id} does not exist for tenant {tenant_id}")

        sub = self._subscriptions[subscription_id]
        invoice_id = f"inv_{uuid.uuid4().hex[:10]}"
        line_items: List[InvoiceLineItem] = []

        # Base subscription line item
        line_items.append(
            InvoiceLineItem(
                item_id=f"item_{uuid.uuid4().hex[:8]}",
                description=f"Base Platform Fee - {sub['tier'].upper()}",
                unit_amount_cents=sub["amount_cents"],
                quantity=1,
                subtotal_cents=sub["amount_cents"],
                tax_rate_percent=18.0,
            )
        )

        # Metered usage line items
        usage_summary: Dict[str, int] = {}
        for ur in usage_records:
            if ur.tenant_id != tenant_id:
                raise TenantIsolationViolation(
                    f"Cross-tenant usage aggregation detected: Expected {tenant_id}, found {ur.tenant_id}"
                )
            usage_summary[ur.metric_name] = usage_summary.get(ur.metric_name, 0) + ur.quantity

        for metric, total_qty in usage_summary.items():
            rate_per_unit = self._get_metered_rate(metric)
            subtotal = total_qty * rate_per_unit
            line_items.append(
                InvoiceLineItem(
                    item_id=f"item_{uuid.uuid4().hex[:8]}",
                    description=f"Metered Usage: {metric}",
                    unit_amount_cents=rate_per_unit,
                    quantity=total_qty,
                    subtotal_cents=subtotal,
                    tax_rate_percent=18.0,
                )
            )

        invoice = Invoice(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            provider=PaymentProvider.STRIPE,
            status=InvoiceStatus.PENDING_SETTLEMENT,
            line_items=line_items,
        )

        self._invoices[invoice_id] = invoice
        self._record_audit_event(tenant_id, "invoice.generated", {"invoice_id": invoice_id})
        return invoice

    async def settle_invoice(
        self, invoice_id: str, transaction_reference: str
    ) -> Invoice:
        if invoice_id not in self._invoices:
            raise KeyError(f"Invoice {invoice_id} not found in pending settlement catalog")

        invoice = self._invoices[invoice_id]
        if invoice.status == InvoiceStatus.PAID:
            logger.info("Invoice %s is already settled. Skipping duplicate payment.", invoice_id)
            return invoice

        invoice.status = InvoiceStatus.PAID
        invoice.settled_at = datetime.now(timezone.utc)

        self._record_audit_event(
            invoice.tenant_id,
            "invoice.settled",
            {"invoice_id": invoice_id, "reference": transaction_reference},
        )
        return invoice

    def _get_metered_rate(self, metric: str) -> int:
        rate_table = {
            "api_requests_per_thousand": 15,
            "compute_vcup_hours": 45,
            "vector_index_storage_gb": 80,
            "llm_token_batches_million": 250,
            "egress_bandwidth_gb": 12,
        }
        return rate_table.get(metric, 10)

    def _record_audit_event(self, tenant_id: str, action: str, details: Dict[str, Any]) -> None:
        self._audit_trail.append(
            {
                "audit_id": f"aud_{uuid.uuid4().hex[:8]}",
                "tenant_id": tenant_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details,
            }
        )


class EnterpriseBillingFacade:
    """Unified façade entry point for upstream microservice RPCs and REST controllers."""

    def __init__(
        self,
        stripe_key: str,
        adyen_key: str,
        idempotency_store: Optional[DistributedIdempotencyStore] = None,
    ):
        self.idempotency = idempotency_store or DistributedIdempotencyStore()
        self.validator = CryptographicWebhookValidator(stripe_key, adyen_key)
        self.manager = SubscriptionManager(self.idempotency)
        self.limiter = RateLimiterRegistry(requests_per_minute=2500)

    async def handle_ingress_webhook(
        self,
        provider: str,
        raw_body: bytes,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        if provider == "stripe":
            sig = headers.get("stripe-signature", "")
            if not self.validator.verify_stripe_signature(raw_body, sig):
                raise CryptographicSignatureError("Stripe webhook signature HMAC verification failed.")
            return {"status": "accepted", "provider": "stripe"}
        elif provider == "adyen":
            sig = headers.get("x-adyen-signature", "")
            if not self.validator.verify_adyen_signature(raw_body, sig):
                raise CryptographicSignatureError("Adyen webhook signature HMAC verification failed.")
            return {"status": "accepted", "provider": "adyen"}
        else:
            raise ValueError(f"Unsupported payment gateway provider: {provider}")

    async def process_batch_billing_run(
        self,
        tenants: List[TenantContext],
        usage_matrix: Dict[str, List[UsageRecord]],
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "processed_count": 0,
            "total_settled_cents": 0,
            "failed_tenants": [],
        }

        for tenant in tenants:
            allowed = await self.limiter.check_rate_limit(tenant.tenant_id)
            if not allowed:
                results["failed_tenants"].append(
                    {"tenant_id": tenant.tenant_id, "error": "Rate limit exceeded during batch run"}
                )
                continue

            try:
                sub = await self.manager.create_subscription(tenant, tenant.tier)
                records = usage_matrix.get(tenant.tenant_id, [])
                invoice = await self.manager.generate_invoice_for_cycle(
                    tenant.tenant_id, sub["subscription_id"], records
                )
                settled = await self.manager.settle_invoice(
                    invoice.invoice_id, f"batch_tx_{uuid.uuid4().hex[:8]}"
                )
                results["processed_count"] += 1
                results["total_settled_cents"] += settled.total_amount_cents
            except Exception as err:
                logger.error("Failed batch processing for tenant %s: %s", tenant.tenant_id, err)
                results["failed_tenants"].append({"tenant_id": tenant.tenant_id, "error": str(err)})

        return results
