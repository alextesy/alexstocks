"""Tests for user profile API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, UserProfile
from app.db.session import get_db
from app.main import app
from app.models.dto import UserCreateDTO, UserProfileCreateDTO
from app.repos.user_repo import UserRepository
from app.services.auth_service import AuthService


@pytest.fixture
def test_db_engine():
    """Create a test database engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_session(test_db_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def override_db(test_session):
    """Override database dependency with test session."""

    def _get_db():
        yield test_session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_session):
    """Create a test user."""
    repo = UserRepository(test_session)
    user_dto = UserCreateDTO(
        email="test@example.com",
        auth_provider="google",
        auth_provider_id="google_123",
    )
    user = repo.create_user(user_dto)
    test_session.commit()
    return user


@pytest.fixture
def test_user_with_profile(test_session, test_user):
    """Create a test user with profile."""
    repo = UserRepository(test_session)
    profile_dto = UserProfileCreateDTO(
        user_id=test_user.id,
        display_name="Test User",
        timezone="America/New_York",
        avatar_url="https://example.com/avatar.jpg",  # From OAuth provider
        preferences={"notification_defaults": {"notify_on_surges": True}},
    )
    profile = repo.create_profile(profile_dto)
    test_session.commit()
    return test_user, profile


@pytest.fixture
def authenticated_client(test_user, override_db):
    """Create an authenticated test client."""
    auth_service = AuthService()
    session_token = auth_service.create_session_token(
        user_id=test_user.id, email=test_user.email
    )

    client = TestClient(app)
    client.cookies.set("session_token", session_token)
    return client


def test_get_profile_unauthenticated(override_db):
    """Test GET /api/users/me requires authentication."""
    client = TestClient(app)
    response = client.get("/api/users/me")
    assert response.status_code == 401


