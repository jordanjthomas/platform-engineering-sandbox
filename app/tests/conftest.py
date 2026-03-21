from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth import require_auth
from app.main import app
from app.routers.namespaces import get_namespace_service
from app.services.namespace_service import NamespaceService


@pytest.fixture
def mock_service():
    return MagicMock(spec=NamespaceService)


@pytest.fixture
def client(mock_service):
    def override_auth():
        return True

    def override_service():
        return mock_service

    app.dependency_overrides[require_auth] = override_auth
    app.dependency_overrides[get_namespace_service] = override_service

    test_client = TestClient(app)
    test_client.mock_service = mock_service
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client():
    app.dependency_overrides.clear()
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
