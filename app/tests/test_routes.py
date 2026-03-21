from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.namespace import NamespaceDetail, NamespaceSummary, QuotaUsage


class TestHealthEndpoint:
    def test_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCreateNamespace:
    def test_create_returns_201(self, client):
        client.mock_service.create_namespace.return_value = {
            "name": "payments-dev",
            "created": True,
        }
        response = client.post(
            "/namespaces",
            json={
                "name": "payments-dev",
                "team": "payments",
                "environment": "dev",
            },
        )
        assert response.status_code == 201

    def test_upsert_returns_200(self, client):
        client.mock_service.create_namespace.return_value = {
            "name": "payments-dev",
            "created": False,
        }
        response = client.post(
            "/namespaces",
            json={
                "name": "payments-dev",
                "team": "payments",
                "environment": "dev",
            },
        )
        assert response.status_code == 200

    def test_invalid_name_returns_422(self, client):
        response = client.post(
            "/namespaces",
            json={
                "name": "INVALID",
                "team": "payments",
                "environment": "dev",
            },
        )
        assert response.status_code == 422


class TestListNamespaces:
    def test_list_returns_200(self, client):
        client.mock_service.list_namespaces.return_value = [
            NamespaceSummary(
                name="payments-dev",
                team="payments",
                environment="dev",
                created_at="2026-03-21T10:00:00Z",
            )
        ]
        response = client.get("/namespaces")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_list_with_filters(self, client):
        client.mock_service.list_namespaces.return_value = []
        response = client.get("/namespaces?team=payments&environment=dev")
        assert response.status_code == 200
        client.mock_service.list_namespaces.assert_called_once_with(
            team="payments", environment="dev"
        )


class TestGetNamespace:
    def test_get_returns_200(self, client):
        client.mock_service.get_namespace.return_value = NamespaceDetail(
            name="payments-dev",
            team="payments",
            environment="dev",
            created_at="2026-03-21T10:00:00Z",
            quota={
                "cpu_requests": QuotaUsage(hard="1", used="250m"),
                "cpu_limits": QuotaUsage(hard="2", used="500m"),
                "memory_requests": QuotaUsage(hard="1Gi", used="128Mi"),
                "memory_limits": QuotaUsage(hard="2Gi", used="256Mi"),
                "pods": QuotaUsage(hard="10", used="3"),
            },
        )
        response = client.get("/namespaces/payments-dev")
        assert response.status_code == 200
        assert response.json()["quota"]["cpu_limits"]["hard"] == "2"


class TestDeleteNamespace:
    def test_delete_returns_204(self, client):
        client.mock_service.delete_namespace.return_value = None
        response = client.delete("/namespaces/payments-dev")
        assert response.status_code == 204

    def test_force_delete(self, client):
        client.mock_service.delete_namespace.return_value = None
        response = client.delete("/namespaces/payments-dev?force=true")
        assert response.status_code == 204
        client.mock_service.delete_namespace.assert_called_once_with(
            "payments-dev", force=True
        )


class TestAuthRequired:
    def test_unauthenticated_returns_403(self, unauthed_client):
        response = unauthed_client.get("/namespaces")
        assert response.status_code == 403
