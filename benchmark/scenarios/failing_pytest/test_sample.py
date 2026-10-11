import pytest
import asyncio
from unittest.mock import MagicMock

class DatabaseConnectionPool:
    def __init__(self, dsn: str, max_connections: int = 5):
        self.dsn = dsn
        self.max_connections = max_connections
        self.active_connections = 0

    async def acquire(self):
        if self.active_connections >= self.max_connections:
            raise ConnectionRefusedError(
                f"FATAL 53300: remaining connection slots ({self.max_connections}/{self.max_connections}) "
                f"exhausted on pool {self.dsn}. Reserved for superuser failover."
            )
        self.active_connections += 1
        return MagicMock(name="db_session")

    async def release(self, conn):
        self.active_connections = max(0, self.active_connections - 1)


class TokenBucketRateLimiter:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate

    def consume(self, cost: int = 1) -> bool:
        if self.tokens < cost:
            raise PermissionError(
                f"HTTP 429 Too Many Requests: Burst quota depleted (requested {cost}, available {self.tokens})"
            )
        self.tokens -= cost
        return True


class EnterprisePaymentGateway:
    def __init__(self, db_pool: DatabaseConnectionPool, limiter: TokenBucketRateLimiter):
        self.pool = db_pool
        self.limiter = limiter

    async def execute_settlement(self, tenant_id: str, amount_cents: int, idempotency_key: str):
        if amount_cents <= 0:
            raise ValueError(f"Invalid transaction amount {amount_cents}: ledger requires positive integer.")
        self.limiter.consume(1)
        conn = await self.pool.acquire()
        try:
            if tenant_id == "tenant_isolated_404":
                raise KeyError(
                    f"Tenant '{tenant_id}' not found in active catalog partition or replica replica-us-east-1a."
                )
            return {"status": "SETTLED", "tenant_id": tenant_id, "amount_cents": amount_cents}
        finally:
            await self.pool.release(conn)


@pytest.fixture
def exhausted_pool():
    pool = DatabaseConnectionPool("postgresql://app_admin:secret@pg-primary.internal:5432/fintech_core", max_connections=5)
    pool.active_connections = 5
    return pool

@pytest.fixture
def depleted_rate_limiter():
    return TokenBucketRateLimiter(capacity=0, refill_rate=0.0)

def test_health_check_operational():
    assert {"status": "healthy", "cluster_nodes": 8}["status"] == "healthy"

def test_tenant_configuration_cache():
    cache = {"tenant_001": {"tier": "enterprise"}, "tenant_002": {"tier": "pro"}}
    assert "tenant_001" in cache

def test_exhausted_connection_pool_cascades_into_service_unavailable(exhausted_pool):
    limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1.0)
    service = EnterprisePaymentGateway(exhausted_pool, limiter)
    # Triggers deep multi-frame ConnectionRefusedError
    asyncio.run(service.execute_settlement("tenant_001", 5000, "idem_key_99214"))

def test_rate_limiter_burst_exhaustion(depleted_rate_limiter):
    pool = DatabaseConnectionPool("postgresql://localhost:5432/test", max_connections=10)
    service = EnterprisePaymentGateway(pool, depleted_rate_limiter)
    # Triggers PermissionError HTTP 429
    asyncio.run(service.execute_settlement("tenant_002", 12000, "idem_key_77123"))

def test_tenant_lookup_integrity_failure():
    pool = DatabaseConnectionPool("postgresql://localhost:5432/test", max_connections=10)
    limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1.0)
    service = EnterprisePaymentGateway(pool, limiter)
    # Triggers KeyError tenant not found
    asyncio.run(service.execute_settlement("tenant_isolated_404", 4500, "idem_key_11200"))
