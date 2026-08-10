import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models import Plan, SubscriptionStatus, Tenant


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_maker = async_sessionmaker(bind=db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    session_maker = async_sessionmaker(bind=db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed plans + two tenants for every test.
    async with session_maker() as session:
        session.add_all([
            Plan(id="free", name="Free", api_call_limit=1000, ai_token_limit=100_000, monthly_price_cents=0),
            Plan(id="pro", name="Pro", api_call_limit=50_000, ai_token_limit=5_000_000, monthly_price_cents=2900),
        ])
        session.add_all([
            Tenant(id="t-free", name="Free Tenant", plan_id="free", subscription_status=SubscriptionStatus.active),
            Tenant(id="t-pro", name="Pro Tenant", plan_id="pro", subscription_status=SubscriptionStatus.active),
            Tenant(
                id="t-pastdue",
                name="Past Due Tenant",
                plan_id="pro",
                subscription_status=SubscriptionStatus.past_due,
            ),
        ])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def tenant_headers():
    def _headers(tenant_id: str, idempotency_key: str = "key-1"):
        return {"X-Tenant-Id": tenant_id, "Idempotency-Key": idempotency_key}
    return _headers
