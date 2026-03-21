from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from app.k8s.client import KubernetesClient

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "namespace-provisioner"


@pytest.fixture
def mock_core_v1():
    return MagicMock()


@pytest.fixture
def mock_networking_v1():
    return MagicMock()


@pytest.fixture
def k8s_client(mock_core_v1, mock_networking_v1):
    client = KubernetesClient.__new__(KubernetesClient)
    client.core_v1 = mock_core_v1
    client.networking_v1 = mock_networking_v1
    return client


class TestGetNamespace:
    def test_returns_namespace(self, k8s_client, mock_core_v1):
        mock_ns = MagicMock()
        mock_ns.metadata.name = "test-ns"
        mock_core_v1.read_namespace.return_value = mock_ns
        result = k8s_client.get_namespace("test-ns")
        assert result.metadata.name == "test-ns"

    def test_returns_none_when_not_found(self, k8s_client, mock_core_v1):
        mock_core_v1.read_namespace.side_effect = ApiException(status=404)
        result = k8s_client.get_namespace("missing")
        assert result is None


class TestCreateNamespace:
    def test_creates_namespace_with_labels(self, k8s_client, mock_core_v1):
        labels = {"team": "payments", "environment": "dev", MANAGED_BY_LABEL: MANAGED_BY_VALUE}
        k8s_client.create_namespace("payments-dev", labels)
        call_args = mock_core_v1.create_namespace.call_args
        body = call_args[1]["body"] if "body" in call_args[1] else call_args[0][0]
        assert body.metadata.name == "payments-dev"
        assert body.metadata.labels == labels


class TestCreateOrUpdateResourceQuota:
    def test_creates_quota(self, k8s_client, mock_core_v1):
        mock_core_v1.read_namespaced_resource_quota.side_effect = ApiException(status=404)
        hard = {"requests.cpu": "1", "limits.cpu": "2", "pods": "10"}
        k8s_client.create_or_update_resource_quota("test-ns", hard)
        mock_core_v1.create_namespaced_resource_quota.assert_called_once()

    def test_updates_existing_quota(self, k8s_client, mock_core_v1):
        mock_core_v1.read_namespaced_resource_quota.return_value = MagicMock()
        hard = {"requests.cpu": "1", "limits.cpu": "2", "pods": "10"}
        k8s_client.create_or_update_resource_quota("test-ns", hard)
        mock_core_v1.replace_namespaced_resource_quota.assert_called_once()


class TestCreateOrUpdateLimitRange:
    def test_creates_limit_range(self, k8s_client, mock_core_v1):
        mock_core_v1.read_namespaced_limit_range.side_effect = ApiException(status=404)
        k8s_client.create_or_update_limit_range(
            "test-ns", {"cpu": "500m", "memory": "512Mi"}, {"cpu": "100m", "memory": "102Mi"}
        )
        mock_core_v1.create_namespaced_limit_range.assert_called_once()

    def test_updates_existing_limit_range(self, k8s_client, mock_core_v1):
        mock_core_v1.read_namespaced_limit_range.return_value = MagicMock()
        k8s_client.create_or_update_limit_range(
            "test-ns", {"cpu": "500m", "memory": "512Mi"}, {"cpu": "100m", "memory": "102Mi"}
        )
        mock_core_v1.replace_namespaced_limit_range.assert_called_once()


class TestCreateOrUpdateNetworkPolicy:
    def test_creates_network_policy(self, k8s_client, mock_networking_v1):
        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)
        spec = MagicMock()
        k8s_client.create_or_update_network_policy("test-ns", "deny-all", spec)
        mock_networking_v1.create_namespaced_network_policy.assert_called_once()

    def test_updates_existing_network_policy(self, k8s_client, mock_networking_v1):
        mock_networking_v1.read_namespaced_network_policy.return_value = MagicMock()
        spec = MagicMock()
        k8s_client.create_or_update_network_policy("test-ns", "deny-all", spec)
        mock_networking_v1.replace_namespaced_network_policy.assert_called_once()


class TestListManagedNamespaces:
    def test_returns_managed_namespaces(self, k8s_client, mock_core_v1):
        ns1 = MagicMock()
        mock_core_v1.list_namespace.return_value.items = [ns1]
        result = k8s_client.list_managed_namespaces()
        assert len(result) == 1
        mock_core_v1.list_namespace.assert_called_once()

    def test_filters_by_team_and_environment(self, k8s_client, mock_core_v1):
        mock_core_v1.list_namespace.return_value.items = []
        k8s_client.list_managed_namespaces(team="payments", environment="dev")
        call_args = mock_core_v1.list_namespace.call_args
        label_selector = call_args[1].get("label_selector", call_args[0][0] if call_args[0] else "")
        assert "team=payments" in label_selector
        assert "environment=dev" in label_selector


class TestListPods:
    def test_returns_pod_count(self, k8s_client, mock_core_v1):
        mock_core_v1.list_namespaced_pod.return_value.items = [
            MagicMock(), MagicMock()
        ]
        assert k8s_client.list_pods("test-ns") == 2

    def test_returns_zero_for_empty(self, k8s_client, mock_core_v1):
        mock_core_v1.list_namespaced_pod.return_value.items = []
        assert k8s_client.list_pods("test-ns") == 0


class TestDeleteNamespace:
    def test_deletes_namespace(self, k8s_client, mock_core_v1):
        k8s_client.delete_namespace("test-ns")
        mock_core_v1.delete_namespace.assert_called_once_with("test-ns")

    def test_raises_on_not_found(self, k8s_client, mock_core_v1):
        mock_core_v1.delete_namespace.side_effect = ApiException(status=404)
        with pytest.raises(ApiException):
            k8s_client.delete_namespace("missing")