def test_get_profile_no_profile(authenticated_client, test_user):
    """Test GET /api/users/me creates default profile if missing."""
    response = authenticated_client.get("/api/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == "test@example.com"
    assert data["nickname"] is None
    assert data["avatar_url"] is None
    assert data["timezone"] == "UTC"
    assert data["notification_defaults"] == {}


def test_get_profile_with_existing_profile(
    authenticated_client, test_user_with_profile
):
    """Test GET /api/users/me returns existing profile."""
    test_user, profile = test_user_with_profile
    response = authenticated_client.get("/api/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == "test@example.com"
    assert data["nickname"] == "Test User"
    assert data["avatar_url"] == "https://example.com/avatar.jpg"
    assert data["timezone"] == "America/New_York"
    assert data["notification_defaults"] == {"notify_on_surges": True}


def test_update_profile_unauthenticated(override_db):
    """Test PUT /api/users/me requires authentication."""
    client = TestClient(app)
    response = client.put("/api/users/me", json={"nickname": "New Name"})
    assert response.status_code == 401


def test_update_profile_nickname(authenticated_client, test_user_with_profile):
    """Test updating nickname."""
    response = authenticated_client.put(
        "/api/users/me", json={"nickname": "Updated Name"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == "Updated Name"

    # Verify persisted
    response = authenticated_client.get("/api/users/me")
    assert response.json()["nickname"] == "Updated Name"


def test_update_profile_timezone(authenticated_client, test_user_with_profile):
    """Test updating timezone."""
    response = authenticated_client.put(
        "/api/users/me", json={"timezone": "Europe/London"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["timezone"] == "Europe/London"


def test_update_profile_notification_defaults(
    authenticated_client, test_user_with_profile
):
    """Test updating notification defaults."""
    defaults = {
        "notify_on_surges": True,
        "notify_on_most_discussed": False,
    }
    response = authenticated_client.put(
        "/api/users/me", json={"notification_defaults": defaults}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["notification_defaults"] == defaults


def test_update_profile_multiple_fields(authenticated_client, test_user_with_profile):
    """Test updating multiple fields at once."""
    response = authenticated_client.put(
        "/api/users/me",
        json={
            "nickname": "Multi Update",
            "timezone": "Asia/Tokyo",
            "notification_defaults": {
                "notify_on_surges": False,
                "notify_on_most_discussed": True,
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == "Multi Update"
    assert data["timezone"] == "Asia/Tokyo"
    assert data["notification_defaults"] == {
        "notify_on_surges": False,
        "notify_on_most_discussed": True,
    }


def test_update_profile_nickname_uniqueness(
    authenticated_client, test_user_with_profile, test_session
):
    """Test nickname uniqueness validation."""
    test_user, _ = test_user_with_profile

    # Create another user with a nickname
    repo = UserRepository(test_session)
    other_user = repo.create_user(
        UserCreateDTO(
            email="other@example.com",
            auth_provider="google",
            auth_provider_id="google_456",
        )
    )
    test_session.commit()

    repo.create_profile(
        UserProfileCreateDTO(
            user_id=other_user.id,
            display_name="Existing Nickname",
            timezone="UTC",
        )
    )
    test_session.commit()

    # Try to use the same nickname
    response = authenticated_client.put(
        "/api/users/me", json={"nickname": "Existing Nickname"}
    )
    assert response.status_code == 400
    assert "already taken" in response.json()["detail"].lower()


def test_update_profile_nickname_case_insensitive(
    authenticated_client, test_user_with_profile, test_session
):
    """Test nickname uniqueness is case-insensitive."""
    test_user, _ = test_user_with_profile

    # Create another user with a nickname
    repo = UserRepository(test_session)
    other_user = repo.create_user(
        UserCreateDTO(
            email="other@example.com",
            auth_provider="google",
            auth_provider_id="google_456",
        )
    )
    test_session.commit()

    repo.create_profile(
        UserProfileCreateDTO(
            user_id=other_user.id,
            display_name="ExistingNickname",
            timezone="UTC",
        )
    )
    test_session.commit()

    # Try to use the same nickname with different case
    response = authenticated_client.put(
        "/api/users/me", json={"nickname": "existingnickname"}
    )
    assert response.status_code == 400


def test_update_profile_nickname_empty(authenticated_client, test_user_with_profile):
    """Test nickname cannot be empty."""
    response = authenticated_client.put("/api/users/me", json={"nickname": "   "})
    assert response.status_code == 400


def test_update_profile_nickname_too_long(authenticated_client, test_user_with_profile):
    """Test nickname length validation."""
    long_nickname = "a" * 101
    response = authenticated_client.put(
        "/api/users/me", json={"nickname": long_nickname}
    )
    assert response.status_code == 400


def test_update_profile_own_nickname(authenticated_client, test_user_with_profile):
    """Test user can keep their own nickname."""
    test_user, profile = test_user_with_profile
    # Update to same nickname (should succeed)
    response = authenticated_client.put(
        "/api/users/me", json={"nickname": profile.display_name}
    )
    assert response.status_code == 200


def test_update_profile_invalid_nickname(authenticated_client, test_user_with_profile):
    """Test validation of nickname field."""
    # Nickname too long
    long_nickname = "a" * 101
    response = authenticated_client.put(
        "/api/users/me", json={"nickname": long_nickname}
    )
    assert response.status_code == 400


def test_auth_service_generates_unique_display_name(test_session):
    """AuthService should generate unique display names for duplicate Google names."""
    auth_service = AuthService()

    user1 = auth_service.get_or_create_user(
        db=test_session,
        auth_provider_id="google_1",
        email="unique1@example.com",
        auth_provider="google",
        display_name="Alex Example",
    )

    user2 = auth_service.get_or_create_user(
        db=test_session,
        auth_provider_id="google_2",
        email="unique2@example.com",
        auth_provider="google",
        display_name="Alex Example",
    )

    profile1 = test_session.query(UserProfile).filter_by(user_id=user1.id).first()
    profile2 = test_session.query(UserProfile).filter_by(user_id=user2.id).first()

    assert profile1 is not None
    assert profile2 is not None
    assert profile1.display_name == "Alex Example"
    assert profile2.display_name != profile1.display_name
    assert profile2.display_name.startswith("Alex Example")
