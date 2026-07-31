
import cloudinary.uploader
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("MAIL_USERNAME", "test")
os.environ.setdefault("MAIL_PASSWORD", "test")
os.environ.setdefault("MAIL_FROM", "test@example.com")
os.environ.setdefault("MAIL_SERVER", "smtp.example.com")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "test")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test")

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crud
import database
import main
import models
import schemas
import security
from cache import get_redis



@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def _mock_cloudinary(monkeypatch):
    monkeypatch.setattr(
        cloudinary.uploader,
        "upload",
        lambda *args, **kwargs: {"secure_url": "https://cloudinary.test/fake-avatar.png"},
    )

@pytest.fixture()
def fake_redis():
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield server


from fastapi import Request, Response  # noqa: E402


async def _noop_rate_limiter(self, request: Request, response: Response) -> None:
    return None


@pytest.fixture()
def client(db_session, fake_redis, monkeypatch):

    def override_get_db():
        yield db_session

    def override_get_redis():
        return fake_redis

    # The app's lifespan() normally opens a real Redis connection and
    # initializes FastAPILimiter against it. Redirect both to fakeredis so
    # TestClient's startup event does not require Docker services.
    monkeypatch.setattr(main.Redis, "from_url", lambda *a, **kw: fake_redis)
    monkeypatch.setattr(main.FastAPILimiter, "redis", fake_redis, raising=False)
    monkeypatch.setattr(
        main.FastAPILimiter, "init", lambda *a, **kw: _async_noop(), raising=False
    )
    monkeypatch.setattr(
        main.FastAPILimiter, "close", lambda *a, **kw: _async_noop(), raising=False
    )
    monkeypatch.setattr("fastapi_limiter.depends.RateLimiter.__call__", _noop_rate_limiter)

    main.app.dependency_overrides[database.get_db] = override_get_db
    main.app.dependency_overrides[get_redis] = override_get_redis

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()


async def _async_noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def make_user(db_session):

    def _make(
        username: str = "anna",
        email: str = "anna@example.com",
        password: str = "strongpassword1",
        role: str = "user",
        confirmed: bool = True,
    ) -> models.User:
        user = crud.create_user(
            db_session,
            schemas.UserCreate(username=username, email=email, password=password),
            security.get_password_hash(password),
        )
        if confirmed:
            crud.confirm_user_email(db_session, user)
        if role != "user":
            crud.update_user_role(db_session, user, role)
        return user

    return _make


@pytest.fixture()
def auth_headers():

    def _headers(user: models.User) -> dict:
        token = security.create_access_token({"sub": user.email, "user_id": user.id})
        return {"Authorization": f"Bearer {token}"}

    return _headers