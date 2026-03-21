from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi import HTTPException
from kubernetes.client.exceptions import ApiException

from app.k8s.client import MANAGED_BY_LABEL, MANAGED_BY_VALUE
from app.models.namespace import CreateNamespaceRequest, QuotaSpec
from app.services.namespace_service import NamespaceService


@pytest.fixture
def mock_k8s():
    return MagicMock()


@pytest.fixture
def service(mock_k8s):
    return NamespaceService(mock_k8s)


def make_ns_object(name, labels=None, creation_timestamp="2026-03-21T10:00:00Z"):
    ns = MagicMock()
    ns.metadata.name = name
    ns.metadata.labels = labels or {}
    ns.metadata.creation_timestamp.isoformat.return_value = creation_timestamp
    return ns


class TestCreateNamespace:
    def test_creates_namespace_with_all_resources(self, service, mock_k8s):
        mock_k8s.get_namespace.return_value = None
        req = CreateNamespaceRequest(
            name="payments-dev", team="payments", environment="dev"
        )
        result = service.create_namespace(req)
        assert result["name"] == "payments-dev"
        assert result["created"] is True
        mock_k8s.create_namespace.assert_called_once()
        mock_k8s.create_or_update_resource_quota.assert_called_once()
        mock_k8s.create_or_update_limit_range.assert_called_once()
        assert mock_k8s.create_or_update_network_policy.call_count == 2

    def test_upserts_when_namespace_exists_and_managed(self, service, mock_k8s):
        existing = make_ns_object("payments-dev", {
            MANAGED_BY_LABEL: MANAGED_BY_VALUE,
            "team": "payments",
            "environment": "dev",
        })
        mock_k8s.get_namespace.return_value = existing
        req = CreateNamespaceRequest(
            name="payments-dev", team="payments", environment="dev"
        )
        result = service.create_namespace(req)
        assert result["created"] is False
        mock_k8s.create_namespace.assert_not_called()
        mock_k8s.create_or_update_resource_quota.assert_called_once()

    def test_rejects_unmanaged_existing_namespace(self, service, mock_k8s):
        mock_k8s.get_namespace.return_value = make_ns_object("test-ns", {})
        req = CreateNamespaceRequest(
            name="test-ns", team="payments", environment="dev"
        )
        with pytest.raises(HTTPException) as exc_info:
            service.create_namespace(req)
        assert exc_info.value.status_code == 409

    def test_applies_custom_quota_overrides(self, service, mock_k8s):
        mock_k8s.get_namespace.return_value = None
        req = CreateNamespaceRequest(
            name="payments-dev",
            team="payments",
            environment="dev",
            quota=QuotaSpec(cpu_limits="8", pods=50),
        )
        service.create_namespace(req)
        quota_call = mock_k8s.create_or_update_resource_quota.call_args
        hard = quota_call[1]["hard"] if "hard" in quota_call[1] else quota_call[0][1]
        assert hard["limits.cpu"] == "8"
        assert hard["pods"] == "50"
        assert hard["requests.cpu"] == "1"


class TestGetNamespace:
    def test_returns_detail(self, service, mock_k8s):
        ns = make_ns_object("payments-dev", {
            MANAGED_BY_LABEL: MANAGED_BY_VALUE,
            "team": "payments",
            "environment": "dev",
        })
        mock_k8s.get_namespace.return_value = ns
        quota = MagicMock()
        quota.status.hard = {
            "requests.cpu": "1", "limits.cpu": "2",
            "requests.memory": "1Gi", "limits.memory": "2Gi",
            "pods": "10",
        }
        quota.status.used = {
            "requests.cpu": "250m", "limits.cpu": "500m",
            "requests.memory": "128Mi", "limits.memory": "256Mi",
            "pods": "3",
        }
        mock_k8s.get_resource_quota.return_value = quota
        result = service.get_namespace("payments-dev")
        assert result.name == "payments-dev"
        assert result.quota["cpu_limits"].hard == "2"
        assert result.quota["pods"].used == "3"

    def test_raises_404_when_not_found(self, service, mock_k8s):
        mock_k8s.get_namespace.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            service.get_namespace("missing")
        assert exc_info.value.status_code == 404

    def test_raises_403_when_not_managed(self, service, mock_k8s):
        ns = make_ns_object("kube-system", {})
        mock_k8s.get_namespace.return_value = ns
        with pytest.raises(HTTPException) as exc_info:
            service.get_namespace("kube-system")
        assert exc_info.value.status_code == 403


class TestDeleteNamespace:
    def test_deletes_empty_managed_namespace(self, service, mock_k8s):
        ns = make_ns_object("payments-dev", {MANAGED_BY_LABEL: MANAGED_BY_VALUE})
        mock_k8s.get_namespace.return_value = ns
        mock_k8s.list_pods.return_value = 0
        service.delete_namespace("payments-dev")
        mock_k8s.delete_namespace.assert_called_once_with("payments-dev")

    def test_rejects_non_empty_namespace(self, service, mock_k8s):
        ns = make_ns_object("payments-dev", {MANAGED_BY_LABEL: MANAGED_BY_VALUE})
        mock_k8s.get_namespace.return_value = ns
        mock_k8s.list_pods.return_value = 3
        with pytest.raises(HTTPException) as exc_info:
            service.delete_namespace("payments-dev")
        assert exc_info.value.status_code == 409

    def test_force_deletes_non_empty_namespace(self, service, mock_k8s):
        ns = make_ns_object("payments-dev", {MANAGED_BY_LABEL: MANAGED_BY_VALUE})
        mock_k8s.get_namespace.return_value = ns
        mock_k8s.list_pods.return_value = 3
        service.delete_namespace("payments-dev", force=True)
        mock_k8s.delete_namespace.assert_called_once_with("payments-dev")

    def test_raises_403_when_not_managed(self, service, mock_k8s):
        ns = make_ns_object("kube-system", {})
        mock_k8s.get_namespace.return_value = ns
        with pytest.raises(HTTPException) as exc_info:
            service.delete_namespace("kube-system")
        assert exc_info.value.status_code == 403


class TestListNamespaces:
    def test_lists_managed_namespaces(self, service, mock_k8s):
        ns1 = make_ns_object("payments-dev", {
            MANAGED_BY_LABEL: MANAGED_BY_VALUE,
            "team": "payments", "environment": "dev",
        })
        ns2 = make_ns_object("orders-prod", {
            MANAGED_BY_LABEL: MANAGED_BY_VALUE,
            "team": "orders", "environment": "prod",
        })
        mock_k8s.list_managed_namespaces.return_value = [ns1, ns2]
        result = service.list_namespaces()
        assert len(result) == 2
        assert result[0].name == "payments-dev"


class TestComputeLimitRange:
    def test_derives_from_quota(self, service):
        from app.models.namespace import QuotaDefaults
        quota = QuotaDefaults(
            cpu_requests="1", cpu_limits="2",
            memory_requests="1Gi", memory_limits="2Gi", pods=10,
        )
        default, default_request = service.compute_limit_range(quota)
        assert default["cpu"] == "500m"
        assert default["memory"] == "512Mi"
        assert default_request["cpu"] == "100m"
        assert default_request["memory"] == "102Mi"

    def test_enforces_minimum_floor(self, service):
        from app.models.namespace import QuotaDefaults
        quota = QuotaDefaults(
            cpu_requests="100m", cpu_limits="200m",
            memory_requests="128Mi", memory_limits="256Mi", pods=5,
        )
        default, default_request = service.compute_limit_range(quota)
        assert default["cpu"] == "50m"
        assert default_request["cpu"] == "50m"
        assert default_request["memory"] == "64Mi"
