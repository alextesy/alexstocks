"""Tests for watchlist management API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import Base, Ticker
from app.db.session import get_db
from app.main import app
from app.models.dto import UserCreateDTO, UserTickerFollowCreateDTO
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
def test_tickers(test_session):
    """Create test tickers."""
    tickers = [
        Ticker(symbol="AAPL", name="Apple Inc."),
        Ticker(symbol="TSLA", name="Tesla Inc."),
        Ticker(symbol="NVDA", name="NVIDIA Corporation"),
        Ticker(symbol="MSFT", name="Microsoft Corporation"),
        Ticker(symbol="GOOGL", name="Alphabet Inc."),
    ]
    test_session.add_all(tickers)
    test_session.commit()
    return tickers


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


class TestWatchlistAPI:
    """Test watchlist management endpoints."""

    def test_get_watchlist_empty(self, authenticated_client, test_user):
        """Test getting empty watchlist."""
        response = authenticated_client.get("/api/users/me/follows")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_watchlist_unauthenticated(self, override_db):
        """Test getting watchlist requires authentication."""
        client = TestClient(app)
        response = client.get("/api/users/me/follows")
        assert response.status_code == 401

    def test_add_ticker_to_watchlist(
        self, authenticated_client, test_user, test_tickers
    ):
        """Test adding a ticker to watchlist."""
        response = authenticated_client.post(
            "/api/users/me/follows",
            json={"ticker": "AAPL"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["user_id"] == test_user.id
        assert data["order"] == 0
        assert data["notify_on_signals"] is True

    def test_add_ticker_invalid_ticker(self, authenticated_client, test_user):
        """Test adding non-existent ticker fails."""
        response = authenticated_client.post(
            "/api/users/me/follows",
            json={"ticker": "INVALID"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_add_ticker_duplicate(self, authenticated_client, test_user, test_tickers):
        """Test adding duplicate ticker fails."""
        # Add first time
        response = authenticated_client.post(
            "/api/users/me/follows",
            json={"ticker": "AAPL"},
        )
        assert response.status_code == 201

        # Try to add again
        response = authenticated_client.post(
            "/api/users/me/follows",
            json={"ticker": "AAPL"},
        )
        assert response.status_code == 400
        assert "already following" in response.json()["detail"].lower()

    def test_add_ticker_exceeds_limit(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test adding ticker when limit is reached."""
        from unittest.mock import patch

        # Patch the limit to 2 for this test
        with patch.object(settings, "USER_MAX_TICKER_FOLLOWS", 2):
            repo = UserRepository(test_session)
            # Add tickers up to the limit
            for ticker in test_tickers[:2]:
                follow_dto = UserTickerFollowCreateDTO(
                    user_id=test_user.id, ticker=ticker.symbol
                )
                repo.create_ticker_follow(follow_dto)
                test_session.flush()
            test_session.commit()

            # Try to add one more - should fail with limit error
            test_ticker = test_tickers[2].symbol
            response = authenticated_client.post(
                "/api/users/me/follows",
                json={"ticker": test_ticker},
            )
            assert response.status_code == 400
            detail = response.json()["detail"].lower()
            assert "limit" in detail

    def test_get_watchlist_with_tickers(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test getting watchlist with multiple tickers."""
        repo = UserRepository(test_session)
        # Add tickers in specific order
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()

        response = authenticated_client.get("/api/users/me/follows")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Check order (should be by order field, then created_at)
        assert data[0]["ticker"] == "AAPL"
        assert data[1]["ticker"] == "TSLA"
        assert data[2]["ticker"] == "NVDA"
        # Check ticker names are included
        assert data[0]["ticker_name"] == "Apple Inc."
        assert data[1]["ticker_name"] == "Tesla Inc."
        assert data[2]["ticker_name"] == "NVIDIA Corporation"

    def test_remove_ticker_from_watchlist(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test removing a ticker from watchlist."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        test_session.commit()

        response = authenticated_client.delete("/api/users/me/follows/AAPL")
        assert response.status_code == 204

        # Verify it's removed
        follows = authenticated_client.get("/api/users/me/follows").json()
        assert len(follows) == 1
        assert follows[0]["ticker"] == "TSLA"

    def test_remove_ticker_not_in_watchlist(
        self, authenticated_client, test_user, test_tickers
    ):
        """Test removing ticker that's not in watchlist."""
        response = authenticated_client.delete("/api/users/me/follows/AAPL")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_remove_ticker_reorders_remaining(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test that removing a ticker reorders remaining items."""
        repo = UserRepository(test_session)
        # Add 3 tickers
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()

        # Remove middle one (TSLA)
        response = authenticated_client.delete("/api/users/me/follows/TSLA")
        assert response.status_code == 204

        # Verify remaining items are reordered sequentially
        follows = authenticated_client.get("/api/users/me/follows").json()
        assert len(follows) == 2
        # Both tickers should be present
        tickers = {f["ticker"] for f in follows}
        assert tickers == {"AAPL", "NVDA"}
        # Orders should be sequential (0, 1)
        orders = sorted(f["order"] for f in follows)
        assert orders == [0, 1]

    def test_reorder_watchlist(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test reordering tickers in watchlist."""
        repo = UserRepository(test_session)
        # Add tickers
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()

        # Reorder: NVDA -> 0, AAPL -> 1, TSLA -> 2
        response = authenticated_client.patch(
            "/api/users/me/follows/reorder",
            json={"ticker_orders": {"NVDA": 0, "AAPL": 1, "TSLA": 2}},
        )
        assert response.status_code == 200

        # Verify new order
        follows = authenticated_client.get("/api/users/me/follows").json()
        assert len(follows) == 3
        assert follows[0]["ticker"] == "NVDA"
        assert follows[0]["order"] == 0
        assert follows[1]["ticker"] == "AAPL"
        assert follows[1]["order"] == 1
        assert follows[2]["ticker"] == "TSLA"
        assert follows[2]["order"] == 2

    def test_reorder_partial_list(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test reordering with partial ticker list."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()

        # Reorder only two tickers
        response = authenticated_client.patch(
            "/api/users/me/follows/reorder",
            json={"ticker_orders": {"NVDA": 0, "TSLA": 1}},
        )
        assert response.status_code == 200

        follows = authenticated_client.get("/api/users/me/follows").json()
        # Check that NVDA and TSLA were reordered
        nvda_follow = next(f for f in follows if f["ticker"] == "NVDA")
        tsla_follow = next(f for f in follows if f["ticker"] == "TSLA")
        assert nvda_follow["order"] == 0
        assert tsla_follow["order"] == 1
        # AAPL should still be there
        assert any(f["ticker"] == "AAPL" for f in follows)

    def test_reorder_invalid_ticker(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test reordering with ticker not in watchlist."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        test_session.commit()

        response = authenticated_client.patch(
            "/api/users/me/follows/reorder",
            json={"ticker_orders": {"INVALID": 0}},
        )
        assert response.status_code == 400
        assert "not in watchlist" in response.json()["detail"].lower()

    def test_search_tickers(self, authenticated_client, test_user, test_tickers):
        """Test searching for tickers."""
        response = authenticated_client.get("/api/users/me/follows/search?q=AP")
        assert response.status_code == 200
        data = response.json()
        # Should find AAPL
        assert len(data) >= 1
        symbols = [t["symbol"] for t in data]
        assert "AAPL" in symbols

    def test_search_tickers_case_insensitive(
        self, authenticated_client, test_user, test_tickers
    ):
        """Test search is case insensitive."""
        response = authenticated_client.get("/api/users/me/follows/search?q=aapl")
        assert response.status_code == 200
        data = response.json()
        symbols = [t["symbol"] for t in data]
        assert "AAPL" in symbols

    def test_search_tickers_includes_all(
        self, authenticated_client, test_user, test_tickers, test_session
    ):
        """Test search includes all tickers (followed or not)."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        test_session.commit()

        response = authenticated_client.get("/api/users/me/follows/search?q=AP")
        assert response.status_code == 200
        data = response.json()
        symbols = [t["symbol"] for t in data]
        # Search should return all matching tickers (exclusion happens on frontend)
        # So AAPL should be in results
        assert "AAPL" in symbols

    def test_search_tickers_empty_query(
        self, authenticated_client, test_user, test_tickers
    ):
        """Test search with empty query."""
        response = authenticated_client.get("/api/users/me/follows/search?q=")
        assert response.status_code == 200
        data = response.json()
        # Should return some results or empty list
        assert isinstance(data, list)

    def test_search_tickers_limit(self, authenticated_client, test_user, test_tickers):
        """Test search respects limit parameter."""
        response = authenticated_client.get("/api/users/me/follows/search?q=A&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2

    def test_add_ticker_with_notification_settings(
        self, authenticated_client, test_user, test_tickers
    ):
        """Test adding ticker with custom notification settings."""
        response = authenticated_client.post(
            "/api/users/me/follows",
            json={
                "ticker": "AAPL",
                "notify_on_signals": True,
                "notify_on_price_change": True,
                "price_change_threshold": 5.0,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["notify_on_signals"] is True
        assert data["notify_on_price_change"] is True
        assert data["price_change_threshold"] == 5.0


class TestWatchlistRepository:
    """Test watchlist repository methods."""

    def test_create_ticker_follow_assigns_order(
        self, test_session, test_user, test_tickers
    ):
        """Test that creating follow assigns sequential order."""
        repo = UserRepository(test_session)
        follow1 = repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        test_session.commit()
        order1 = follow1.order

        follow2 = repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        test_session.commit()
        order2 = follow2.order

        follow3 = repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()
        order3 = follow3.order

        # Orders should be sequential and increasing
        assert order1 < order2 < order3

    def test_get_ticker_follows_ordered(self, test_session, test_user, test_tickers):
        """Test getting follows returns them in order."""
        repo = UserRepository(test_session)
        # Add in different order
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        test_session.commit()
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        test_session.commit()

        follows = repo.get_ticker_follows(test_user.id)
        assert len(follows) == 3
        # Should be ordered by order field (ascending)
        orders = [f.order for f in follows]
        assert orders == sorted(orders)  # Should be in ascending order
        # Check that all tickers are present
        tickers = {f.ticker for f in follows}
        assert tickers == {"NVDA", "AAPL", "TSLA"}

    def test_delete_ticker_follow_reorders(self, test_session, test_user, test_tickers):
        """Test deleting a follow reorders remaining."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        test_session.commit()
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        test_session.commit()
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()

        # Delete middle one (order 1)
        repo.delete_ticker_follow(test_user.id, "TSLA")
        test_session.commit()

        follows = repo.get_ticker_follows(test_user.id)
        assert len(follows) == 2
        # Both should be present and ordered sequentially
        follows_dict = {f.ticker: f for f in follows}
        assert "AAPL" in follows_dict
        assert "NVDA" in follows_dict
        # Orders should be sequential (0, 1)
        orders = sorted(f.order for f in follows)
        assert orders == [0, 1]

    def test_reorder_ticker_follows(self, test_session, test_user, test_tickers):
        """Test reordering follows."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="TSLA")
        )
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="NVDA")
        )
        test_session.commit()

        # Reorder
        repo.reorder_ticker_follows(test_user.id, {"NVDA": 0, "AAPL": 1, "TSLA": 2})
        test_session.commit()

        follows = repo.get_ticker_follows(test_user.id)
        assert follows[0].ticker == "NVDA"
        assert follows[0].order == 0
        assert follows[1].ticker == "AAPL"
        assert follows[1].order == 1
        assert follows[2].ticker == "TSLA"
        assert follows[2].order == 2

    def test_get_ticker_follows_includes_ticker_names(
        self, test_session, test_user, test_tickers
    ):
        """Test that get_ticker_follows includes ticker names."""
        repo = UserRepository(test_session)
        repo.create_ticker_follow(
            UserTickerFollowCreateDTO(user_id=test_user.id, ticker="AAPL")
        )
        test_session.commit()

        follows = repo.get_ticker_follows(test_user.id)
        assert len(follows) == 1
        assert follows[0].ticker_name == "Apple Inc."
