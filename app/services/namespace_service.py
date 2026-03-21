import logging
import re

from fastapi import HTTPException, status

from app.k8s.client import MANAGED_BY_LABEL, MANAGED_BY_VALUE, KubernetesClient
from app.models.namespace import (
    CreateNamespaceRequest,
    NamespaceDetail,
    NamespaceSummary,
    QuotaDefaults,
    QuotaUsage,
)

logger = logging.getLogger("namespace_provisioner.services")

CPU_RE = re.compile(r"^(\d+)(m?)$")
MEMORY_RE = re.compile(r"^(\d+)(Mi|Gi)?$")

MIN_CPU_MILLICORES = 50
MIN_MEMORY_MI = 64


def _parse_cpu_to_millicores(value: str) -> int:
    match = CPU_RE.match(value)
    if not match:
        raise ValueError(f"Cannot parse CPU value: {value}")
    num, unit = int(match.group(1)), match.group(2)
    return num if unit == "m" else num * 1000


def _millicores_to_str(m: int) -> str:
    if m >= 1000 and m % 1000 == 0:
        return str(m // 1000)
    return f"{m}m"


def _parse_memory_to_mi(value: str) -> int:
    match = MEMORY_RE.match(value)
    if not match:
        raise ValueError(f"Cannot parse memory value: {value}")
    num, unit = int(match.group(1)), match.group(2)
    if unit == "Gi":
        return num * 1024
    return num


def _mi_to_str(mi: int) -> str:
    if mi >= 1024 and mi % 1024 == 0:
        return f"{mi // 1024}Gi"
    return f"{mi}Mi"


class NamespaceService:
    def __init__(self, k8s_client: KubernetesClient):
        self.k8s = k8s_client

    def create_namespace(self, req: CreateNamespaceRequest) -> dict:
        existing = self.k8s.get_namespace(req.name)
        created = False

        if existing is not None:
            labels = existing.metadata.labels or {}
            if labels.get(MANAGED_BY_LABEL) != MANAGED_BY_VALUE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Namespace '{req.name}' exists but is not managed by this API",
                )
            logger.info("Namespace %s exists and is managed, upserting resources", req.name)
        else:
            labels = {
                MANAGED_BY_LABEL: MANAGED_BY_VALUE,
                "team": req.team,
                "environment": req.environment,
            }
            self.k8s.create_namespace(req.name, labels)
            created = True

        defaults = QuotaDefaults.for_environment(req.environment)
        merged = defaults.merge(req.quota)

        hard = {
            "requests.cpu": merged.cpu_requests,
            "limits.cpu": merged.cpu_limits,
            "requests.memory": merged.memory_requests,
            "limits.memory": merged.memory_limits,
            "pods": str(merged.pods),
        }
        self.k8s.create_or_update_resource_quota(req.name, hard=hard)

        default, default_request = self.compute_limit_range(merged)
        self.k8s.create_or_update_limit_range(
            req.name, default=default, default_request=default_request
        )

        self._apply_network_policies(req.name)

        return {"name": req.name, "created": created}

    def get_namespace(self, name: str) -> NamespaceDetail:
        ns = self.k8s.get_namespace(name)
        if ns is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Namespace '{name}' not found",
            )
        labels = ns.metadata.labels or {}
        if labels.get(MANAGED_BY_LABEL) != MANAGED_BY_VALUE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Namespace '{name}' is not managed by this API",
            )

        quota_obj = self.k8s.get_resource_quota(name)
        quota = {}
        if quota_obj and quota_obj.status:
            field_map = {
                "requests.cpu": "cpu_requests",
                "limits.cpu": "cpu_limits",
                "requests.memory": "memory_requests",
                "limits.memory": "memory_limits",
                "pods": "pods",
            }
            for k8s_key, api_key in field_map.items():
                hard_val = (quota_obj.status.hard or {}).get(k8s_key, "0")
                used_val = (quota_obj.status.used or {}).get(k8s_key, "0")
                quota[api_key] = QuotaUsage(hard=hard_val, used=used_val)

        return NamespaceDetail(
            name=name,
            team=labels.get("team", ""),
            environment=labels.get("environment", ""),
            created_at=ns.metadata.creation_timestamp.isoformat(),
            quota=quota,
        )

    def list_namespaces(
        self,
        team: str | None = None,
        environment: str | None = None,
    ) -> list[NamespaceSummary]:
        namespaces = self.k8s.list_managed_namespaces(
            team=team, environment=environment
        )
        return [
            NamespaceSummary(
                name=ns.metadata.name,
                team=(ns.metadata.labels or {}).get("team", ""),
                environment=(ns.metadata.labels or {}).get("environment", ""),
                created_at=ns.metadata.creation_timestamp.isoformat(),
            )
            for ns in namespaces
        ]

    def delete_namespace(self, name: str, force: bool = False) -> None:
        ns = self.k8s.get_namespace(name)
        if ns is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Namespace '{name}' not found",
            )
        labels = ns.metadata.labels or {}
        if labels.get(MANAGED_BY_LABEL) != MANAGED_BY_VALUE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Namespace '{name}' is not managed by this API",
            )
        if not force:
            pod_count = self.k8s.list_pods(name)
            if pod_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Namespace '{name}' has {pod_count} running pod(s). "
                        "Use ?force=true to delete anyway."
                    ),
                )
        self.k8s.delete_namespace(name)

    def compute_limit_range(
        self, quota: QuotaDefaults
    ) -> tuple[dict, dict]:
        limit_cpu = max(
            _parse_cpu_to_millicores(quota.cpu_limits) * 25 // 100,
            MIN_CPU_MILLICORES,
        )
        limit_mem = max(
            _parse_memory_to_mi(quota.memory_limits) * 25 // 100,
            MIN_MEMORY_MI,
        )
        request_cpu = max(
            _parse_cpu_to_millicores(quota.cpu_requests) * 10 // 100,
            MIN_CPU_MILLICORES,
        )
        request_mem = max(
            _parse_memory_to_mi(quota.memory_requests) * 10 // 100,
            MIN_MEMORY_MI,
        )

        default = {
            "cpu": _millicores_to_str(limit_cpu),
            "memory": _mi_to_str(limit_mem),
        }
        default_request = {
            "cpu": _millicores_to_str(request_cpu),
            "memory": _mi_to_str(request_mem),
        }
        return default, default_request

    def _apply_network_policies(self, namespace: str) -> None:
        from kubernetes import client as k8s

        deny_all_spec = k8s.V1NetworkPolicySpec(
            pod_selector=k8s.V1LabelSelector(),
            policy_types=["Ingress"],
        )
        self.k8s.create_or_update_network_policy(
            namespace, "deny-all-ingress", deny_all_spec
        )

        allow_same_ns_spec = k8s.V1NetworkPolicySpec(
            pod_selector=k8s.V1LabelSelector(),
            policy_types=["Ingress"],
            ingress=[
                k8s.V1NetworkPolicyIngressRule(
                    _from=[k8s.V1NetworkPolicyPeer(
                        pod_selector=k8s.V1LabelSelector()
                    )]
                )
            ],
        )
        self.k8s.create_or_update_network_policy(
            namespace, "allow-same-namespace", allow_same_ns_spec
        )
