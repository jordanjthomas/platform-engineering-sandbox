import pytest
from pydantic import ValidationError

from app.models.namespace import (
    CreateNamespaceRequest,
    NamespaceDetail,
    NamespaceSummary,
    QuotaDefaults,
    QuotaSpec,
    QuotaUsage,
)


class TestCreateNamespaceRequest:
    def test_valid_request_with_defaults(self):
        req = CreateNamespaceRequest(
            name="payments-dev", team="payments", environment="dev"
        )
        assert req.name == "payments-dev"
        assert req.quota is None

    def test_valid_request_with_custom_quota(self):
        req = CreateNamespaceRequest(
            name="payments-dev",
            team="payments",
            environment="dev",
            quota=QuotaSpec(cpu_requests="4", memory_limits="8Gi", pods=50),
        )
        assert req.quota.cpu_requests == "4"
        assert req.quota.pods == 50

    def test_name_rejects_uppercase(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="Payments-Dev", team="payments", environment="dev"
            )

    def test_name_rejects_leading_hyphen(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="-payments", team="payments", environment="dev"
            )

    def test_name_rejects_trailing_hyphen(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="payments-", team="payments", environment="dev"
            )

    def test_name_rejects_too_long(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="a" * 64, team="payments", environment="dev"
            )

    def test_name_rejects_kube_prefix(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="kube-system", team="payments", environment="dev"
            )

    def test_name_rejects_reserved_default(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="default", team="payments", environment="dev"
            )

    def test_name_rejects_reserved_platform(self):
        with pytest.raises(ValidationError, match="name"):
            CreateNamespaceRequest(
                name="platform", team="payments", environment="dev"
            )


class TestQuotaDefaults:
    def test_dev_defaults(self):
        defaults = QuotaDefaults.for_environment("dev")
        assert defaults.cpu_requests == "1"
        assert defaults.cpu_limits == "2"
        assert defaults.memory_requests == "1Gi"
        assert defaults.memory_limits == "2Gi"
        assert defaults.pods == 10

    def test_prod_defaults(self):
        defaults = QuotaDefaults.for_environment("prod")
        assert defaults.cpu_requests == "2"
        assert defaults.cpu_limits == "4"
        assert defaults.memory_requests == "2Gi"
        assert defaults.memory_limits == "4Gi"
        assert defaults.pods == 20

    def test_unknown_environment_uses_dev_defaults(self):
        defaults = QuotaDefaults.for_environment("staging")
        assert defaults.cpu_requests == "1"
        assert defaults.pods == 10

    def test_merge_with_overrides(self):
        defaults = QuotaDefaults.for_environment("dev")
        overrides = QuotaSpec(cpu_limits="8", pods=50)
        merged = defaults.merge(overrides)
        assert merged.cpu_requests == "1"  # kept default
        assert merged.cpu_limits == "8"  # overridden
        assert merged.pods == 50  # overridden


class TestNamespaceSummary:
    def test_summary_fields(self):
        summary = NamespaceSummary(
            name="payments-dev",
            team="payments",
            environment="dev",
            created_at="2026-03-21T10:00:00Z",
        )
        assert summary.name == "payments-dev"


class TestNamespaceDetail:
    def test_detail_includes_quota(self):
        detail = NamespaceDetail(
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
        assert detail.quota["cpu_limits"].hard == "2"
